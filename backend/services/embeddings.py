# services/embeddings.py — third stage of DocuBot's RAG ingestion pipeline.
# Responsibility: convert plain-text strings (document chunks or user queries)
# into 1536-dimensional float vectors by calling the OpenAI text-embedding-3-small API.
# What it does NOT do: write to the database — that is the upload route's job.
#
# IMPORTANT — both public functions are async but wrap a synchronous OpenAI SDK call
# via asyncio.to_thread() so the FastAPI event loop is never blocked during I/O.
# The caller does:
#   vectors = await embed_texts(chunks)   # batch — ingestion pipeline
#   vector  = await embed_single(query)   # single — query embedding at search time

import asyncio
import logging

import openai

from config import settings

logger = logging.getLogger(__name__)

# Embedding model — one constant to update if OpenAI releases a successor.
_EMBEDDING_MODEL = "text-embedding-3-small"

# Number of dimensions returned by text-embedding-3-small.
_EXPECTED_DIMS = 1536

# Maximum strings per batch call. OpenAI allows larger batches, but this cap
# bounds cost and memory per request and matches the RAG pattern context (max 100).
_MAX_BATCH_SIZE = 100

# Per-string character ceiling — a rough proxy for the 8192-token OpenAI per-item
# limit that avoids needing tiktoken here. 2000 ASCII chars ≈ 500 tokens.
_MAX_STRING_CHARS = 2_000

# Retry policy for transient failures (429, 5xx, connection error, timeout).
# Retry 0 → sleep 1 s, retry 1 → sleep 2 s, retry 2 → sleep 4 s, then raise.
_MAX_RETRIES = 3
_BACKOFF_SECONDS = [1, 2, 4]  # 0-indexed: _BACKOFF_SECONDS[retry_num - 1]

# Module-level OpenAI client singleton — created once via _get_client().
# Reusing one client avoids repeated SSL handshake overhead on every embed call.
_openai_client: openai.OpenAI | None = None


def _get_client() -> openai.OpenAI:
    """
    Return the module-level OpenAI sync client, creating it on first call.

    Lazy initialisation so a missing API key raises a clear RuntimeError at
    call time rather than a confusing error at import time.

    timeout=30.0 is passed to the client constructor so the underlying httpx
    transport terminates the HTTP connection after 30 seconds and raises
    openai.APITimeoutError. This is the correct approach — using asyncio.wait_for()
    instead would cancel the coroutine but leave the worker thread running (thread leak).

    Args: none.

    Returns:
        openai.OpenAI: Configured sync client shared across all embed calls.

    Raises:
        RuntimeError: If OPENAI_API_KEY is missing or an empty string.
    """
    global _openai_client

    # Pre-flight check: catch a misconfigured key before any network call.
    if not settings.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    if _openai_client is None:
        # openai.OpenAI is the synchronous client — NOT openai.AsyncOpenAI.
        # The sync client is wrapped in asyncio.to_thread() in embed_texts()
        # so the event loop stays free. Using AsyncOpenAI here would be wrong
        # because asyncio.to_thread() expects a regular blocking callable.
        _openai_client = openai.OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=30.0,  # httpx-level timeout; raises APITimeoutError when hit
        )

    return _openai_client


def _validate_texts(texts: object) -> None:
    """
    Validate the texts argument before making any API call.

    Checks run in a fixed order (None → type → empty → size cap → per-element)
    so error messages are always specific and predictable.

    Args:
        texts: Value passed by the caller — typed as object so mypy does not
               complain about isinstance checks on a narrower type.

    Raises:
        TypeError:  texts is None, not a list, or contains a non-str element.
        ValueError: texts is empty, exceeds the batch cap, or contains a string
                    that is blank after stripping whitespace or too long.
    """
    if texts is None:
        raise TypeError("texts must be a list, got None")

    if not isinstance(texts, list):
        raise TypeError(f"texts must be a list, got {type(texts).__name__}")

    if len(texts) == 0:
        raise ValueError("texts must contain at least one string")

    if len(texts) > _MAX_BATCH_SIZE:
        raise ValueError(f"texts exceeds maximum batch size of {_MAX_BATCH_SIZE}")

    for i, item in enumerate(texts):
        if not isinstance(item, str):
            raise TypeError(f"texts[{i}] must be a str, got {type(item).__name__}")

        # strip() removes whitespace before the emptiness check so that "   "
        # is rejected the same way as "" — both are useless for embedding.
        if not item.strip():
            raise ValueError(f"texts[{i}] is empty or whitespace")

        if len(item) > _MAX_STRING_CHARS:
            raise ValueError(
                f"texts[{i}] exceeds maximum length of {_MAX_STRING_CHARS} characters"
            )


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Convert a list of plain-text strings into 1536-dimensional embedding vectors.

    Sends a single batched request to the OpenAI text-embedding-3-small API.
    Transient failures (rate limits, server errors, timeouts, connection errors)
    are retried up to three times with exponential backoff (1 s → 2 s → 4 s).
    Non-retryable errors (auth, permission, bad request) raise immediately.

    The OpenAI SDK call is synchronous — it runs in a thread pool via
    asyncio.to_thread() so the FastAPI event loop is never blocked.
    asyncio.sleep() is used for backoff so the loop stays responsive to other
    requests while waiting between retries.

    Args:
        texts: Non-empty list of plain-text strings (document chunks).
               Each string must be non-blank and ≤ 2000 characters.
               Maximum 100 strings per call.

    Returns:
        list[list[float]]: One 1536-float vector per input string, in the same
        order as the input. Values are 64-bit Python floats (IEEE 754 double).
        NOTE: cast each vector to float32 before inserting into Supabase pgvector,
        which stores vectors as 32-bit floats.

    Raises:
        TypeError:    texts is None, not a list, or contains a non-str element.
        ValueError:   Input validation failure (blank, too long, too many items).
        RuntimeError: OPENAI_API_KEY not configured; API call failed after all
                      retries; response shape unexpected (wrong count or dims);
                      non-retryable HTTP error (400, 401, 403).
    """
    _validate_texts(texts)
    client = _get_client()

    last_error: Exception | None = None

    # range(_MAX_RETRIES + 1) gives 0, 1, 2, 3.
    # retry_num 0 = initial attempt (no sleep before it).
    # retry_num 1, 2, 3 = retries (sleep before each).
    # If retry_num reaches 3 and last_error is set, we fall through to the raise below.
    for retry_num in range(_MAX_RETRIES + 1):
        if retry_num > 0:
            # _BACKOFF_SECONDS is 0-indexed by retry number:
            #   retry 1 → sleep 1 s, retry 2 → sleep 2 s, retry 3 → sleep 4 s
            sleep_seconds = _BACKOFF_SECONDS[retry_num - 1]
            logger.warning(
                "OpenAI embedding request failed — retry %d/%d in %ds.",
                retry_num,
                _MAX_RETRIES,
                sleep_seconds,
            )
            # asyncio.sleep yields to the event loop — time.sleep() would freeze
            # the entire FastAPI server for all users during the backoff wait.
            await asyncio.sleep(sleep_seconds)

        try:
            # asyncio.to_thread() moves the blocking SDK call to a worker thread
            # from Python's default ThreadPoolExecutor, keeping the event loop free.
            response = await asyncio.to_thread(
                client.embeddings.create,
                model=_EMBEDDING_MODEL,
                input=texts,
            )

        except openai.AuthenticationError as exc:
            # 401 — key is wrong or revoked. No point retrying.
            raise RuntimeError("OpenAI API key is invalid or missing") from exc

        except openai.PermissionDeniedError as exc:
            # 403 — key valid but lacks permission for this model. No point retrying.
            raise RuntimeError(
                "OpenAI API key does not have permission to use this model (HTTP 403)"
            ) from exc

        except openai.BadRequestError as exc:
            # 400 — malformed request (e.g. input rejected at API level). No point retrying.
            raise RuntimeError("OpenAI rejected the request (HTTP 400)") from exc

        except (openai.RateLimitError, openai.InternalServerError) as exc:
            # 429 or 5xx — transient; retry with backoff.
            last_error = exc
            continue

        except (
            openai.APIConnectionError,
            openai.APITimeoutError,
        ) as exc:
            # Network-level failure (DNS, firewall) or 30-second timeout — both transient.
            # APIConnectionError has no HTTP status code; APITimeoutError is raised by
            # the httpx transport when the timeout=30.0 wall-clock limit is hit.
            last_error = exc
            continue

        except openai.APIStatusError as exc:
            # Catch-all for any HTTP status not covered by the specific types above.
            # Retry on 5xx (defensive — InternalServerError should catch these first);
            # raise immediately on unexpected 4xx errors.
            if exc.status_code >= 500:
                last_error = exc
                continue
            raise RuntimeError(
                f"OpenAI API returned an unexpected error (HTTP {exc.status_code})"
            ) from exc

        # ── Response validation ──────────────────────────────────────────────

        # The API must return exactly one embedding per input string.
        # Using != (not just <) catches both fewer-than and more-than mismatches,
        # either of which would corrupt the output order if silently accepted.
        if len(response.data) != len(texts):
            raise RuntimeError(
                f"OpenAI returned {len(response.data)} embeddings for {len(texts)} inputs"
            )

        embeddings: list[list[float]] = []
        for item in response.data:
            vector: list[float] = item.embedding

            # Each vector must be exactly 1536 floats — a dimension mismatch means
            # an API change or a badly constructed mock in tests.
            if len(vector) != _EXPECTED_DIMS:
                raise RuntimeError(
                    f"Unexpected embedding dimension: {len(vector)}"
                    f" (expected {_EXPECTED_DIMS})"
                )

            embeddings.append(vector)

        # Log token usage for cost tracking — never log chunk text content.
        # getattr guards against API responses that omit the usage field entirely.
        total_tokens = getattr(response.usage, "total_tokens", 0)
        logger.info(
            "Embedded %d texts using %d tokens (model=%s).",
            len(texts),
            total_tokens,
            _EMBEDDING_MODEL,
        )

        return embeddings

    # ── All retries exhausted ────────────────────────────────────────────────
    # last_error is always set here: the loop reaches this point only via
    # 'continue', which always assigns last_error first.
    # Explicit check instead of assert — assert is stripped by Python's -O flag.
    if last_error is None:
        raise RuntimeError("internal: retry loop exited without setting last_error")

    if isinstance(last_error, openai.RateLimitError):
        raise RuntimeError(
            f"OpenAI rate limit exceeded after {_MAX_RETRIES} retries"
        ) from last_error

    if isinstance(last_error, openai.APITimeoutError):
        raise RuntimeError(
            f"OpenAI request timed out after {_MAX_RETRIES} retries"
        ) from last_error

    raise RuntimeError(
        f"OpenAI API unavailable after {_MAX_RETRIES} retries"
    ) from last_error


async def embed_single(text: str) -> list[float]:
    """
    Convert a single plain-text string into a 1536-dimensional embedding vector.

    Convenience wrapper around embed_texts() for the query-embedding path:
    when a user sends a question, it must be embedded as a single string before
    cosine similarity search can find matching document chunks.

    Args:
        text: A non-blank plain-text string ≤ 2000 characters.

    Returns:
        list[float]: A single 1536-float vector. Same float64 / float32 note
        as embed_texts() applies if storing in pgvector.

    Raises:
        TypeError:    text is None or not a str (delegated to embed_texts).
        ValueError:   text is blank or too long (delegated to embed_texts).
        RuntimeError: Any API or response-shape error (delegated to embed_texts).
    """
    # Wrap in a list so _validate_texts() and the batch API call work unchanged.
    # [0] unwraps the single-element result list back to a bare vector.
    results = await embed_texts([text])
    return results[0]
