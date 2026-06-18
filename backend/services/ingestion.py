# services/ingestion.py — first two stages of DocuBot's RAG ingestion pipeline.
# Responsibility: (1) receive raw file bytes and extract human-readable plain text;
#                 (2) split that text into overlapping token-bounded chunks for embedding.
# What it does NOT do: embed chunks or write to the database — those are later stages.
#
# IMPORTANT — this module is synchronous (plain def, no async).
# The FastAPI route handler must call these functions via a thread pool:
#   text   = await asyncio.run_in_executor(None, parse_document, file_bytes, file_type)
#   chunks = await asyncio.to_thread(chunk_text, text)
# This keeps the async event loop free while CPU-bound parsing and encoding run.

import io
import logging

import tiktoken

from PyPDF2 import PdfReader
from PyPDF2.errors import FileNotDecryptedError, PdfReadError, PdfStreamError

from config import settings

logger = logging.getLogger(__name__)

# Hard ceiling on extracted text length — protects against PDF decompression bombs.
# A crafted PDF can store megabytes of repeated text in a compressed stream;
# the input size limit alone cannot protect against this because we can't know
# the decompressed size until after extraction. This check catches it post-extraction.
_MAX_EXTRACTED_CHARS = 2_000_000

# Explicit allowlist — never derive accepted types from user-supplied strings alone.
_ALLOWED_FILE_TYPES = frozenset({"pdf", "txt"})

# Every valid PDF file starts with these five ASCII bytes ("magic bytes").
# Verifying this rejects files that are named .pdf but contain HTML, ZIP, etc.
_PDF_MAGIC_BYTES = b"%PDF-"

# Initialised once at import time so every call to chunk_text() shares the same
# encoder object instead of reloading the vocabulary from disk on each call.
# The try/except converts any tiktoken load failure into a clear RuntimeError that
# surfaces at startup rather than silently at the first upload request.
try:
    ENCODER = tiktoken.get_encoding("cl100k_base")
except Exception as exc:
    raise RuntimeError(f"Failed to load tiktoken encoder cl100k_base: {exc}") from exc

# text-embedding-3-small hard token limit per API call.
# Tail-merged chunks must never exceed this even if the 1.5× formula permits it.
_EMBEDDING_TOKEN_LIMIT = 8_191

# Maximum chunks produced from a single document.
# Prevents adversarial inputs (tiny chunk_size) from flooding Supabase with rows.
_MAX_CHUNK_COUNT = 2_000

# Latin-script sentence terminators used by sentence-boundary snapping.
# Defined at module level so the tuple is not reallocated on every loop iteration.
_SNAP_PATTERNS = (". ", "! ", "? ", ".\n", "!\n", "?\n")


def parse_document(file_bytes: bytes, file_type: str) -> str:
    """
    Extract plain text from the raw bytes of a PDF or TXT file.

    Validation checks run in a fixed order (None → empty → size → type → magic bytes)
    so that error messages are always specific and predictable.
    After extraction, a character cap guards against decompression bombs.

    This is a plain def — NOT async. The caller must offload it to a thread pool:
        await asyncio.run_in_executor(None, parse_document, file_bytes, file_type)

    Args:
        file_bytes: Raw binary content of the uploaded file.
        file_type:  Lowercase file type — must be "pdf" or "txt".

    Returns:
        Plain-text string, stripped of leading/trailing whitespace.
        Returns "" if extraction succeeds but yields no text (e.g. scanned-image PDF).

    Raises:
        ValueError: Any validation failure or parsing error.
                    Message strings are safe to include in HTTP 422 response bodies.
    """
    # ── Validation — order matches the approved spec ──────────────────────────

    if file_bytes is None:
        raise ValueError("No file content received.")

    if len(file_bytes) == 0:
        raise ValueError("File is empty — no content to parse.")

    # Read the size limit from settings so it can be changed in .env without
    # touching this file. Default is 20 MB (MAX_FILE_SIZE_MB=20).
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise ValueError(
            f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB} MB."
        )

    if file_type not in _ALLOWED_FILE_TYPES:
        raise ValueError(f"Unsupported file type: {file_type!r}. Accepted: pdf, txt.")

    # ── Dispatch to type-specific helpers ─────────────────────────────────────

    logger.info("Parsing %s file (%d bytes).", file_type, len(file_bytes))

    if file_type == "pdf":
        extracted = _parse_pdf(file_bytes)
    else:
        extracted = _parse_txt(file_bytes)

    # ── Output size cap — checked after extraction ────────────────────────────

    # Must come AFTER parsing: we cannot know the decompressed text size in advance.
    if len(extracted) > _MAX_EXTRACTED_CHARS:
        raise ValueError(
            "Document contains too much text to process — maximum 2 million characters."
        )

    # Remove null bytes — PostgreSQL text columns and JSON payloads reject them.
    # A crafted TXT file or a corrupted PDF can contain \x00 bytes in extracted text.
    extracted = extracted.replace("\x00", "")
    return extracted.strip()


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 50,
) -> list[str]:
    """
    Split a plain-text string into an ordered list of overlapping token chunks.

    Uses OpenAI's cl100k_base tiktoken encoder (the same vocabulary used by
    text-embedding-3-small) so that chunk sizes are measured in the same token
    units that the embedding API will consume.  Overlapping windows (50 tokens
    by default) ensure that a sentence split across a chunk boundary still
    appears in full in at least one chunk, preserving semantic context for RAG
    retrieval.

    This function is synchronous — the caller must offload it to a thread pool:
        chunks = await asyncio.to_thread(chunk_text, text)

    When overlap=0 and sentence snapping trims a chunk, the trimmed tokens appear
    in neither the current chunk nor the next window — they are permanently
    discarded.  Callers that need lossless output should set overlap > 0.

    Args:
        text:       Plain-text string produced by parse_document(). Must be a str,
                    ≤ 2,000,000 characters, and free of Unicode surrogate code points.
        chunk_size: Maximum tokens per chunk (1–8191 inclusive). Default 512.
        overlap:    Tokens shared between consecutive chunks (0 to chunk_size-1).
                    Default 50.

    Returns:
        Ordered list[str] of decoded text chunks.  Returns [] for empty or
        whitespace-only input.  Each chunk is ≤ chunk_size tokens when
        re-encoded, except for a possible tail-merged final chunk which is
        always ≤ 8,191 tokens.

    Raises:
        TypeError:  text is not a str, or chunk_size/overlap are not ints.
        ValueError: Any range violation, character limit exceeded, surrogate
                    code points detected, or chunk count exceeds 2,000.
    """
    # ── Type validation ────────────────────────────────────────────────────────

    if not isinstance(text, str):
        # bytes is the most common wrong type (callers forget to decode first).
        if isinstance(text, bytes):
            raise TypeError("text must be a str, not bytes — decode it first")
        raise TypeError(f"text must be a str, got {type(text).__name__}")

    # isinstance(True, int) is True in Python, so booleans would silently pass
    # as 0 or 1; float is the more common mistake the spec calls out explicitly.
    if not isinstance(chunk_size, int):
        raise TypeError(f"chunk_size must be an int, got {type(chunk_size).__name__}")

    if not isinstance(overlap, int):
        raise TypeError(f"overlap must be an int, got {type(overlap).__name__}")

    # ── Range validation ───────────────────────────────────────────────────────

    if chunk_size <= 0:
        raise ValueError("chunk_size must be at least 1")

    if chunk_size > _EMBEDDING_TOKEN_LIMIT:
        raise ValueError(
            f"chunk_size must not exceed {_EMBEDDING_TOKEN_LIMIT}"
            " (text-embedding-3-small token limit)"
        )

    if overlap < 0:
        raise ValueError("overlap must be non-negative")

    if overlap >= chunk_size:
        raise ValueError("overlap must be less than chunk_size")

    # ── Step 2: strip ─────────────────────────────────────────────────────────

    text = text.strip()

    # ── Step 3: early-exit on empty input ─────────────────────────────────────

    if not text:
        return []

    # ── Step 4: character pre-filter (before any encoding) ────────────────────

    # Encoding a 10 M-char string allocates a large token list even if we discard
    # it immediately — the pre-filter prevents that allocation entirely.
    if len(text) > 2_000_000:
        raise ValueError("text exceeds 2,000,000 character pre-filter limit")

    # ── Step 4a: surrogate check (before encoding) ─────────────────────────────

    # tiktoken raises an opaque error on surrogate code points (\ud800–\udfff).
    # Detecting them here gives a clear ValueError instead of a cryptic crash.
    # any() short-circuits on the first surrogate found, avoiding a full scan for
    # the common case where the text is invalid from the very first character.
    if any("\ud800" <= c <= "\udfff" for c in text):
        raise ValueError(
            "text contains invalid Unicode surrogates and cannot be encoded"
        )

    # ── Step 6: encode ────────────────────────────────────────────────────────

    token_ids: list[int] = ENCODER.encode(text)

    # ── Step 7: empty token list ──────────────────────────────────────────────

    if not token_ids:
        return []

    # ── Step 8: single-chunk fast path ────────────────────────────────────────

    # Entire document fits in one chunk — no windowing needed.
    if len(token_ids) <= chunk_size:
        return [text]

    # ── Steps 9–12: sliding window ────────────────────────────────────────────

    # step is how far the window advances each iteration.
    # With overlap=50 and chunk_size=512, step=462 — the next window starts 462
    # tokens after the current one, giving 50 tokens of shared context.
    step = chunk_size - overlap

    start = 0
    chunks: list[str] = []

    while start < len(token_ids):
        end = min(start + chunk_size, len(token_ids))
        window = token_ids[start:end]
        tail_token_count = len(token_ids) - end

        # ── Tail merge ────────────────────────────────────────────────────────
        # If the remaining tokens after this window are too few to form a useful
        # chunk on their own, absorb them into the current window.
        # Three conditions must ALL be true to merge:
        #   1. tail is fewer than 10 tokens (too short to stand alone)
        #   2. merged size stays under 1.5× chunk_size (avoids oversized chunks)
        #   3. merged size stays at or below the embedding model's hard token cap
        if tail_token_count > 0:
            merged_size = len(window) + tail_token_count
            if (
                tail_token_count < 10
                and merged_size < chunk_size * 1.5
                and merged_size <= _EMBEDDING_TOKEN_LIMIT
            ):
                end = len(token_ids)  # extend window to consume all tokens
                window = token_ids[start:end]
                tail_token_count = 0  # signals "this is now the final chunk"

        # Decode the token IDs back to a human-readable string.
        decoded: str = ENCODER.decode(window)

        # An empty decoded string (rare edge case with special tokens) contributes
        # nothing useful — skip it rather than storing an empty database row.
        if decoded:
            # ── Sentence-boundary snapping ────────────────────────────────────
            # Only snap when this is NOT the final chunk and was NOT tail-merged.
            # Snapping on the final chunk would silently discard tokens.
            if tail_token_count > 0:
                # Derive the search region: the last `overlap` tokens' worth of text.
                # Searching only the tail is an optimisation — boundaries near the
                # start of a chunk are too far back to be useful cut points.
                if overlap == 0:
                    # window[-0:] == window[0:] (the full window) — not what we want.
                    # With overlap=0 there is no shared region, so skip snapping.
                    tail_text = ""
                else:
                    # Intermediate windows (tail_token_count > 0) always contain
                    # exactly chunk_size tokens; validation enforces overlap < chunk_size,
                    # so len(window) >= overlap is always true here. Decode only the
                    # last `overlap` tokens to get the sentence-boundary search region.
                    tail_text = ENCODER.decode(window[-overlap:])

                if tail_text:
                    # Search for Latin-script sentence terminators followed by
                    # whitespace.  rfind() returns the position of the pattern's
                    # first character (the punctuation), or -1 if absent.
                    positions = [
                        pos
                        for pat in _SNAP_PATTERNS
                        if (pos := tail_text.rfind(pat)) >= 0
                    ]

                    if positions:
                        # Pick the rightmost boundary so we keep as much text as
                        # possible in this chunk.
                        rfind_result = max(positions)

                        # Map the position in tail_text back to the full decoded string.
                        # +1 advances past the punctuation char itself (.!?) so the
                        # chunk ends with the punctuation, excluding the space/newline.
                        trim_pos = len(decoded) - len(tail_text) + rfind_result + 1
                        decoded = decoded[:trim_pos]

            chunks.append(decoded)

            # Guard against adversarial inputs (e.g. chunk_size=1) that would
            # flood Supabase. Check after append so the error count is 1-indexed.
            if len(chunks) > _MAX_CHUNK_COUNT:
                raise ValueError(
                    f"document produces too many chunks — exceeds {_MAX_CHUNK_COUNT}"
                    " chunk limit"
                )

        # Advance the window by `step` tokens regardless of any text trimming.
        # The token pointer is always aligned to token boundaries; text-level
        # trimming only affects the decoded string that gets stored, not the
        # position from which the next window starts.
        start += step

        # If we just processed the final token, stop.
        if end == len(token_ids):
            break

    logger.debug(
        "chunk_text produced %d chunks from %d tokens (chunk_size=%d, overlap=%d).",
        len(chunks),
        len(token_ids),
        chunk_size,
        overlap,
    )

    return chunks


def _parse_pdf(file_bytes: bytes) -> str:
    """
    Extract text from PDF bytes using PyPDF2.

    Only called by parse_document() after all input validation has passed.
    Pages are joined with double newlines so downstream chunkers can treat
    blank lines as natural split boundaries between pages.

    Args:
        file_bytes: Validated raw bytes of a PDF file.

    Returns:
        All extracted page text joined with "\\n\\n". Returns "" if every page
        contains only images with no embedded text layer.

    Raises:
        ValueError: If the file fails the magic-bytes check, is encrypted,
                    or is too corrupted to open. Message is safe for HTTP responses.
    """
    # Magic-bytes guard: rejects files that aren't actually PDFs before handing
    # them to PdfReader, which could behave unpredictably on non-PDF binary data.
    if file_bytes[:5] != _PDF_MAGIC_BYTES:
        raise ValueError(
            "File does not appear to be a valid PDF — magic bytes check failed."
        )

    # Context manager ensures the in-memory buffer is released as soon as we
    # finish reading — halves peak memory usage compared to a bare assignment.
    # BytesIO wraps the bytes in a file-like object with .read()/.seek() so
    # PdfReader can navigate the PDF structure without writing to disk.
    with io.BytesIO(file_bytes) as pdf_buffer:
        try:
            reader = PdfReader(pdf_buffer)
        except FileNotDecryptedError as e:
            raise ValueError("Password-protected PDFs are not supported.") from e
        except (PdfReadError, PdfStreamError) as e:
            raise ValueError(
                "Could not read PDF — file may be corrupted or not a valid PDF."
            ) from e

        # reader.is_encrypted is True even before you access any pages.
        # Checking here gives a clean error rather than letting FileNotDecryptedError
        # surface from deep inside the page iteration loop below.
        if reader.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported.")

        logger.info("PDF opened successfully — %d pages.", len(reader.pages))

        page_texts: list[str] = []
        total_chars = 0  # running character count — checked after each page
        for page_num, page in enumerate(reader.pages):
            try:
                # extract_text() returns None for pages with no text layer (image-only).
                # "or ''" converts None to an empty string so the rest is uniform.
                text = page.extract_text() or ""
                if text:
                    page_texts.append(text)
                    total_chars += len(text)
                    # Short-circuit: raise as soon as we exceed the cap rather than
                    # after the full loop. This bounds both time and memory for
                    # decompression-bomb PDFs without waiting for all pages to extract.
                    if total_chars > _MAX_EXTRACTED_CHARS:
                        raise ValueError(
                            "Document contains too much text to process"
                            " — maximum 2 million characters."
                        )
            except (PdfReadError, PdfStreamError, FileNotDecryptedError) as e:
                # A single unreadable page should not fail the entire document.
                # Log the page number for debugging and continue with remaining pages.
                logger.warning(
                    "Skipping page %d — could not extract text: %s",
                    page_num,
                    type(e).__name__,
                )

        # "\n\n" between pages creates a blank-line separator that LangChain's
        # text splitters can treat as a natural paragraph/section boundary.
        return "\n\n".join(page_texts)


def _parse_txt(file_bytes: bytes) -> str:
    """
    Decode plain-text file bytes to a string.

    Tries UTF-8 with BOM stripping first (covers modern files and Windows Notepad output),
    then falls back to latin-1 which is guaranteed to succeed for any byte sequence.

    Args:
        file_bytes: Validated raw bytes of a text file.

    Returns:
        Decoded string. This function never raises — latin-1 is an infallible fallback
        because it maps every byte value 0x00–0xFF to a Unicode code point.
    """
    try:
        # "utf-8-sig" decodes UTF-8 AND silently strips a leading BOM (\xef\xbb\xbf)
        # if one is present. Using plain "utf-8" would leave the BOM as a garbage
        # character at the start of the string, corrupting the first chunk.
        return file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        # latin-1 (ISO-8859-1) maps every byte to a code point — it cannot raise
        # UnicodeDecodeError. It is the safe last resort for legacy Windows files
        # saved in encodings like cp1252 (which is a superset of latin-1).
        logger.debug("UTF-8 decode failed — falling back to latin-1.")
        return file_bytes.decode("latin-1")
