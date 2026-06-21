# tests/test_services_database.py — unit tests for services/database.py
# Covers store_document(), store_chunks(), and _cleanup_document().
#
# Key mocking approach:
#   All three functions accept `db: Client` as a parameter — so tests simply
#   pass a MagicMock() as `db`. No module-level patching is needed, unlike
#   test_embeddings.py which had to patch asyncio.to_thread.
#
#   store_chunks() calls db.table("documents") AND db.table("chunks") in the
#   same function, so we use db.table.side_effect to return different mock
#   chains depending on the table name (see _make_chunks_db()).

from unittest.mock import MagicMock, call, patch

import pytest

from services.database import (
    DatabaseError,
    _cleanup_document,
    store_chunks,
    store_document,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_VALID_UUID = "12345678-1234-4234-b234-123456789abc"
_VALID_FILENAME = "report.pdf"
_VALID_FILE_SIZE = 1024  # 1 KB — well within the 20 MB ceiling
_VALID_MIME_PDF = "application/pdf"
_VALID_MIME_TXT = "text/plain"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def valid_chunks() -> list[str]:
    """Returns a list of 3 non-empty chunk strings for use in store_chunks() tests."""
    return ["chunk one text", "chunk two text", "chunk three text"]


@pytest.fixture
def valid_embeddings() -> list[list[float]]:
    """Returns 3 fake 1536-dimension embedding vectors (all 0.1) for store_chunks() tests."""
    return [[0.1] * 1536] * 3


@pytest.fixture
def ok_insert_result() -> MagicMock:
    """Returns a mock Supabase result representing a successful single-row insert.

    result.data contains one row with a fake UUID 'id'.
    result.error is None (no database error).
    """
    result = MagicMock()
    result.data = [{"id": _VALID_UUID}]
    result.error = None
    return result


@pytest.fixture
def ok_chunks_insert_result() -> MagicMock:
    """Returns a mock Supabase result for a successful chunk batch insert.

    result.data is a non-empty list (actual content doesn't matter for these tests).
    result.error is None.
    """
    result = MagicMock()
    result.data = [{"id": "chunk-row-id"}]
    result.error = None
    return result


@pytest.fixture
def ok_rpc_result() -> MagicMock:
    """Returns a mock RPC result with data=[...] to bypass the verification step.

    When rpc_result.data is a non-empty list (not None/[]/{}), store_chunks()
    skips the follow-up count query because the RPC already confirms the update.
    """
    result = MagicMock()
    # Non-empty list means: RPC returned rows (RETURNING-style), verification skipped.
    result.data = [{"status": "ready"}]
    result.error = None
    return result


def _make_store_document_db(execute_result: MagicMock) -> MagicMock:
    """Build a mock Supabase client wired for store_document() calls.

    store_document() only calls db.table("documents").insert(...).execute(),
    so we only need to configure that chain.

    Args:
        execute_result: The MagicMock returned by .execute() — set .data and .error on it.
    Returns:
        Configured MagicMock that acts as a Supabase Client.
    """
    db = MagicMock()
    # Chain: db.table(...).insert(...).execute() → execute_result
    db.table.return_value.insert.return_value.execute.return_value = execute_result
    return db


def _make_chunks_db(
    chunks_result: MagicMock,
    rpc_result: MagicMock,
    verify_count: int = 1,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Build a mock Supabase client wired for store_chunks() calls.

    store_chunks() calls three different Supabase chains:
      1. db.table("chunks").insert(batch).execute()      — chunk inserts
      2. db.rpc("finalize_document", {...}).execute()    — RPC
      3. db.table("documents").select(...).eq(...).eq(...).execute()  — verification

    We use db.table.side_effect to return different mock chains for "chunks" vs
    "documents", so each table's assert calls are independent.

    Args:
        chunks_result:  Result returned by the chunks insert .execute().
        rpc_result:     Result returned by the RPC .execute().
        verify_count:   Value for check.count in the verification query (default 1 = found).

    Returns:
        Tuple of (db, documents_chain, chunks_chain) so tests can inspect call counts.
    """
    db = MagicMock()

    # ── "chunks" table chain ─────────────────────────────────────────────────
    chunks_chain = MagicMock()
    chunks_chain.insert.return_value.execute.return_value = chunks_result

    # ── "documents" table chain (used only in the verification step) ─────────
    documents_chain = MagicMock()
    verify_result = MagicMock()
    verify_result.count = verify_count
    verify_result.error = None
    # Chain: db.table("documents").select(...).eq(...).eq(...).execute()
    documents_chain.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
        verify_result
    )

    def _table_side_effect(table_name: str) -> MagicMock:
        """Return the correct chain mock based on which table is being accessed."""
        if table_name == "chunks":
            return chunks_chain
        if table_name == "documents":
            return documents_chain
        return MagicMock()

    db.table.side_effect = _table_side_effect
    db.rpc.return_value.execute.return_value = rpc_result

    return db, documents_chain, chunks_chain


def _make_cleanup_db(execute_result: MagicMock) -> MagicMock:
    """Build a mock Supabase client wired for _cleanup_document() calls.

    _cleanup_document() calls db.table("documents").update(...).eq(...).execute().
    """
    db = MagicMock()
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        execute_result
    )
    return db


# ═════════════════════════════════════════════════════════════════════════════
# store_document()
# ═════════════════════════════════════════════════════════════════════════════


class TestStoreDocument:
    """Tests for store_document() — inserts a documents row, returns UUID string."""

    def test_happy_path_returns_document_id(self, ok_insert_result: MagicMock) -> None:
        """Verifies that store_document() returns the UUID from result.data[0]['id']
        when Supabase insert succeeds with valid inputs."""
        db = _make_store_document_db(ok_insert_result)
        result = store_document(_VALID_FILENAME, _VALID_FILE_SIZE, _VALID_MIME_PDF, db)
        assert result == _VALID_UUID

    def test_inserts_correct_payload_fields(self, ok_insert_result: MagicMock) -> None:
        """Verifies that store_document() passes filename, file_size, mime_type,
        status='processing', and created_at to the Supabase insert call."""
        db = _make_store_document_db(ok_insert_result)
        store_document(_VALID_FILENAME, _VALID_FILE_SIZE, _VALID_MIME_PDF, db)

        # Extract the payload that was passed to .insert(...)
        insert_call_args = db.table.return_value.insert.call_args
        payload = insert_call_args[0][0]  # first positional arg to insert()

        assert payload["filename"] == _VALID_FILENAME
        assert payload["file_size"] == _VALID_FILE_SIZE
        assert payload["mime_type"] == _VALID_MIME_PDF
        assert payload["status"] == "processing"
        assert "created_at" in payload  # datetime string — just verify key is present

    def test_inserts_into_documents_table(self, ok_insert_result: MagicMock) -> None:
        """Verifies that store_document() calls db.table('documents'), not any other table."""
        db = _make_store_document_db(ok_insert_result)
        store_document(_VALID_FILENAME, _VALID_FILE_SIZE, _VALID_MIME_PDF, db)
        db.table.assert_called_once_with("documents")

    def test_accepts_txt_mime_type(self, ok_insert_result: MagicMock) -> None:
        """Verifies that store_document() accepts 'text/plain' as a valid mime_type."""
        db = _make_store_document_db(ok_insert_result)
        result = store_document(_VALID_FILENAME, _VALID_FILE_SIZE, _VALID_MIME_TXT, db)
        assert result == _VALID_UUID

    def test_filename_at_max_length_succeeds(self, ok_insert_result: MagicMock) -> None:
        """Verifies that store_document() accepts a filename of exactly 255 characters."""
        db = _make_store_document_db(ok_insert_result)
        filename_255 = "a" * 255
        result = store_document(filename_255, _VALID_FILE_SIZE, _VALID_MIME_PDF, db)
        assert result == _VALID_UUID

    def test_file_size_at_max_limit_succeeds(self, ok_insert_result: MagicMock) -> None:
        """Verifies that store_document() accepts file_size == 20 MB exactly (the ceiling)."""
        db = _make_store_document_db(ok_insert_result)
        max_bytes = 20 * 1024 * 1024
        result = store_document(_VALID_FILENAME, max_bytes, _VALID_MIME_PDF, db)
        assert result == _VALID_UUID

    def test_filename_too_long_raises_value_error(self) -> None:
        """Verifies that store_document() raises ValueError when filename exceeds 255 chars,
        before any Supabase call is made."""
        db = MagicMock()
        with pytest.raises(ValueError, match="filename exceeds"):
            store_document("a" * 256, _VALID_FILE_SIZE, _VALID_MIME_PDF, db)
        db.table.assert_not_called()

    def test_file_size_zero_raises_value_error(self) -> None:
        """Verifies that store_document() raises ValueError when file_size is 0."""
        db = MagicMock()
        with pytest.raises(ValueError, match="file_size out of allowed range"):
            store_document(_VALID_FILENAME, 0, _VALID_MIME_PDF, db)
        db.table.assert_not_called()

    def test_file_size_above_limit_raises_value_error(self) -> None:
        """Verifies that store_document() raises ValueError when file_size exceeds 20 MB."""
        db = MagicMock()
        over_limit = 20 * 1024 * 1024 + 1
        with pytest.raises(ValueError, match="file_size out of allowed range"):
            store_document(_VALID_FILENAME, over_limit, _VALID_MIME_PDF, db)
        db.table.assert_not_called()

    def test_file_size_as_bool_raises_value_error(self) -> None:
        """Verifies that store_document() raises ValueError when file_size is True or False.
        bool is a subclass of int in Python — without this check, True (== 1) would pass."""
        db = MagicMock()
        with pytest.raises(ValueError, match="file_size must be an int"):
            store_document(_VALID_FILENAME, True, _VALID_MIME_PDF, db)  # type: ignore[arg-type]
        db.table.assert_not_called()

    def test_file_size_as_float_raises_value_error(self) -> None:
        """Verifies that store_document() raises ValueError when file_size is a float."""
        db = MagicMock()
        with pytest.raises(ValueError, match="file_size must be an int"):
            store_document(_VALID_FILENAME, 1024.5, _VALID_MIME_PDF, db)  # type: ignore[arg-type]
        db.table.assert_not_called()

    def test_filename_with_path_traversal_raises_value_error(self) -> None:
        """Verifies that store_document() raises ValueError for filenames containing '..',
        preventing directory traversal sequences from being stored in the database."""
        db = MagicMock()
        with pytest.raises(ValueError, match="must not contain"):
            store_document("../../etc/passwd", _VALID_FILE_SIZE, _VALID_MIME_PDF, db)
        db.table.assert_not_called()

    def test_filename_with_forward_slash_raises_value_error(self) -> None:
        """Verifies that store_document() raises ValueError for filenames containing '/',
        which signals a path component and must not be stored."""
        db = MagicMock()
        with pytest.raises(ValueError, match="invalid characters"):
            store_document("folder/report.pdf", _VALID_FILE_SIZE, _VALID_MIME_PDF, db)
        db.table.assert_not_called()

    def test_filename_with_null_byte_raises_value_error(self) -> None:
        """Verifies that store_document() raises ValueError for filenames containing null bytes,
        which can truncate strings in C-based systems and bypass extension checks."""
        db = MagicMock()
        with pytest.raises(ValueError, match="invalid characters"):
            store_document("report\x00.pdf", _VALID_FILE_SIZE, _VALID_MIME_PDF, db)
        db.table.assert_not_called()

    def test_unsupported_mime_type_raises_value_error(self) -> None:
        """Verifies that store_document() raises ValueError for mime types outside the allowlist."""
        db = MagicMock()
        with pytest.raises(ValueError, match="unsupported mime_type"):
            store_document(_VALID_FILENAME, _VALID_FILE_SIZE, "image/png", db)
        db.table.assert_not_called()

    def test_supabase_raises_exception_wrapped_as_database_error(self) -> None:
        """Verifies that store_document() wraps a Supabase exception in DatabaseError,
        not letting the raw exception propagate to the route handler."""
        db = MagicMock()
        db.table.return_value.insert.return_value.execute.side_effect = RuntimeError(
            "connection refused"
        )
        with pytest.raises(DatabaseError, match="Failed to insert document record"):
            store_document(_VALID_FILENAME, _VALID_FILE_SIZE, _VALID_MIME_PDF, db)

    def test_result_error_set_raises_database_error(self) -> None:
        """Verifies that store_document() raises DatabaseError when result.error is not None,
        which is how supabase-py signals constraint violations without raising."""
        result = MagicMock()
        result.data = []
        result.error = "some db error"
        db = _make_store_document_db(result)
        with pytest.raises(DatabaseError, match="database operation failed"):
            store_document(_VALID_FILENAME, _VALID_FILE_SIZE, _VALID_MIME_PDF, db)

    def test_duplicate_filename_raises_database_error_with_message(self) -> None:
        """Verifies that a unique-constraint violation produces a specific DatabaseError message
        about duplicate filenames, making the error actionable for the route handler."""
        result = MagicMock()
        result.data = []
        result.error = 'duplicate key value violates unique constraint "documents_filename_key"'
        db = _make_store_document_db(result)
        with pytest.raises(DatabaseError, match="document with this filename already exists"):
            store_document(_VALID_FILENAME, _VALID_FILE_SIZE, _VALID_MIME_PDF, db)

    def test_empty_result_data_raises_database_error(self) -> None:
        """Verifies that store_document() raises DatabaseError when result.data is an empty list,
        meaning Supabase returned success but no row data — an unexpected state."""
        result = MagicMock()
        result.data = []
        result.error = None
        db = _make_store_document_db(result)
        with pytest.raises(DatabaseError, match="unexpected empty response"):
            store_document(_VALID_FILENAME, _VALID_FILE_SIZE, _VALID_MIME_PDF, db)

    def test_result_data_missing_id_field_raises_database_error(self) -> None:
        """Verifies that store_document() raises DatabaseError when the returned row
        has no 'id' key — prevents a bare KeyError from reaching the route handler."""
        result = MagicMock()
        result.data = [{"filename": "report.pdf"}]  # row exists but 'id' key is absent
        result.error = None
        db = _make_store_document_db(result)
        with pytest.raises(DatabaseError, match="missing expected 'id' field"):
            store_document(_VALID_FILENAME, _VALID_FILE_SIZE, _VALID_MIME_PDF, db)


# ═════════════════════════════════════════════════════════════════════════════
# store_chunks()
# ═════════════════════════════════════════════════════════════════════════════


class TestStoreChunks:
    """Tests for store_chunks() — batch-inserts chunks and calls finalize_document RPC."""

    def test_happy_path_returns_none(
        self,
        valid_chunks: list[str],
        valid_embeddings: list[list[float]],
        ok_chunks_insert_result: MagicMock,
        ok_rpc_result: MagicMock,
    ) -> None:
        """Verifies that store_chunks() returns None when all Supabase calls succeed."""
        db, _, _ = _make_chunks_db(ok_chunks_insert_result, ok_rpc_result)
        result = store_chunks(_VALID_UUID, valid_chunks, valid_embeddings, db)
        assert result is None

    def test_chunk_index_is_sequential_from_zero(
        self,
        valid_chunks: list[str],
        valid_embeddings: list[list[float]],
        ok_chunks_insert_result: MagicMock,
        ok_rpc_result: MagicMock,
    ) -> None:
        """Verifies that chunk_index in inserted rows is 0, 1, 2... preserving document order."""
        db, _, chunks_chain = _make_chunks_db(ok_chunks_insert_result, ok_rpc_result)
        store_chunks(_VALID_UUID, valid_chunks, valid_embeddings, db)

        inserted_batch = chunks_chain.insert.call_args[0][0]  # first call, first positional arg
        indices = [row["chunk_index"] for row in inserted_batch]
        assert indices == [0, 1, 2]

    def test_embeddings_cast_to_float32(
        self,
        ok_chunks_insert_result: MagicMock,
        ok_rpc_result: MagicMock,
    ) -> None:
        """Verifies that embedding values in inserted rows are float32, not float64.
        pgvector rejects float64 — the cast must happen before the insert call."""
        chunks = ["text"]
        # float64 input — Python default
        embeddings_f64 = [[0.123456789012345] * 1536]

        db, _, chunks_chain = _make_chunks_db(ok_chunks_insert_result, ok_rpc_result)
        store_chunks(_VALID_UUID, chunks, embeddings_f64, db)

        inserted_batch = chunks_chain.insert.call_args[0][0]
        stored_vector = inserted_batch[0]["embedding"]

        # Round-trip through float32 and back to float64 — values change if cast correctly.
        # If no cast happened, the original float64 precision would be preserved.
        import numpy as np
        expected_f32 = np.array(embeddings_f64[0], dtype=np.float32).tolist()
        assert stored_vector == expected_f32
        assert stored_vector != embeddings_f64[0]  # proves the cast actually changed values

    def test_250_chunks_makes_three_insert_calls(
        self,
        ok_chunks_insert_result: MagicMock,
        ok_rpc_result: MagicMock,
    ) -> None:
        """Verifies that store_chunks() calls insert exactly 3 times for 250 chunks:
        batches of [0:100], [100:200], [200:250] — matching the 100-row batch cap."""
        chunks = [f"chunk {i}" for i in range(250)]
        embeddings = [[0.1] * 1536] * 250

        db, _, chunks_chain = _make_chunks_db(ok_chunks_insert_result, ok_rpc_result)
        store_chunks(_VALID_UUID, chunks, embeddings, db)

        assert chunks_chain.insert.call_count == 3

        # Verify batch sizes: 100, 100, 50
        first_batch = chunks_chain.insert.call_args_list[0][0][0]
        second_batch = chunks_chain.insert.call_args_list[1][0][0]
        third_batch = chunks_chain.insert.call_args_list[2][0][0]
        assert len(first_batch) == 100
        assert len(second_batch) == 100
        assert len(third_batch) == 50

    def test_single_chunk_makes_one_insert_call(
        self,
        ok_chunks_insert_result: MagicMock,
        ok_rpc_result: MagicMock,
    ) -> None:
        """Verifies that store_chunks() makes exactly one insert call for a single chunk."""
        db, _, chunks_chain = _make_chunks_db(ok_chunks_insert_result, ok_rpc_result)
        store_chunks(_VALID_UUID, ["only chunk"], [[0.1] * 1536], db)
        assert chunks_chain.insert.call_count == 1

    def test_calls_finalize_rpc_with_correct_args(
        self,
        valid_chunks: list[str],
        valid_embeddings: list[list[float]],
        ok_chunks_insert_result: MagicMock,
        ok_rpc_result: MagicMock,
    ) -> None:
        """Verifies that store_chunks() calls the finalize_document RPC with the correct
        document_id and chunk_count after all inserts succeed."""
        db, _, _ = _make_chunks_db(ok_chunks_insert_result, ok_rpc_result)
        store_chunks(_VALID_UUID, valid_chunks, valid_embeddings, db)

        db.rpc.assert_called_once_with(
            "finalize_document",
            {"p_document_id": _VALID_UUID, "p_chunk_count": len(valid_chunks)},
        )

    def test_verification_step_runs_when_rpc_returns_void(
        self,
        valid_chunks: list[str],
        valid_embeddings: list[list[float]],
        ok_chunks_insert_result: MagicMock,
    ) -> None:
        """Verifies that when the RPC returns None data (void RPC), store_chunks()
        performs a follow-up count query to confirm the document was updated."""
        rpc_result = MagicMock()
        rpc_result.data = None  # void RPC — triggers the verification step
        rpc_result.error = None

        db, documents_chain, _ = _make_chunks_db(
            ok_chunks_insert_result, rpc_result, verify_count=1
        )
        store_chunks(_VALID_UUID, valid_chunks, valid_embeddings, db)

        # Verification query must have been called on the documents table
        documents_chain.select.assert_called_once()

    def test_verification_count_zero_raises_database_error(
        self,
        valid_chunks: list[str],
        valid_embeddings: list[list[float]],
        ok_chunks_insert_result: MagicMock,
    ) -> None:
        """Verifies that store_chunks() raises DatabaseError when the post-RPC
        count query returns 0, meaning the document_id was not found or not updated."""
        rpc_result = MagicMock()
        rpc_result.data = None  # void RPC — triggers verification step
        rpc_result.error = None

        db, _, _ = _make_chunks_db(
            ok_chunks_insert_result, rpc_result, verify_count=0
        )
        with pytest.raises(DatabaseError, match="document record was not updated"):
            store_chunks(_VALID_UUID, valid_chunks, valid_embeddings, db)

    def test_empty_chunks_raises_value_error_before_db_call(self) -> None:
        """Verifies that store_chunks() raises ValueError for an empty chunks list
        before making any Supabase call."""
        db = MagicMock()
        with pytest.raises(ValueError, match="chunks list must not be empty"):
            store_chunks(_VALID_UUID, [], [], db)
        db.table.assert_not_called()

    def test_mismatched_lengths_raises_value_error(self) -> None:
        """Verifies that store_chunks() raises ValueError when len(chunks) != len(embeddings),
        preventing rows with missing embeddings from reaching the DB."""
        db = MagicMock()
        with pytest.raises(ValueError, match="length mismatch"):
            store_chunks(_VALID_UUID, ["a", "b"], [[0.1] * 1536], db)
        db.table.assert_not_called()

    def test_wrong_embedding_dimension_raises_value_error(self) -> None:
        """Verifies that store_chunks() raises ValueError when any embedding has != 1536 dims,
        which pgvector would reject with a cryptic constraint error if not caught here."""
        db = MagicMock()
        with pytest.raises(ValueError, match="embedding\\[0\\] has 512 dimensions"):
            store_chunks(_VALID_UUID, ["chunk"], [[0.1] * 512], db)
        db.table.assert_not_called()

    def test_invalid_uuid_raises_value_error(self) -> None:
        """Verifies that store_chunks() raises ValueError for a malformed document_id,
        catching bad UUIDs before they reach Supabase and produce cryptic FK errors."""
        db = MagicMock()
        with pytest.raises(ValueError, match="not a valid UUID"):
            store_chunks("not-a-uuid", ["chunk"], [[0.1] * 1536], db)
        db.table.assert_not_called()

    def test_insert_raises_exception_wrapped_as_database_error(self) -> None:
        """Verifies that an exception from the chunks insert call is wrapped in DatabaseError,
        not propagated as a raw exception to the route handler."""
        db = MagicMock()
        db.table.side_effect = None  # reset side_effect so .table is a plain MagicMock
        db.table.return_value.insert.return_value.execute.side_effect = RuntimeError(
            "network timeout"
        )
        with pytest.raises(DatabaseError, match="Failed to insert chunk batch"):
            store_chunks(_VALID_UUID, ["chunk"], [[0.1] * 1536], db)

    def test_insert_result_error_raises_database_error(
        self,
        ok_rpc_result: MagicMock,
    ) -> None:
        """Verifies that store_chunks() raises DatabaseError when result.error is set
        on the chunks insert result (supabase-py error object, not a raised exception)."""
        bad_result = MagicMock()
        bad_result.data = []
        bad_result.error = "violates foreign key constraint"

        db, _, _ = _make_chunks_db(bad_result, ok_rpc_result)
        with pytest.raises(DatabaseError, match="database operation failed on batch"):
            store_chunks(_VALID_UUID, ["chunk"], [[0.1] * 1536], db)

    def test_rpc_raises_exception_wrapped_as_database_error(
        self,
        valid_chunks: list[str],
        valid_embeddings: list[list[float]],
        ok_chunks_insert_result: MagicMock,
    ) -> None:
        """Verifies that an exception from the finalize_document RPC is wrapped in
        DatabaseError — all chunks are already inserted at this point.

        Note: we build the db mock directly here instead of using _make_chunks_db
        because we need db.rpc(...).execute() to RAISE (not return a result object).
        Setting side_effect on the execute call itself is the correct way to do this.
        """
        db, _, chunks_chain = _make_chunks_db(ok_chunks_insert_result, MagicMock())
        # Override: make db.rpc(...).execute() raise instead of returning a result.
        db.rpc.return_value.execute.side_effect = RuntimeError("RPC not found")

        with pytest.raises(DatabaseError, match="finalize_document RPC failed"):
            store_chunks(_VALID_UUID, valid_chunks, valid_embeddings, db)

    def test_rpc_result_error_raises_database_error(
        self,
        valid_chunks: list[str],
        valid_embeddings: list[list[float]],
        ok_chunks_insert_result: MagicMock,
    ) -> None:
        """Verifies that store_chunks() raises DatabaseError when the RPC result.error
        is set — the finalize_document procedure returned a PostgreSQL error."""
        rpc_result = MagicMock()
        rpc_result.data = None
        rpc_result.error = "function finalize_document does not exist"

        db, _, _ = _make_chunks_db(ok_chunks_insert_result, rpc_result)
        with pytest.raises(DatabaseError, match="finalize_document RPC operation failed"):
            store_chunks(_VALID_UUID, valid_chunks, valid_embeddings, db)


# ═════════════════════════════════════════════════════════════════════════════
# _cleanup_document()
# ═════════════════════════════════════════════════════════════════════════════


class TestCleanupDocument:
    """Tests for _cleanup_document() — sets document status to 'failed', never raises."""

    def test_sets_status_to_failed(self) -> None:
        """Verifies that _cleanup_document() calls Supabase update with status='failed'."""
        ok_result = MagicMock()
        ok_result.error = None
        db = _make_cleanup_db(ok_result)

        _cleanup_document(_VALID_UUID, db)

        update_call_args = db.table.return_value.update.call_args[0][0]
        assert update_call_args == {"status": "failed"}

    def test_filters_update_by_document_id(self) -> None:
        """Verifies that _cleanup_document() adds WHERE id = document_id to the update,
        not updating all documents."""
        ok_result = MagicMock()
        ok_result.error = None
        db = _make_cleanup_db(ok_result)

        _cleanup_document(_VALID_UUID, db)

        # .eq("id", document_id) must be called with the correct id
        db.table.return_value.update.return_value.eq.assert_called_once_with(
            "id", _VALID_UUID
        )

    def test_returns_none_on_success(self) -> None:
        """Verifies that _cleanup_document() returns None (not the Supabase result)."""
        ok_result = MagicMock()
        ok_result.error = None
        db = _make_cleanup_db(ok_result)

        result = _cleanup_document(_VALID_UUID, db)
        assert result is None

    def test_swallows_supabase_exception_and_returns_none(self) -> None:
        """Verifies that _cleanup_document() never raises even when Supabase throws —
        cleanup failure must not mask the original pipeline error that caused it."""
        db = MagicMock()
        db.table.return_value.update.return_value.eq.return_value.execute.side_effect = (
            RuntimeError("DB is down")
        )

        # Must not raise — must return None silently
        result = _cleanup_document(_VALID_UUID, db)
        assert result is None

    def test_swallows_result_error_and_returns_none(self) -> None:
        """Verifies that _cleanup_document() returns None even when result.error is set,
        logging the error without re-raising it."""
        bad_result = MagicMock()
        bad_result.error = "row not found"
        db = _make_cleanup_db(bad_result)

        result = _cleanup_document(_VALID_UUID, db)
        assert result is None
