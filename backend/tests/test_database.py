# tests/test_database.py — tests for the Supabase client singleton in database.py.
#
# Why test a singleton?
#   database.py runs _init_supabase_client() at import time. That function has two
#   branches: success (returns a client) and failure (raises RuntimeError).
#   conftest.py already exercises the success branch by letting it run during app
#   import. These tests verify the singleton exists AND that the failure branch
#   raises the right exception with no credential leakage.

from unittest.mock import MagicMock, patch

import pytest

# Import database AFTER conftest.py has already patched create_client and imported main.
# Because Python caches modules in sys.modules, this import is free — it just returns
# the already-initialised module without re-running any module-level code.
import database


class TestSupabaseSingleton:
    """Tests that the module-level supabase singleton is correctly initialised."""

    def test_supabase_singleton_is_not_none(self, mock_supabase: MagicMock) -> None:
        """Verifies that database.supabase exists and is not None."""
        assert database.supabase is not None

    def test_supabase_singleton_is_mock_during_tests(self, mock_supabase: MagicMock) -> None:
        """Verifies that database.supabase is the MagicMock, not a real Supabase client.

        If this assertion fails, the test suite is making real network connections.
        Fix: ensure conftest.py patches supabase.create_client before importing main.
        """
        assert database.supabase is mock_supabase


class TestInitSupabaseClient:
    """Tests for the _init_supabase_client() helper function's error-handling branch.

    Note on patch target:
        database.py uses 'from supabase import create_client', which binds the name
        'create_client' into database.py's own namespace at import time.
        To replace that already-bound name, we patch 'database.create_client'
        (the copy inside database.py), NOT 'supabase.create_client' (the original).
    """

    def test_init_calls_create_client_with_url_and_key(self) -> None:
        """Verifies that _init_supabase_client passes SUPABASE_URL and SUPABASE_ANON_KEY
        to create_client."""
        mock_client = MagicMock()
        with patch("database.create_client", return_value=mock_client) as mock_create:
            database._init_supabase_client()

            mock_create.assert_called_once()
            call_args = mock_create.call_args
            # First positional arg is the URL, second is the anon key
            assert call_args.args[0] == "https://test.supabase.co"
            assert call_args.args[1] == "test-supabase-anon-key"

    def test_init_returns_client_on_success(self) -> None:
        """Verifies that _init_supabase_client returns the value from create_client."""
        mock_client = MagicMock()
        with patch("database.create_client", return_value=mock_client):
            result = database._init_supabase_client()

        assert result is mock_client

    def test_init_raises_runtime_error_on_failure(self) -> None:
        """Verifies that _init_supabase_client raises RuntimeError when create_client fails.

        We deliberately convert any SDK exception into a RuntimeError so that
        credential-containing error messages from the SDK can't reach log output.
        """
        with patch("database.create_client", side_effect=ValueError("connection refused")):
            with pytest.raises(RuntimeError, match="Supabase client initialisation failed"):
                database._init_supabase_client()

    def test_init_suppresses_original_exception_cause(self) -> None:
        """Verifies that the RuntimeError has no __cause__ (raised with 'from None').

        'raise RuntimeError(...) from None' breaks the exception chain so the SDK's
        original exception (which may contain URL fragments) cannot be introspected.
        """
        with patch("database.create_client", side_effect=ValueError("secret-url-fragment")):
            with pytest.raises(RuntimeError) as exc_info:
                database._init_supabase_client()

            # __cause__ is None when 'raise ... from None' was used
            assert exc_info.value.__cause__ is None

    def test_init_runtime_error_message_does_not_expose_exception_type(self) -> None:
        """Verifies that the RuntimeError message is a safe, generic string.

        The original exception type is logged (not the message), so the RuntimeError
        message itself must never repeat SDK-specific details.
        """
        with patch("database.create_client", side_effect=ConnectionError("host unreachable")):
            with pytest.raises(RuntimeError) as exc_info:
                database._init_supabase_client()

        # The message should be our safe generic string, not anything from the SDK
        assert "SUPABASE_URL" in str(exc_info.value)
        assert "host unreachable" not in str(exc_info.value)
