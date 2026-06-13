# database.py — creates and exposes one shared Supabase client for the entire application.
# Every module that needs to query the database imports `supabase` from here.
# A single shared client is more efficient than opening a new connection per request.

import logging

from supabase import Client, create_client

from config import settings

# Standard Python logger — __name__ resolves to "database" so log lines show the source module
logger = logging.getLogger(__name__)


def _init_supabase_client() -> Client:
    """
    Create and return a validated Supabase client using credentials from settings.

    Wrapped in a private function so the try/except isolates initialisation failures
    and prevents them from producing unhelpful bare import-time tracebacks.

    Args: none — reads SUPABASE_URL and SUPABASE_ANON_KEY from the settings singleton.
    Returns: an initialised supabase.Client ready for database operations.
    Raises: re-raises the original exception after logging the error type (never the key value).
    """
    try:
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        logger.info("Supabase client object created (connectivity not yet verified).")
        return client
    except Exception as e:
        # Log the exception TYPE only — never log URL or key values in error messages
        logger.error("Failed to initialise Supabase client: %s", type(e).__name__)
        # Raise a safe RuntimeError so no credential-containing exception message
        # from the Supabase SDK can reach uvicorn's default traceback printer
        raise RuntimeError(
            "Supabase client initialisation failed — check SUPABASE_URL and SUPABASE_ANON_KEY."
        ) from None


# Module-level singleton — import this anywhere database access is needed:
#   from database import supabase
supabase: Client = _init_supabase_client()
