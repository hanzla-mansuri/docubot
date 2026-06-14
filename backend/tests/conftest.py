# tests/conftest.py — shared fixtures and test environment setup for DocuBot.
# This file is automatically loaded by pytest before any test runs.
#
# Key problem it solves:
#   database.py calls supabase.create_client() at module level (import time).
#   If we let that run during tests, it would try to connect to a real Supabase
#   instance and crash because the test machine has no real credentials.
#   Solution: patch supabase.create_client() BEFORE importing main.py so the
#   singleton is a harmless MagicMock for the entire test session.

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# ── Step 1: set fake environment variables ───────────────────────────────────
# pydantic-settings reads os.environ first (higher priority than .env file).
# These must be set BEFORE config.py is first imported, because Settings() runs
# at config.py's module level and only reads env vars once.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-supabase-anon-key")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("APP_VERSION", "0.1.0")

# ── Step 2: patch supabase.create_client BEFORE any local import ─────────────
# When database.py is imported it runs:
#   from supabase import create_client           ← reads supabase.create_client
#   supabase = _init_supabase_client()           ← calls create_client(...)
#
# By patching supabase.create_client NOW, the "from supabase import create_client"
# line inside database.py will bind our mock to database.create_client.
# The singleton (database.supabase) then becomes our MagicMock — no network call.
_mock_supabase_client = MagicMock()
_supabase_patcher = patch("supabase.create_client", return_value=_mock_supabase_client)
_supabase_patcher.start()

# ── Step 3: now safe to import the app ───────────────────────────────────────
# All import-time side effects (Settings(), _init_supabase_client()) run here
# using our fake env vars and mocked create_client.
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client() -> TestClient:
    """Returns a FastAPI TestClient wrapping the DocuBot app.

    scope="session" means one client is shared across all tests — avoids
    re-importing and re-initialising the app for every test function.
    """
    return TestClient(app)


@pytest.fixture(scope="session")
def mock_supabase() -> MagicMock:
    """Returns the mock Supabase client used during the test session.

    Tests can call mock_supabase.table.return_value = ... to simulate
    database responses without hitting a real Supabase instance.
    """
    return _mock_supabase_client
