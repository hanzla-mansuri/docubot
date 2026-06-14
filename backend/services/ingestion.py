# services/ingestion.py — first stage of DocuBot's RAG ingestion pipeline.
# Responsibility: receive raw file bytes, extract human-readable plain text, return a string.
# What it does NOT do: chunk, embed, or write to the database — those are later stages.
#
# IMPORTANT — this module is synchronous (plain def, no async).
# The FastAPI route handler must call parse_document() via a thread pool executor:
#   text = await asyncio.run_in_executor(None, parse_document, file_bytes, file_type)
# This keeps the async event loop free to serve other requests while parsing runs.

import io
import logging

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
        raise ValueError(
            f"Unsupported file type: {file_type!r}. Accepted: pdf, txt."
        )

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
