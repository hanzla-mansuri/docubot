# services/database.py — fourth stage of DocuBot's RAG ingestion pipeline.
# Responsibility: persist a parsed, chunked, and embedded document into Supabase.
# Provides three public names used by the POST /documents/upload route:
#   store_document()     — inserts a document row with status='processing'
#   store_chunks()       — batch-inserts chunk rows then calls the finalize_document RPC
#   _cleanup_document()  — sets status='failed' if the pipeline errors after store_document()
#
# All three functions are synchronous (plain def, no async).
# The FastAPI route handler must offload them to a thread pool:
#   doc_id = await asyncio.to_thread(store_document, filename, size, mime_type, db)
#
# MVP limitation (documented, not a bug):
# Supabase PostgREST does not wrap multiple Python calls in a single DB transaction.
# If batch chunk inserts partially succeed before an error, the successfully inserted
# chunk rows remain in the database. _cleanup_document() marks the document 'failed'
# so it is not treated as complete, but orphaned chunk rows are not deleted.
# A background cleanup job is a post-MVP concern.

import logging
import re
import uuid
from datetime import datetime, timezone

import numpy as np
from supabase import Client

from config import settings

logger = logging.getLogger(__name__)

# Allowlist for mime_type — checked before any DB call.
# A frozenset is O(1) for membership checks and cannot be mutated by accident.
_ALLOWED_MIME_TYPES = frozenset({"application/pdf", "text/plain"})

# Filename length ceiling — mirrors the documents table column constraint.
_MAX_FILENAME_LENGTH = 255

# S-02: allowlist regex for filenames — rejects path separators and null bytes.
# ^ and $ anchor to the full string; [^\x00/\\] means "no null byte, no /, no \".
# This is defense-in-depth — the route handler must also sanitize upstream.
_SAFE_FILENAME_RE = re.compile(r"^[^\x00/\\]+$")

# Expected vector dimension for text-embedding-3-small.
# Stored as a constant so a model change is one edit, not a search-and-replace.
_EXPECTED_EMBEDDING_DIMS = 1536

# Maximum rows per Supabase insert call.
# Keeps HTTP payloads small and matches the embed_texts() batch cap.
_CHUNK_INSERT_BATCH_SIZE = 100


def _validate_filename(filename: str) -> None:
    """
    Reject filenames that contain path traversal sequences or dangerous characters.

    Defense-in-depth: the route handler must sanitize upstream, but this function
    re-validates so that a missed sanitization step cannot store harmful filenames.

    Args:
        filename: The filename string to validate.

    Raises:
        ValueError: If the filename contains '..', null bytes, '/', or '\'.
    """
    # '..' anywhere in the name enables directory traversal when the filename is
    # later used to construct a path (even if not in this module today).
    if ".." in filename:
        raise ValueError("filename must not contain '..'")

    # _SAFE_FILENAME_RE rejects null bytes (\x00), forward slash (/), and backslash (\).
    # Null bytes can truncate strings in C-based code; slashes signal path components.
    if not _SAFE_FILENAME_RE.match(filename):
        raise ValueError(
            "filename contains invalid characters (null bytes or path separators)"
        )


class DatabaseError(Exception):
    """Raised when any Supabase database operation fails.

    Separates database failures from Python logic errors (ValueError, TypeError)
    so the route handler can map each exception type to the right HTTP status code:
      ValueError / TypeError → HTTP 422 (bad input)
      DatabaseError          → HTTP 500 (internal failure)
    """


def store_document(
    filename: str,
    file_size: int,
    mime_type: str,
    db: Client,
) -> str:
    """
    Insert a new document record into the documents table with status='processing'.

    Validates all inputs before touching the database so that bad data is caught
    with a clear ValueError rather than a cryptic Supabase constraint error.
    The 'processing' status signals that the ingestion pipeline is in progress —
    store_chunks() will update it to 'ready' once all chunks are stored.

    Args:
        filename:  Sanitised original filename; max 255 chars, no path separators.
        file_size: Byte count of the uploaded file. Must be a plain int, > 0,
                   and ≤ MAX_FILE_SIZE_MB × 1024 × 1024 (default 20 MB).
        mime_type: Must be exactly 'application/pdf' or 'text/plain'.
        db:        Supabase client; injected by the route handler.

    Returns:
        document_id (str): UUID string of the newly inserted row.

    Raises:
        ValueError:     Any input validation failure. Safe to include in HTTP 422 body.
        DatabaseError:  Supabase insert failed or returned an unexpected response.
    """
    # ── Input validation ──────────────────────────────────────────────────────

    # isinstance(True, int) is True in Python — booleans must be explicitly rejected
    # because file_size=True (== 1) would silently pass the range check.
    if not isinstance(file_size, int) or isinstance(file_size, bool):
        raise ValueError(
            f"file_size must be an int, got {type(file_size).__name__}"
        )

    if len(filename) > _MAX_FILENAME_LENGTH:
        raise ValueError(
            f"filename exceeds {_MAX_FILENAME_LENGTH} characters"
        )

    # S-02: defense-in-depth character check (path traversal, null bytes, separators).
    _validate_filename(filename)

    # Read the ceiling from settings so changing MAX_FILE_SIZE_MB in .env
    # takes effect here without touching this file.
    max_file_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size <= 0 or file_size > max_file_size_bytes:
        raise ValueError(
            f"file_size out of allowed range "
            f"(must be 1 to {max_file_size_bytes} bytes)"
        )

    if mime_type not in _ALLOWED_MIME_TYPES:
        raise ValueError(f"unsupported mime_type: {mime_type!r}")

    # ── Build insert payload ───────────────────────────────────────────────────

    # datetime.now(timezone.utc) produces a timezone-aware datetime.
    # .isoformat() formats it as '2026-06-21T10:30:00+00:00' — Supabase's
    # TIMESTAMPTZ column accepts this format and stores it correctly.
    # Never use datetime.utcnow() — it returns a naive datetime (no tzinfo),
    # which can cause silent timezone bugs in multi-region deployments.
    created_at = datetime.now(timezone.utc).isoformat()

    payload = {
        "filename": filename,
        "file_size": file_size,
        "mime_type": mime_type,
        "status": "processing",
        "created_at": created_at,
    }

    # ── Insert ─────────────────────────────────────────────────────────────────

    try:
        result = db.table("documents").insert(payload).execute()
    except Exception as exc:
        # Log the exception type only — never log the payload (may contain filename PII).
        logger.error(
            "store_document: Supabase insert raised %s", type(exc).__name__
        )
        raise DatabaseError("Failed to insert document record") from exc

    # supabase-py returns result.error for constraint violations (e.g. duplicate filename)
    # instead of raising an exception — we must check it explicitly.
    if getattr(result, "error", None) is not None:
        # S-01: log the raw Supabase error server-side only — never put it in the
        # DatabaseError message, which could be forwarded to an HTTP response body.
        error_msg = str(result.error)
        logger.error("store_document: Supabase returned error: %s", error_msg)
        # Detect the unique-constraint message to give a helpful error to the caller.
        if "unique" in error_msg.lower() or "duplicate" in error_msg.lower():
            raise DatabaseError("document with this filename already exists")
        raise DatabaseError("store_document: database operation failed")

    # A successful insert with no error should always return the inserted row.
    if not result.data:
        raise DatabaseError(
            "store_document: unexpected empty response from database"
        )

    # result.data is a list of inserted rows — we inserted one, so index 0 is our row.
    # KeyError means the schema doesn't have an 'id' column where expected;
    # IndexError means data was empty despite passing the earlier check (race condition).
    # Both are DB-layer failures, so we raise DatabaseError rather than letting them
    # propagate as bare KeyError/IndexError which the route handler wouldn't catch.
    try:
        document_id: str = result.data[0]["id"]
    except (KeyError, IndexError) as exc:
        raise DatabaseError(
            "store_document: database response missing expected 'id' field"
        ) from exc

    logger.info(
        "store_document: inserted document_id=%s status='processing'.",
        document_id,
    )
    return document_id


def store_chunks(
    document_id: str,
    chunks: list[str],
    embeddings: list[list[float]],
    db: Client,
) -> None:
    """
    Batch-insert chunk rows into the chunks table and finalise the document record.

    Inserts rows in batches of up to 100 (matching the embed_texts() batch size)
    to avoid hitting Supabase's HTTP payload limits. After all batches succeed,
    calls the finalize_document RPC which atomically updates the document's
    status to 'ready' and sets chunk_count — both in one DB transaction.

    If a batch insert fails mid-way, chunk rows from earlier batches are NOT
    rolled back (no cross-call transaction in PostgREST). The route handler must
    call _cleanup_document() before returning HTTP 500. See module docstring.

    Args:
        document_id: UUID string of the document row created by store_document().
                     Validated with uuid.UUID() before any DB call.
        chunks:      Non-empty list of raw chunk text strings. Must match embeddings length.
        embeddings:  List of 1536-float vectors, one per chunk. Values are float64
                     Python floats — this function casts each to float32 for pgvector.
        db:          Supabase client; injected by the route handler.

    Returns:
        None on success.

    Raises:
        ValueError:     Any input validation failure (empty list, length mismatch, bad UUID,
                        wrong embedding dimension).
        DatabaseError:  Any Supabase insert or RPC failure.
    """
    # ── Input validation ───────────────────────────────────────────────────────

    # uuid.UUID() raises ValueError for any non-UUID string.
    # Catching and re-raising gives a clearer message than the raw UUID error.
    try:
        uuid.UUID(document_id)
    except ValueError:
        raise ValueError(f"document_id is not a valid UUID: {document_id!r}")

    if not chunks:
        raise ValueError("chunks list must not be empty")

    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks and embeddings length mismatch: "
            f"{len(chunks)} chunks vs {len(embeddings)} embeddings"
        )

    # Check every embedding dimension upfront so we fail fast before any DB call.
    for i, emb in enumerate(embeddings):
        if len(emb) != _EXPECTED_EMBEDDING_DIMS:
            raise ValueError(
                f"embedding[{i}] has {len(emb)} dimensions, "
                f"expected {_EXPECTED_EMBEDDING_DIMS}"
            )

    # ── Build row payloads ─────────────────────────────────────────────────────

    rows = []
    for chunk_index, (text, embedding) in enumerate(zip(chunks, embeddings)):
        # pgvector stores vectors as 32-bit floats (float4).
        # Python's default float is 64-bit — inserting float64 would be rejected
        # or silently truncated. numpy converts the whole list in one call.
        float32_vector = np.array(embedding, dtype=np.float32).tolist()

        rows.append({
            "document_id": document_id,
            # chunk_index preserves insertion order so the document can be
            # reconstructed in page order if needed for debugging.
            "chunk_index": chunk_index,
            "text": text,
            # Never log 'text' — it may contain PII from uploaded documents.
            "embedding": float32_vector,
        })

    # ── Batch insert ───────────────────────────────────────────────────────────

    # range(0, total, 100) produces start indices: 0, 100, 200, ...
    # Each slice is at most 100 rows; the last slice may be smaller.
    for batch_start in range(0, len(rows), _CHUNK_INSERT_BATCH_SIZE):
        batch = rows[batch_start: batch_start + _CHUNK_INSERT_BATCH_SIZE]

        try:
            result = db.table("chunks").insert(batch).execute()
        except Exception as exc:
            logger.error(
                "store_chunks: Supabase insert raised %s for batch [%d:%d] "
                "of document %s",
                type(exc).__name__,
                batch_start,
                batch_start + len(batch),
                document_id,
            )
            raise DatabaseError(
                f"Failed to insert chunk batch "
                f"[{batch_start}:{batch_start + len(batch)}]"
            ) from exc

        if getattr(result, "error", None) is not None:
            # S-01: log detail server-side; raise generic message safe for any consumer.
            logger.error(
                "store_chunks: Supabase returned error on batch [%d:%d]: %s",
                batch_start,
                batch_start + len(batch),
                result.error,
            )
            raise DatabaseError(
                f"store_chunks: database operation failed on batch [{batch_start}]"
            )

        if not result.data:
            raise DatabaseError(
                f"store_chunks: unexpected empty response for batch [{batch_start}]"
            )

    # ── Finalise via RPC (atomic) ──────────────────────────────────────────────

    # The finalize_document stored procedure runs as a single DB transaction,
    # so status and chunk_count are always updated together or not at all.
    # This prevents a partial update where status='ready' but chunk_count=0.
    try:
        rpc_result = db.rpc(
            "finalize_document",
            {"p_document_id": document_id, "p_chunk_count": len(chunks)},
        ).execute()
    except Exception as exc:
        # Log as CRITICAL — all chunk rows are in the DB but the document is
        # still 'processing'. The route handler must call _cleanup_document().
        logger.critical(
            "store_chunks: finalize_document RPC raised %s for document %s "
            "after %d chunks were already inserted — document left in 'processing' state",
            type(exc).__name__,
            document_id,
            len(chunks),
        )
        raise DatabaseError("finalize_document RPC failed") from exc

    if getattr(rpc_result, "error", None) is not None:
        logger.critical(
            "store_chunks: finalize_document RPC returned error for document %s: %s",
            document_id,
            rpc_result.error,
        )
        # S-01: log detail server-side; raise generic message safe for any consumer.
        logger.critical(
            "store_chunks: finalize_document RPC returned error for document %s: %s",
            document_id,
            rpc_result.error,
        )
        raise DatabaseError("finalize_document RPC operation failed")

    # Verify the RPC actually updated a row. The finalize_document procedure does an
    # UPDATE WHERE id = p_document_id — if the document_id doesn't exist in the table
    # (e.g. deleted between store_document() and store_chunks()), the UPDATE silently
    # affects 0 rows and returns successfully. We detect this by checking the RPC data.
    # supabase-py returns the affected rows in rpc_result.data for RETURNING-style RPCs;
    # if the RPC uses RETURNS void (as in our spec), data will be None or [].
    # In that case we fall back to a direct count query to confirm the document exists
    # and now has status='ready'.
    rpc_data = getattr(rpc_result, "data", None)
    if rpc_data is None or rpc_data == [] or rpc_data == {}:
        # RETURNS void RPC — verify the update took effect with a lightweight count check.
        try:
            check = (
                db.table("documents")
                .select("id", count="exact")
                .eq("id", document_id)
                .eq("status", "ready")
                .execute()
            )
        except Exception as exc:
            logger.error(
                "store_chunks: post-RPC verification query failed for document %s: %s",
                document_id,
                type(exc).__name__,
            )
            raise DatabaseError(
                "finalize_document RPC verification failed"
            ) from exc

        # check.count is the number of rows matching id + status='ready'.
        # 0 means the document_id was not found or status was not updated.
        if getattr(check, "count", 0) == 0:
            logger.critical(
                "store_chunks: finalize_document RPC ran but document %s "
                "not found or status not updated to 'ready'",
                document_id,
            )
            raise DatabaseError(
                "finalize_document RPC completed but document record was not updated — "
                "document_id may not exist in documents table"
            )

    logger.info(
        "store_chunks: %d chunks stored and document %s finalised as 'ready'.",
        len(chunks),
        document_id,
    )


def _cleanup_document(document_id: str, db: Client) -> None:
    """
    Set a document's status to 'failed' after a pipeline error.

    Called by the route handler when store_document() succeeds but a later
    stage (embed_texts or store_chunks) fails. Prevents the document row from
    remaining permanently in 'processing' state, which would make it invisible
    to users but waste storage space.

    This function intentionally swallows its own errors — if cleanup fails,
    the original error is already being propagated by the caller and must not
    be replaced by a cleanup error. The failure is logged at ERROR level so
    it appears in monitoring dashboards.

    Args:
        document_id: UUID string of the document row to mark as 'failed'.
        db:          Supabase client; injected by the route handler.

    Returns:
        None. Always returns, never raises.
    """
    try:
        result = (
            db.table("documents")
            .update({"status": "failed"})
            # .eq() adds WHERE id = document_id to the UPDATE query.
            .eq("id", document_id)
            .execute()
        )

        if getattr(result, "error", None) is not None:
            # Log but do not raise — cleanup failure must not mask the original error.
            logger.error(
                "_cleanup_document: update returned error for document %s: %s",
                document_id,
                result.error,
            )
        else:
            logger.info(
                "_cleanup_document: document %s marked as 'failed'.",
                document_id,
            )

    except Exception as exc:
        # Swallow the exception — see docstring.
        logger.error(
            "_cleanup_document: update raised %s for document %s",
            type(exc).__name__,
            document_id,
        )
