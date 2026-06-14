# tests/test_ingestion.py — tests for parse_document() in services/ingestion.py.
# Covers the first stage of the RAG pipeline: raw bytes → plain text string.
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
from services.ingestion import parse_document


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
