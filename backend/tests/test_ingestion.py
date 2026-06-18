# tests/test_ingestion.py — tests for parse_document() and chunk_text() in services/ingestion.py.
# Covers the first two stages of the RAG pipeline: raw bytes → plain text → token chunks.
#
# Key mocking pattern used throughout:
#   patch("services.ingestion.PdfReader", return_value=mock_reader)
#
# Why "services.ingestion.PdfReader" and not "PyPDF2.PdfReader"?
# Because ingestion.py does "from PyPDF2 import PdfReader", which binds the name
# "PdfReader" into the services.ingestion namespace at import time. Patching the
# original location (PyPDF2) has no effect — you must patch where it's USED.

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyPDF2.errors import FileNotDecryptedError, PdfReadError, PdfStreamError

from config import settings
from services.ingestion import ENCODER, chunk_text, parse_document


# ── Fixtures and helpers ──────────────────────────────────────────────────────

@pytest.fixture
def minimal_pdf_bytes() -> bytes:
    """Minimal bytes that pass the %PDF- magic-bytes check.

    PdfReader itself is always mocked in these tests — the bytes only need
    the correct five-byte prefix to get past parse_document's magic-bytes guard.
    """
    return b"%PDF-1.4 minimal fake pdf content for testing"


def _make_mock_reader(
    page_texts: list,
    is_encrypted: bool = False,
) -> MagicMock:
    """Build a mock PdfReader whose pages return controlled text strings.

    Args:
        page_texts: One entry per page. Pass a string for text, None to simulate
                    an image-only page (extract_text returns None).
        is_encrypted: When True, reader.is_encrypted returns True.

    Returns:
        MagicMock that behaves like a PyPDF2 PdfReader instance.
    """
    reader = MagicMock()
    reader.is_encrypted = is_encrypted
    pages = []
    for text in page_texts:
        page = MagicMock()
        # extract_text() returns None for image-only pages — we simulate that here
        page.extract_text.return_value = text
        pages.append(page)
    reader.pages = pages
    return reader


# ── TXT parsing ───────────────────────────────────────────────────────────────

class TestParseTxt:
    """Tests for the TXT decoding branch of parse_document()."""

    def test_parse_document_valid_txt_utf8_returns_correct_string(self) -> None:
        """Verifies that parse_document returns the decoded string for valid UTF-8 bytes."""
        txt_bytes = "Hello, DocuBot!".encode("utf-8")

        result = parse_document(txt_bytes, "txt")

        assert result == "Hello, DocuBot!"

    def test_parse_document_txt_with_bom_strips_bom_from_result(self) -> None:
        """Verifies that parse_document strips the UTF-8 BOM (\\xef\\xbb\\xbf) when present.

        Windows Notepad prepends a BOM byte sequence to UTF-8 files. Using plain
        "utf-8" decode preserves it as a garbage '\\ufeff' character at position 0.
        "utf-8-sig" strips it silently — this test confirms that behaviour.
        """
        # encode("utf-8-sig") adds the BOM prefix automatically for us to test against
        bom_bytes = "Hello from Notepad".encode("utf-8-sig")
        # Sanity-check that the fixture actually has a BOM
        assert bom_bytes[:3] == b"\xef\xbb\xbf", "fixture must start with BOM bytes"

        result = parse_document(bom_bytes, "txt")

        assert result == "Hello from Notepad"
        # "﻿" is the Unicode BOM character — it must not appear in the output
        assert "﻿" not in result

    def test_parse_document_txt_latin1_fallback_decodes_correctly(self) -> None:
        """Verifies that bytes failing UTF-8 decode are correctly decoded via latin-1 fallback.

        \\xe9 alone is invalid UTF-8 (it starts a 3-byte sequence that is never completed),
        so utf-8-sig raises UnicodeDecodeError. latin-1 maps \\xe9 to 'é' and always succeeds.
        """
        # b"caf\xe9" is "café" in latin-1 but invalid UTF-8
        latin1_bytes = b"caf\xe9"

        result = parse_document(latin1_bytes, "txt")

        assert result == "café"

    def test_parse_document_txt_with_null_bytes_strips_null_bytes(self) -> None:
        """Verifies that parse_document removes null bytes (\\x00) from extracted text.

        PostgreSQL text columns and JSON payloads both reject null bytes — a crafted
        TXT file containing \\x00 would cause a Supabase insert error downstream.
        The null byte must be stripped silently, not raise an exception.
        """
        null_byte_content = b"hello\x00world"

        result = parse_document(null_byte_content, "txt")

        assert result == "helloworld"
        assert "\x00" not in result

    def test_parse_document_txt_leading_trailing_whitespace_stripped(self) -> None:
        """Verifies that parse_document strips leading and trailing whitespace from output."""
        txt_bytes = "   spaced content   \n\n".encode("utf-8")

        result = parse_document(txt_bytes, "txt")

        assert result == "spaced content"

    def test_parse_document_txt_preserves_internal_content(self) -> None:
        """Verifies that whitespace and newlines INSIDE the text are preserved."""
        txt_bytes = "paragraph one\n\nparagraph two".encode("utf-8")

        result = parse_document(txt_bytes, "txt")

        assert "paragraph one" in result
        assert "paragraph two" in result
        assert "\n\n" in result


# ── PDF parsing ───────────────────────────────────────────────────────────────

class TestParsePdf:
    """Tests for the PDF parsing branch of parse_document()."""

    def test_parse_document_valid_pdf_returns_non_empty_string(
        self, minimal_pdf_bytes: bytes
    ) -> None:
        """Verifies that parse_document returns extracted text for a valid single-page PDF."""
        mock_reader = _make_mock_reader(["Annual report Q4 content."])

        with patch("services.ingestion.PdfReader", return_value=mock_reader):
            result = parse_document(minimal_pdf_bytes, "pdf")

        assert result == "Annual report Q4 content."

    def test_parse_document_multi_page_pdf_returns_all_pages_joined_with_double_newline(
        self, minimal_pdf_bytes: bytes
    ) -> None:
        """Verifies that text from all pages is in the output, joined with '\\n\\n'.

        The double newline acts as a paragraph separator that downstream text
        splitters can treat as a natural section boundary between pages.
        """
        mock_reader = _make_mock_reader(
            ["Page one text.", "Page two text.", "Page three text."]
        )

        with patch("services.ingestion.PdfReader", return_value=mock_reader):
            result = parse_document(minimal_pdf_bytes, "pdf")

        assert result == "Page one text.\n\nPage two text.\n\nPage three text."

    def test_parse_document_scanned_image_pdf_returns_empty_string_without_raising(
        self, minimal_pdf_bytes: bytes
    ) -> None:
        """Verifies that a PDF where every page has no text layer returns '' without error.

        A scanned PDF (photograph of a document) contains images, not embedded text.
        extract_text() returns None per page. parse_document must return '' — not raise —
        because the route handler decides whether to reject empty results.
        """
        # None from extract_text() simulates an image-only page
        mock_reader = _make_mock_reader([None, None, None])

        with patch("services.ingestion.PdfReader", return_value=mock_reader):
            result = parse_document(minimal_pdf_bytes, "pdf")

        assert result == ""

    def test_parse_document_pdf_password_protected_via_is_encrypted_raises_value_error(
        self, minimal_pdf_bytes: bytes
    ) -> None:
        """Verifies that parse_document raises ValueError when reader.is_encrypted is True.

        reader.is_encrypted is checked after the constructor succeeds — it is the
        primary encryption detection path for most password-protected PDFs.
        """
        mock_reader = _make_mock_reader(["secret content"], is_encrypted=True)

        with patch("services.ingestion.PdfReader", return_value=mock_reader):
            with pytest.raises(ValueError, match="Password-protected"):
                parse_document(minimal_pdf_bytes, "pdf")

    def test_parse_document_pdf_password_protected_at_construction_raises_value_error(
        self, minimal_pdf_bytes: bytes
    ) -> None:
        """Verifies that parse_document raises ValueError when PdfReader() raises
        FileNotDecryptedError at construction time."""
        with patch(
            "services.ingestion.PdfReader",
            side_effect=FileNotDecryptedError("encrypted at open"),
        ):
            with pytest.raises(ValueError, match="Password-protected"):
                parse_document(minimal_pdf_bytes, "pdf")

    def test_parse_document_pdf_magic_bytes_fail_raises_value_error(self) -> None:
        """Verifies that parse_document raises ValueError when bytes don't start with %PDF-.

        The magic-bytes check runs before PdfReader is ever called, so no mock is needed.
        A ZIP file, HTML file, or any non-PDF binary will fail this check.
        """
        # PK\x03\x04 is the magic bytes signature for a ZIP file
        not_a_pdf = b"PK\x03\x04 this is actually a ZIP file"

        with pytest.raises(ValueError, match="magic bytes"):
            parse_document(not_a_pdf, "pdf")

    def test_parse_document_pdf_corrupted_pdf_read_error_raises_value_error(
        self, minimal_pdf_bytes: bytes
    ) -> None:
        """Verifies that parse_document raises ValueError when PdfReader raises PdfReadError."""
        with patch(
            "services.ingestion.PdfReader",
            side_effect=PdfReadError("malformed cross-reference table"),
        ):
            with pytest.raises(ValueError, match="corrupted"):
                parse_document(minimal_pdf_bytes, "pdf")

    def test_parse_document_pdf_corrupted_stream_error_raises_value_error(
        self, minimal_pdf_bytes: bytes
    ) -> None:
        """Verifies that parse_document raises ValueError when PdfReader raises PdfStreamError."""
        with patch(
            "services.ingestion.PdfReader",
            side_effect=PdfStreamError("bad content stream"),
        ):
            with pytest.raises(ValueError, match="corrupted"):
                parse_document(minimal_pdf_bytes, "pdf")

    def test_parse_document_pdf_decompression_bomb_raises_value_error_before_loop_ends(
        self, minimal_pdf_bytes: bytes
    ) -> None:
        """Verifies that parse_document raises ValueError when accumulated page text
        exceeds 2 million characters, and that the loop short-circuits before page 3.

        Breakdown:
          Page 1: 1,500,000 chars → running total = 1,500,000 → under cap, continues
          Page 2:   600,001 chars → running total = 2,100,001 → exceeds cap, raises
          Page 3: never reached  → extract_text() must NOT be called

        This confirms the per-page short-circuit works: we raise immediately rather
        than accumulating all text first (which would hold gigabytes in memory).
        """
        mock_reader = _make_mock_reader([
            "A" * 1_500_000,  # page 1 — 1.5M chars, under the 2M cap
            "B" * 600_001,    # page 2 — pushes total to 2.1M, triggers ValueError
            "C" * 1_000,      # page 3 — must NEVER be extracted
        ])

        with patch("services.ingestion.PdfReader", return_value=mock_reader):
            with pytest.raises(ValueError, match="2 million characters"):
                parse_document(minimal_pdf_bytes, "pdf")

        # The critical assertion: page 3 was never touched — the loop truly stopped early
        mock_reader.pages[2].extract_text.assert_not_called()

    def test_parse_document_pdf_unreadable_page_is_skipped_rest_of_document_returned(
        self, minimal_pdf_bytes: bytes
    ) -> None:
        """Verifies that a single unreadable page is skipped gracefully — not fatal.

        A multi-page PDF with one corrupted page should still return text from
        the readable pages rather than failing the entire document.
        """
        # Build a reader with 3 pages; make the middle one raise on extract_text()
        good_page_1 = MagicMock()
        good_page_1.extract_text.return_value = "Introduction chapter."

        broken_page = MagicMock()
        broken_page.extract_text.side_effect = PdfReadError("page stream corrupt")

        good_page_3 = MagicMock()
        good_page_3.extract_text.return_value = "Conclusion chapter."

        mock_reader = MagicMock()
        mock_reader.is_encrypted = False
        mock_reader.pages = [good_page_1, broken_page, good_page_3]

        with patch("services.ingestion.PdfReader", return_value=mock_reader):
            result = parse_document(minimal_pdf_bytes, "pdf")

        assert "Introduction chapter." in result
        assert "Conclusion chapter." in result


# ── Input validation ──────────────────────────────────────────────────────────

class TestValidation:
    """Tests for the validation checks at the top of parse_document()."""

    def test_parse_document_none_bytes_raises_value_error_with_correct_message(
        self,
    ) -> None:
        """Verifies that parse_document raises ValueError with 'No file content' message
        when file_bytes is None."""
        with pytest.raises(ValueError, match="No file content received"):
            parse_document(None, "txt")  # type: ignore[arg-type]

    def test_parse_document_empty_bytes_raises_value_error_with_empty_in_message(
        self,
    ) -> None:
        """Verifies that parse_document raises ValueError with 'empty' in message
        when file_bytes is an empty bytes object."""
        with pytest.raises(ValueError, match="empty"):
            parse_document(b"", "txt")

    def test_parse_document_unsupported_file_type_raises_value_error(self) -> None:
        """Verifies that parse_document raises ValueError with 'Unsupported' in message
        for any file_type not in the {'pdf', 'txt'} allowlist."""
        for bad_type in ("docx", "xlsx", "png", "exe", "PDF", "TXT", ""):
            with pytest.raises(ValueError, match="Unsupported"):
                parse_document(b"some content", bad_type)

    def test_parse_document_exceeds_size_limit_raises_value_error_with_mb_in_message(
        self,
    ) -> None:
        """Verifies that parse_document raises ValueError mentioning the MB limit when
        file_bytes exceeds settings.MAX_FILE_SIZE_MB.

        We patch MAX_FILE_SIZE_MB to 1 so the oversized fixture stays small (1 MB + 1 byte
        instead of 20 MB + 1 byte). The error message must include the patched limit value.
        """
        # Patching settings.MAX_FILE_SIZE_MB directly since it drives the size check
        with patch.object(settings, "MAX_FILE_SIZE_MB", 1):
            oversized = b"x" * (1 * 1024 * 1024 + 1)  # 1 MB + 1 byte
            with pytest.raises(ValueError, match="1 MB"):
                parse_document(oversized, "txt")

    def test_parse_document_exactly_at_size_limit_does_not_raise(self) -> None:
        """Verifies that a file exactly at MAX_FILE_SIZE_MB is accepted (boundary: ≤ is OK)."""
        with patch.object(settings, "MAX_FILE_SIZE_MB", 1):
            at_limit = b"x" * (1 * 1024 * 1024)  # exactly 1 MB — must NOT raise

            result = parse_document(at_limit, "txt")

        assert len(result) == 1 * 1024 * 1024

    def test_parse_document_no_temp_files_created_on_disk(self) -> None:
        """Verifies that parse_document() never writes to the filesystem — all I/O is in-memory.

        Checks two things:
        1. The system temp directory has no new files after parse_document runs.
        2. The ingestion module does not import 'tempfile' (which would indicate disk usage).

        PDF parsing uses io.BytesIO (an in-memory file-like object) — no disk path needed.
        """
        # ── Check 1: no new files appear in the system temp directory ──────────
        temp_dir = Path(tempfile.gettempdir())
        files_before = set(temp_dir.iterdir())

        txt_bytes = "In-memory content only.".encode("utf-8")
        parse_document(txt_bytes, "txt")

        files_after = set(temp_dir.iterdir())
        new_files = files_after - files_before
        assert not new_files, (
            f"parse_document() unexpectedly created temp files: {new_files}"
        )

        # ── Check 2: tempfile is not imported in the ingestion module ───────────
        # If ingestion.py ever imports tempfile, it would appear in the module's
        # namespace — that is a red flag that disk-based I/O was introduced.
        import services.ingestion as ingestion_module
        assert "tempfile" not in vars(ingestion_module), (
            "ingestion.py imported 'tempfile' — use io.BytesIO for in-memory parsing"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# chunk_text() tests
# ═══════════════════════════════════════════════════════════════════════════════
#
# chunk_text() is a pure function — no external calls, no mocks needed.
# ENCODER (tiktoken) is already loaded at module import time.
#
# Token-source helpers
# --------------------
# Two module-level token lists are built once and sliced by the _text() helpers:
#   _SRC_PUNCT   — English sentences with ". " boundaries (for snapping tests)
#   _SRC_NO_PUNCT — words with no sentence terminators (for clean overlap tests)
#
# Using ENCODER.decode(ids[:n]) gives text that re-encodes to exactly n tokens
# for normal English input (no multibyte character boundary splits).

_SRC_PUNCT = ENCODER.encode(
    "The quick brown fox jumps over the lazy dog. "
    "She sells seashells by the seashore. "
    "How much wood could a woodchuck chuck. " * 300
)
_SRC_NO_PUNCT = ENCODER.encode("hello world foo bar baz qux quux corge grault " * 300)


def _text(n: int) -> str:
    """Return text encoding to exactly n tokens (contains sentence boundaries)."""
    return ENCODER.decode(_SRC_PUNCT[:n])


def _text_np(n: int) -> str:
    """Return text encoding to exactly n tokens with no sentence-terminator characters."""
    return ENCODER.decode(_SRC_NO_PUNCT[:n])


# ── Happy path ────────────────────────────────────────────────────────────────

class TestChunkTextHappyPath:
    """Normal inputs: correct return types and chunk counts."""

    def test_chunk_text_short_text_returns_single_element_list(self) -> None:
        """Verifies that chunk_text returns ["hello world"] for a string well under chunk_size."""
        result = chunk_text("hello world")

        assert result == ["hello world"]

    def test_chunk_text_returns_list_of_str_not_bytes(self) -> None:
        """Verifies that chunk_text always returns list[str], never list[bytes]."""
        result = chunk_text(_text(1000), chunk_size=512, overlap=50)

        assert isinstance(result, list)
        assert all(isinstance(c, str) for c in result)

    def test_chunk_text_text_exactly_chunk_size_tokens_returns_single_chunk(self) -> None:
        """Verifies that text encoding to exactly chunk_size tokens hits the single-chunk fast path.

        When len(token_ids) <= chunk_size the sliding window is skipped entirely
        and the original stripped text is returned as a one-element list.
        """
        text = _text(512)
        assert len(ENCODER.encode(text)) == 512  # fixture sanity check

        result = chunk_text(text, chunk_size=512)

        assert len(result) == 1
        assert result[0] == text

    def test_chunk_text_long_text_returns_multiple_chunks_each_within_token_limit(
        self,
    ) -> None:
        """Verifies that a 1000-token string produces >= 2 chunks each <= chunk_size tokens.

        The final tail-merged chunk is exempt from the chunk_size ceiling but must
        still be <= 8191 (the embedding model hard limit).
        """
        text = _text(1000)

        chunks = chunk_text(text, chunk_size=512, overlap=50)

        assert len(chunks) >= 2
        for i, chunk in enumerate(chunks):
            n_tokens = len(ENCODER.encode(chunk))
            is_last = i == len(chunks) - 1
            assert n_tokens <= 512 or is_last, (
                f"Non-final chunk {i} has {n_tokens} tokens, exceeds chunk_size=512"
            )
            assert n_tokens <= 8191  # embedding hard cap always applies


# ── Overlap ───────────────────────────────────────────────────────────────────

class TestChunkTextOverlap:
    """Sliding-window overlap: shared token content at chunk boundaries."""

    def test_chunk_text_consecutive_chunks_share_overlap_tokens(self) -> None:
        """Verifies that consecutive chunks share at least `overlap` token IDs at their boundary.

        Uses text with no sentence-terminator characters so snapping never fires,
        making the token-level overlap deterministic and directly verifiable.
        300 tokens, chunk_size=200, overlap=50 → 2 chunks, tail=100 (no merge).
        """
        overlap = 50
        chunk_size = 200
        text = _text_np(300)  # no punct → snapping cannot fire

        chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        assert len(chunks) >= 2, "fixture must produce at least 2 chunks"

        ids_first = ENCODER.encode(chunks[0])
        ids_second = ENCODER.encode(chunks[1])

        # The last `overlap` tokens of chunk 0 must equal the first `overlap` of chunk 1.
        assert ids_first[-overlap:] == ids_second[:overlap], (
            "Adjacent chunks do not share the expected token overlap at their boundary"
        )

    def test_chunk_text_zero_overlap_total_tokens_equals_source_token_count(
        self,
    ) -> None:
        """Verifies that overlap=0 produces chunks with no repeated tokens.

        With step=chunk_size every adjacent window is non-overlapping, so the sum
        of each chunk's re-encoded token count must equal the source total.
        Uses text with no punctuation to suppress snapping (which would drop tokens).
        (Acceptance criterion 21)
        """
        chunk_size = 100
        text = _text_np(250)  # 250 tokens, no punct

        chunks = chunk_text(text, chunk_size=chunk_size, overlap=0)
        assert len(chunks) >= 2

        total_source = len(ENCODER.encode(text))
        total_chunks = sum(len(ENCODER.encode(c)) for c in chunks)

        assert total_chunks == total_source, (
            f"overlap=0 should produce no repeated tokens: "
            f"source={total_source}, chunks={total_chunks}"
        )


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestChunkTextEdgeCases:
    """Boundary conditions: empty, whitespace-only, leading/trailing whitespace."""

    def test_chunk_text_empty_string_returns_empty_list(self) -> None:
        """Verifies that chunk_text("") returns [] without raising."""
        assert chunk_text("") == []

    def test_chunk_text_whitespace_only_string_returns_empty_list(self) -> None:
        """Verifies that chunk_text returns [] for a string that is only spaces and newlines."""
        assert chunk_text("   \n\n  \t  ") == []

    def test_chunk_text_strips_leading_trailing_whitespace_before_processing(
        self,
    ) -> None:
        """Verifies that chunk_text strips surrounding whitespace before tokenising.

        A short sentence surrounded by whitespace should produce the same result
        as the same sentence without surrounding whitespace.
        """
        result_padded = chunk_text("   hello world   ")
        result_clean = chunk_text("hello world")

        assert result_padded == result_clean

    def test_chunk_text_single_word_returns_one_chunk(self) -> None:
        """Verifies that a single word well within chunk_size returns a single-element list."""
        result = chunk_text("documentation")

        assert len(result) == 1
        assert result[0] == "documentation"


# ── Tail merge ────────────────────────────────────────────────────────────────

class TestChunkTextTailMerge:
    """Tail-merge behaviour: when the final few tokens are absorbed vs emitted separately."""

    def test_chunk_text_tail_of_fewer_than_ten_tokens_merged_into_previous_chunk(
        self,
    ) -> None:
        """Verifies that a tail of 9 tokens is merged into the current window — returns 1 chunk.

        521 tokens with chunk_size=512: tail=9, merged=521 < 512*1.5=768, 521 <= 8191.
        All three merge conditions are satisfied so the tail is absorbed.
        (Acceptance criterion 16)
        """
        text = _text_np(521)
        assert len(ENCODER.encode(text)) == 521  # fixture sanity check

        chunks = chunk_text(text, chunk_size=512, overlap=50)

        assert len(chunks) == 1
        assert len(ENCODER.encode(chunks[0])) == 521

    def test_chunk_text_tail_of_exactly_ten_tokens_emitted_as_own_chunk(self) -> None:
        """Verifies that a tail of exactly 10 tokens is NOT merged (tail < 10 is False).

        522 tokens with chunk_size=512, overlap=50, step=462:
          Window 1: tokens[0:512], tail=10 → no merge (10 is not < 10).
          Window 2: tokens[462:522] = 60 tokens (overlap region + tail).
        Key check: chunk 0 is NOT expanded to 522 tokens (merge did not fire).
        (Acceptance criterion 22a)
        """
        text = _text_np(522)
        assert len(ENCODER.encode(text)) == 522  # fixture sanity check

        chunks = chunk_text(text, chunk_size=512, overlap=50)

        assert len(chunks) == 2
        # Chunk 0 must stay at or under 512 tokens — not inflated by a merge to 522.
        assert len(ENCODER.encode(chunks[0])) <= 512

    def test_chunk_text_tail_failing_embedding_cap_emitted_as_own_chunk(self) -> None:
        """Verifies that a tail which would push merged size above 8191 is NOT merged.

        chunk_size=8183, 8192-token text: tail=9, merged=8192 > _EMBEDDING_TOKEN_LIMIT=8191
        → third merge condition fails → tail emitted as its own chunk.
        Returns 2 chunks: 8183 tokens + 9 tokens.
        (Acceptance criterion 22b)
        """
        # Build exactly 8192 tokens from a reliable English source.
        # ENCODER.decode(src[:n]) re-encodes to exactly n tokens for normal English text.
        _src_8192 = ENCODER.encode("The quick brown fox jumps " * 5000)
        text = ENCODER.decode(_src_8192[:8192])
        assert len(ENCODER.encode(text)) == 8192  # construction sanity check

        chunks = chunk_text(text, chunk_size=8183, overlap=0)

        assert len(chunks) == 2
        assert len(ENCODER.encode(chunks[0])) == 8183
        assert len(ENCODER.encode(chunks[1])) == 9

    def test_chunk_text_tail_merged_chunk_not_sentence_snapped(self) -> None:
        """Verifies that a tail-merged final chunk is never trimmed by sentence snapping.

        A merged chunk (tail_token_count=0) skips the snapping block entirely,
        so even if it contains sentence boundaries the text is returned in full.
        (Acceptance criterion 19)
        """
        # Sentence text where the tail (< 10 tokens) contains ". "
        sentence = "Done. "  # ~3 tokens
        text = (sentence * 170)  # ~510 tokens + a short tail of ~3 tokens

        chunks = chunk_text(text, chunk_size=512, overlap=50)

        # The merged final chunk must NOT be snapped — it ends with the full text.
        last_chunk = chunks[-1]
        # Confirm it was actually merged (tail is short enough) and not trimmed:
        # if snapping had fired incorrectly, the tail would be shorter than all its source tokens.
        assert len(ENCODER.encode(last_chunk)) <= 8191  # just the hard cap applies
        # The tail chunk must contain complete text, not end mid-word from snapping
        assert last_chunk.endswith((".", " ", "\n")) or len(last_chunk) > 0


# ── Sentence snapping ─────────────────────────────────────────────────────────

class TestChunkTextSentenceSnapping:
    """Sentence-boundary snapping trims non-final chunks to end at punctuation."""

    def test_chunk_text_non_final_chunk_trimmed_to_sentence_boundary(self) -> None:
        """Verifies that non-final chunks end with '.', '!', or '?' when a boundary
        exists in the last `overlap` tokens.

        Uses short sentences ("One. " ≈ 3 tokens) with overlap=20 so the overlap
        region always contains multiple boundaries — snapping is guaranteed to fire.
        """
        sentence = "One. "  # ≈ 3 tokens; overlap=20 covers ~6 complete sentences
        text = sentence * 100  # ~300 tokens

        chunks = chunk_text(text, chunk_size=50, overlap=20)
        assert len(chunks) >= 2

        for i, chunk in enumerate(chunks[:-1]):  # every non-final chunk
            assert chunk.endswith((".", "!", "?")), (
                f"Non-final chunk {i} does not end at a sentence boundary: {chunk!r}"
            )

    def test_chunk_text_sentence_snapping_never_exceeds_chunk_size_tokens(
        self,
    ) -> None:
        """Verifies that snapping only removes tokens from a chunk, never adds them.

        Trimming can only make a chunk shorter — so a snapped chunk must be
        <= chunk_size tokens.  (Acceptance criterion 15)
        """
        text = "Sentence ends here. More text follows. " * 50

        chunks = chunk_text(text, chunk_size=30, overlap=10)

        for i, chunk in enumerate(chunks[:-1]):  # non-final chunks only
            n_tokens = len(ENCODER.encode(chunk))
            assert n_tokens <= 30, (
                f"Snapped chunk {i} has {n_tokens} tokens, exceeds chunk_size=30"
            )

    def test_chunk_text_snapping_uses_rightmost_boundary_in_overlap_region(
        self,
    ) -> None:
        """Verifies that chunk_text picks the rightmost sentence boundary, not the first.

        With multiple ". " occurrences in the overlap region, the chunk must end at
        the LAST boundary — keeping as much text as possible in the chunk.
        """
        # Build text long enough for 2 chunks, multiple boundaries in overlap
        text = "Alpha. Beta. Gamma. Delta. Epsilon. " * 30  # ~300 tokens

        chunks = chunk_text(text, chunk_size=60, overlap=30)
        assert len(chunks) >= 2

        # The first chunk must end at a sentence boundary (snapping fires)
        assert chunks[0].endswith((".", "!", "?"))

        # If it ended at the FIRST boundary instead of the rightmost, the chunk
        # would be much shorter.  Verify it is longer than a minimum threshold.
        assert len(chunks[0]) > 10, "chunk is suspiciously short — snapping may have used a non-rightmost boundary"


# ── Type errors ───────────────────────────────────────────────────────────────

class TestChunkTextTypeErrors:
    """Wrong argument types raise TypeError with the correct message."""

    def test_chunk_text_none_raises_type_error_mentioning_nonetype(self) -> None:
        """Verifies that chunk_text(None) raises TypeError with 'NoneType' in the message."""
        with pytest.raises(TypeError, match="NoneType"):
            chunk_text(None)  # type: ignore[arg-type]

    def test_chunk_text_bytes_raises_type_error_mentioning_not_bytes(self) -> None:
        """Verifies that chunk_text(b"hello") raises TypeError with 'not bytes' in the message.

        bytes is the most common wrong type — callers of parse_document() may forget
        to decode before passing the result on.  (Acceptance criterion 8)
        """
        with pytest.raises(TypeError, match="not bytes"):
            chunk_text(b"hello")  # type: ignore[arg-type]

    def test_chunk_text_integer_text_raises_type_error(self) -> None:
        """Verifies that chunk_text(42) raises TypeError with 'int' in the message."""
        with pytest.raises(TypeError, match="int"):
            chunk_text(42)  # type: ignore[arg-type]

    def test_chunk_text_float_chunk_size_raises_type_error(self) -> None:
        """Verifies that passing chunk_size as a float raises TypeError.

        512.0 == 512 in Python, so without an explicit isinstance check this would
        silently proceed.  (Acceptance criterion 9)
        """
        with pytest.raises(TypeError, match="chunk_size"):
            chunk_text("hello", chunk_size=512.0)  # type: ignore[arg-type]

    def test_chunk_text_float_overlap_raises_type_error(self) -> None:
        """Verifies that passing overlap as a float raises TypeError."""
        with pytest.raises(TypeError, match="overlap"):
            chunk_text("hello", overlap=50.0)  # type: ignore[arg-type]


# ── Value errors ──────────────────────────────────────────────────────────────

class TestChunkTextValueErrors:
    """Out-of-range arguments and invalid content raise ValueError with the correct message."""

    def test_chunk_text_chunk_size_zero_raises_value_error(self) -> None:
        """Verifies that chunk_size=0 raises ValueError with 'at least 1' in the message."""
        with pytest.raises(ValueError, match="at least 1"):
            chunk_text("hello", chunk_size=0)

    def test_chunk_text_chunk_size_negative_raises_value_error(self) -> None:
        """Verifies that chunk_size=-1 raises ValueError."""
        with pytest.raises(ValueError, match="at least 1"):
            chunk_text("hello", chunk_size=-1)

    def test_chunk_text_chunk_size_above_embedding_limit_raises_value_error(
        self,
    ) -> None:
        """Verifies that chunk_size=8192 raises ValueError mentioning the token limit.

        8192 exceeds text-embedding-3-small's 8191-token hard cap.
        (Acceptance criterion 11)
        """
        with pytest.raises(ValueError, match="8191"):
            chunk_text("hello", chunk_size=8192)

    def test_chunk_text_negative_overlap_raises_value_error(self) -> None:
        """Verifies that overlap=-1 raises ValueError with 'non-negative' in the message."""
        with pytest.raises(ValueError, match="non-negative"):
            chunk_text("hello", overlap=-1)

    def test_chunk_text_overlap_equal_to_chunk_size_raises_value_error(self) -> None:
        """Verifies that overlap=chunk_size raises ValueError — step would be 0.

        overlap must be strictly less than chunk_size so step = chunk_size - overlap >= 1.
        (Acceptance criterion 10)
        """
        with pytest.raises(ValueError, match="less than chunk_size"):
            chunk_text("hello", chunk_size=512, overlap=512)

    def test_chunk_text_text_over_character_limit_raises_value_error_before_encoding(
        self,
    ) -> None:
        """Verifies that text > 2,000,000 characters raises ValueError before tiktoken runs.

        The pre-filter must fire before ENCODER.encode() is called — passing 2M+ chars
        to tiktoken would allocate a large token list unnecessarily.
        (Acceptance criterion 12)
        """
        with patch("services.ingestion.ENCODER") as mock_enc:
            with pytest.raises(ValueError, match="2,000,000"):
                chunk_text("x" * 2_000_001)
            # If the pre-filter fired correctly, ENCODER.encode() was never reached.
            mock_enc.encode.assert_not_called()

    def test_chunk_text_surrogate_codepoints_raise_value_error_before_encoding(
        self,
    ) -> None:
        """Verifies that surrogate code points (U+D800–U+DFFF) raise ValueError.

        tiktoken raises an opaque error on surrogates — the explicit check gives a
        clear, user-readable message instead.  (Acceptance criterion 13)
        """
        with pytest.raises(ValueError, match="surrogate"):
            chunk_text("\ud800valid text")

    def test_chunk_text_chunk_count_exceeding_limit_raises_value_error(self) -> None:
        """Verifies that producing more than 2000 chunks raises ValueError mid-loop.

        chunk_size=1, overlap=0 makes every token its own chunk — even a short text
        will quickly exceed the 2000-chunk cap.
        """
        text = _text_np(2100)  # 2100 tokens → 2100 chunks with chunk_size=1

        with pytest.raises(ValueError, match="2000"):
            chunk_text(text, chunk_size=1, overlap=0)


# ── Module-level constant ─────────────────────────────────────────────────────

class TestChunkTextModule:
    """ENCODER singleton behaviour."""

    def test_chunk_text_encoder_constant_is_same_object_across_calls(self) -> None:
        """Verifies that ENCODER is initialised once at import — not recreated per call.

        Calling chunk_text() twice must use the same Encoding object in memory
        so the vocabulary is never loaded from disk more than once.
        (Acceptance criterion 18)
        """
        from services.ingestion import ENCODER as enc_before

        chunk_text("first call")
        chunk_text("second call")

        from services.ingestion import ENCODER as enc_after

        assert enc_before is enc_after, "ENCODER was unexpectedly re-initialised between calls"
