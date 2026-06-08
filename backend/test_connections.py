"""
test_connections.py — DocuBot connection verification script.

Purpose: Confirm that all three external APIs (Claude, OpenAI, Supabase)
are reachable and that the keys in backend/.env are valid. Run this once
after setting up your .env file and installing requirements.

Usage (from the backend/ directory with .venv active):
    python test_connections.py

Each test prints PASS or FAIL. If any test fails, the script exits with
code 1 so that CI pipelines (or a calling script) can detect the failure.
"""

import os
import sys

# python-dotenv reads the .env file and adds each key to os.environ.
# This must happen before any API client is imported, because those clients
# read their keys from environment variables at import or instantiation time.
from dotenv import load_dotenv

load_dotenv()  # looks for .env in the current working directory by default


# ---------------------------------------------------------------------------
# Individual connection tests
# ---------------------------------------------------------------------------


def test_claude() -> bool:
    """
    Test the Anthropic Claude API by sending the cheapest valid message.

    Sends a single "hi" prompt with max_tokens=1 to minimise cost while
    still making a real authenticated API call. A successful response
    confirms the key is valid and the endpoint is reachable.

    Parameters: none
    Returns: True if the connection succeeds, False otherwise.
    """
    import anthropic  # imported here so a missing package only fails this test

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("FAIL  Claude API  — ANTHROPIC_API_KEY not found in .env")
        return False

    try:
        client = anthropic.Anthropic(api_key=api_key)

        # max_tokens=1 is the minimum allowed — we don't need the answer,
        # just confirmation that the API accepted our request.
        message = client.messages.create(
            model="claude-haiku-4-5",  # matches the model chosen in CLAUDE.md
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )

        # message.content is a list of content blocks; any non-empty list = success
        if message.content:
            print("PASS  Claude API  — connection OK")
            return True

        print("FAIL  Claude API  — API returned an empty response")
        return False

    except anthropic.AuthenticationError:
        print("FAIL  Claude API  — invalid API key, check ANTHROPIC_API_KEY in .env")
        return False
    except anthropic.APIConnectionError as e:
        print(f"FAIL  Claude API  — could not reach server ({e})")
        return False
    except Exception as e:
        print(f"FAIL  Claude API  — unexpected error ({type(e).__name__}: {e})")
        return False


def test_openai() -> bool:
    """
    Test the OpenAI embeddings API by embedding a short test string.

    Uses text-embedding-3-small (1536 dimensions) — the exact model and
    dimension count that DocuBot will use in production. Confirms the key
    is valid, the quota is not exhausted, and the embedding shape is correct.

    Parameters: none
    Returns: True if a correctly-shaped embedding is returned, False otherwise.
    """
    import openai  # imported here so a missing package only fails this test

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("FAIL  OpenAI API  — OPENAI_API_KEY not found in .env")
        return False

    try:
        client = openai.OpenAI(api_key=api_key)

        response = client.embeddings.create(
            model="text-embedding-3-small",
            input="connection test",  # minimal input keeps the cost near zero
        )

        # response.data is a list of Embedding objects; grab the first one
        embedding = response.data[0].embedding  # embedding is a list of floats

        # text-embedding-3-small always returns exactly 1536 floats
        if len(embedding) == 1536:
            print("PASS  OpenAI API  — connection OK (1536-dimension embedding received)")
            return True

        print(
            f"FAIL  OpenAI API  — unexpected embedding dimension: {len(embedding)} "
            "(expected 1536)"
        )
        return False

    except openai.AuthenticationError:
        print("FAIL  OpenAI API  — invalid API key, check OPENAI_API_KEY in .env")
        return False
    except openai.APIConnectionError as e:
        print(f"FAIL  OpenAI API  — could not reach server ({e})")
        return False
    except openai.RateLimitError:
        print("FAIL  OpenAI API  — rate limit or quota exceeded on your OpenAI account")
        return False
    except Exception as e:
        print(f"FAIL  OpenAI API  — unexpected error ({type(e).__name__}: {e})")
        return False


def test_supabase() -> bool:
    """
    Test the Supabase connection by creating a client and making a real query.

    Queries a table that does not yet exist. Receiving a "relation does not
    exist" error from PostgreSQL still counts as PASS because it proves we
    successfully authenticated and reached the database — we just haven't
    created any tables yet, which is expected at this phase of the project.

    Parameters: none
    Returns: True if the connection succeeds (or table is missing), False on
             authentication or network failure.
    """
    from supabase import create_client, Client  # imported here so a missing package only fails this test

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")

    if not url:
        print("FAIL  Supabase    — SUPABASE_URL not found in .env")
        return False
    if not key:
        print("FAIL  Supabase    — SUPABASE_ANON_KEY not found in .env")
        return False

    try:
        # create_client validates the URL format and builds the HTTP client.
        # No network call happens yet — the actual call is the .execute() below.
        supabase: Client = create_client(url, key)

        # We query a table that doesn't exist on purpose.
        # PostgREST (the layer Supabase uses) returns a 42P01 "relation does
        # not exist" error, which still means we reached the database.
        supabase.table("_docubot_ping").select("id").limit(1).execute()

        # If the table somehow exists, the query succeeded — connection is fine
        print("PASS  Supabase    — connection OK")
        return True

    except Exception as e:
        error_str = str(e)

        # 42P01 = PostgreSQL code for "undefined_table" (relation does not exist).
        # PGRST = PostgREST error prefix. Either of these means we connected.
        if "42P01" in error_str or "does not exist" in error_str or "PGRST" in error_str:
            print("PASS  Supabase    — connection OK (no tables created yet — expected)")
            return True

        # 401 or JWT errors mean the anon key was rejected
        if "401" in error_str or "Invalid API key" in error_str or "jwt" in error_str.lower():
            print("FAIL  Supabase    — invalid anon key, check SUPABASE_ANON_KEY in .env")
            return False

        # Any other network or DNS failure
        print(f"FAIL  Supabase    — unexpected error ({type(e).__name__}: {e})")
        return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """
    Run all three connection tests and print a final summary.

    Calls test_claude, test_openai, and test_supabase in sequence, collects
    their results, then prints a summary. Exits with code 1 if any test
    failed so that CI pipelines can treat the run as a build failure.

    Parameters: none
    Returns: nothing (exits the process when done).
    """
    print("=" * 55)
    print("DocuBot — API Connection Tests")
    print("=" * 55)

    results: dict[str, bool] = {
        "Claude API": test_claude(),
        "OpenAI API": test_openai(),
        "Supabase":   test_supabase(),
    }

    print("=" * 55)

    all_passed = all(results.values())  # True only if every value is True

    if all_passed:
        print("ALL TESTS PASSED — ready to start Section 3.")
    else:
        failed_names = [name for name, passed in results.items() if not passed]
        print(f"FAILED: {', '.join(failed_names)}")
        print("Fix the issues above before moving to the next section.")
        sys.exit(1)  # non-zero exit tells any calling script that tests failed


if __name__ == "__main__":
    # __name__ == "__main__" only when this file is run directly (python test_connections.py).
    # It is False when another file imports this module, so the tests won't run on import.
    main()
