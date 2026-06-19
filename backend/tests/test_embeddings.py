# tests/test_embeddings.py — tests for embed_texts() and embed_single()
# in services/embeddings.py. Covers the third stage of the RAG pipeline:
# text chunks → OpenAI API → 1536-dim float vectors.
#
# Key mocking pattern used throughout:
#   patch("asyncio.to_thread", new_callable=AsyncMock)
#
# Why patch asyncio.to_thread?
# embed_texts() wraps the synchronous openai SDK call in asyncio.to_thread()
# to avoid blocking the event loop. In tests, we replace to_thread with an
# AsyncMock so we control what the "API call" returns or raises — no real
# network calls are ever made.
#
# Why reset _openai_client in every test?
# embeddings.py stores a module-level OpenAI client singleton. If one test
# creates it, the next test inherits it — including tests that patch the API key.
# The reset_openai_singleton fixture wipes it before and after each test.

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import openai
import pytest

import services.embeddings as emb_module
from config import settings
from services.embeddings import embed_single, embed_texts


# ── Error constructors ────────────────────────────────────────────────────────
# The openai SDK exception classes require httpx.Request / httpx.Response objects.
# These helpers build minimal but correctly typed instances for test use.

_OPENAI_URL = "https://api.openai.com/v1/embeddings"


def _req() -> httpx.Request:
    """Minimal httpx.Request pointing at the embeddings endpoint."""
    return httpx.Request("POST", _OPENAI_URL)


def _resp(status_code: int) -> httpx.Response:
    """Minimal httpx.Response with the given status code and a linked request."""
    return httpx.Response(status_code, request=_req())


def _rate_limit_error() -> openai.RateLimitError:
    return openai.RateLimitError(
        "rate limit exceeded", response=_resp(429), body=None
    )


def _auth_error() -> openai.AuthenticationError:
    return openai.AuthenticationError(
        "invalid api key", response=_resp(401), body=None
    )


def _permission_error() -> openai.PermissionDeniedError:
    return openai.PermissionDeniedError(
        "permission denied", response=_resp(403), body=None
    )


def _connection_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(message="connection failed", request=_req())


def _server_error() -> openai.InternalServerError:
    return openai.InternalServerError(
        "internal server error", response=_resp(500), body=None
    )


# ── Response factory ──────────────────────────────────────────────────────────


def _fake_response(n: int = 1, dims: int = 1536) -> MagicMock:
    """Build a mock OpenAI embeddings response with n vectors of `dims` dimensions.

    Args:
        n:    Number of embedding objects in response.data.
        dims: Dimension count of each vector (default 1536).

    Returns:
        MagicMock shaped like an openai.types.CreateEmbeddingResponse.
    """
    response = MagicMock()
    # Each item in response.data has an .embedding attribute (list of floats).
    # Values are 0.1 throughout — the exact values don't matter, only the shape.
    response.data = [MagicMock(embedding=[0.1] * dims) for _ in range(n)]
    response.usage.total_tokens = n * 10
    return response


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_openai_singleton():
    """Reset the module-level _openai_client before and after every test.

    Without this, a client created in one test persists into the next.
    Tests that patch settings.OPENAI_API_KEY would silently use a stale
    client created with a different key.
    """
    emb_module._openai_client = None
    yield
    emb_module._openai_client = None


# ═══════════════════════════════════════════════════════════════════════════════
# Input validation — pure logic, no async, no API calls
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmbedTextsValidation:
    """Tests for _validate_texts() called at the top of embed_texts().

    These are synchronous validation checks — no OpenAI API is contacted.
    pytest-asyncio runs async tests automatically; sync tests run normally.
    """

    async def test_embed_texts_none_input_raises_type_error_with_none_in_message(
        self,
    ) -> None:
        """Verifies that embed_texts raises TypeError with 'None' in the message when texts is None."""
        with pytest.raises(TypeError, match="None"):
            await embed_texts(None)  # type: ignore[arg-type]

    async def test_embed_texts_non_list_string_raises_type_error_with_str_in_message(
        self,
    ) -> None:
        """Verifies that embed_texts raises TypeError mentioning 'str' when a bare string is passed.

        A caller might accidentally pass a single string instead of a list — the
        error message must name the actual wrong type, not a generic message.
        """
        with pytest.raises(TypeError, match="str"):
            await embed_texts("not a list")  # type: ignore[arg-type]

    async def test_embed_texts_empty_list_raises_value_error(self) -> None:
        """Verifies that embed_texts raises ValueError with 'at least one' when texts is []."""
        with pytest.raises(ValueError, match="at least one"):
            await embed_texts([])

    async def test_embed_texts_batch_of_101_raises_value_error_mentioning_batch_size(
        self,
    ) -> None:
        """Verifies that embed_texts raises ValueError when texts has 101 items.

        The maximum batch size is 100. 101 strings must be rejected before any
        API call — no network round-trip should happen.
        """
        with pytest.raises(ValueError, match="batch size"):
            await embed_texts(["hello"] * 101)

    async def test_embed_texts_non_str_element_raises_type_error_with_index_and_type(
        self,
    ) -> None:
        """Verifies that embed_texts raises TypeError naming the index and type of a non-str element."""
        with pytest.raises(TypeError, match=r"texts\[1\].*int"):
            await embed_texts(["valid", 42, "also valid"])  # type: ignore[list-item]

    async def test_embed_texts_none_element_raises_type_error_with_index(self) -> None:
        """Verifies that embed_texts raises TypeError naming the index when an element is None."""
        with pytest.raises(TypeError, match=r"texts\[0\]"):
            await embed_texts([None])  # type: ignore[list-item]

    async def test_embed_texts_blank_string_raises_value_error_with_index(
        self,
    ) -> None:
        """Verifies that embed_texts raises ValueError naming the index for an empty string element."""
        with pytest.raises(ValueError, match=r"texts\[1\]"):
            await embed_texts(["valid chunk", ""])

    async def test_embed_texts_whitespace_only_string_raises_value_error_with_index(
        self,
    ) -> None:
        """Verifies that embed_texts raises ValueError for a whitespace-only string element.

        '   ' and '' must be treated identically — both are stripped to nothing
        and are useless for embedding.
        """
        with pytest.raises(ValueError, match=r"texts\[2\]"):
            await embed_texts(["chunk a", "chunk b", "   "])

    async def test_embed_texts_string_over_2000_chars_raises_value_error_with_index(
        self,
    ) -> None:
        """Verifies that embed_texts raises ValueError when any string exceeds 2000 characters."""
        oversized = "x" * 2001
        with pytest.raises(ValueError, match=r"texts\[0\].*2000"):
            await embed_texts([oversized])


# ═══════════════════════════════════════════════════════════════════════════════
# Happy path — successful embed calls with mocked API
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmbedTextsHappyPath:
    """Tests for successful embed_texts() calls — correct shape and order."""

    async def test_embed_texts_single_string_returns_one_vector_of_1536_dims(
        self,
    ) -> None:
        """Verifies that embed_texts returns [[float * 1536]] for a single input string."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = _fake_response(n=1)

            result = await embed_texts(["document chunk one"])

        assert isinstance(result, list)
        assert len(result) == 1
        assert len(result[0]) == 1536

    async def test_embed_texts_three_strings_returns_three_vectors_of_1536_dims(
        self,
    ) -> None:
        """Verifies that embed_texts returns three 1536-dim vectors for three input strings."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = _fake_response(n=3)

            result = await embed_texts(["chunk one", "chunk two", "chunk three"])

        assert len(result) == 3
        assert all(len(v) == 1536 for v in result)

    async def test_embed_texts_output_order_matches_input_order(self) -> None:
        """Verifies that output[i] corresponds to input[i] — order is never shuffled.

        Each vector is given a unique first element so positional identity
        can be verified without relying on stub values alone.
        """
        response = MagicMock()
        # Vector 0 starts with 1.0, vector 1 starts with 2.0 — uniquely identifiable.
        response.data = [
            MagicMock(embedding=[1.0] + [0.0] * 1535),
            MagicMock(embedding=[2.0] + [0.0] * 1535),
        ]
        response.usage.total_tokens = 20

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = response

            result = await embed_texts(["first chunk", "second chunk"])

        assert result[0][0] == 1.0, "first vector must correspond to first input"
        assert result[1][0] == 2.0, "second vector must correspond to second input"

    async def test_embed_texts_all_returned_values_are_floats(self) -> None:
        """Verifies that every element in every returned vector is a Python float."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = _fake_response(n=2)

            result = await embed_texts(["chunk a", "chunk b"])

        for vector in result:
            assert all(isinstance(v, float) for v in vector), (
                "every embedding value must be a Python float"
            )

    async def test_embed_texts_batch_of_100_strings_returns_100_vectors(
        self,
    ) -> None:
        """Verifies that embed_texts handles the maximum allowed batch size of 100."""
        texts = [f"chunk {i}" for i in range(100)]

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = _fake_response(n=100)

            result = await embed_texts(texts)

        assert len(result) == 100
        assert all(len(v) == 1536 for v in result)

    async def test_embed_texts_no_real_api_call_is_made(self) -> None:
        """Verifies that asyncio.to_thread is called (not bypassed) so no real network I/O occurs."""
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = _fake_response(n=1)

            await embed_texts(["test chunk"])

        # If to_thread was called, the real openai client.embeddings.create was
        # never invoked directly — all I/O went through our mock.
        mock_thread.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════════
# Retry and backoff behaviour
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmbedTextsRetry:
    """Tests for the exponential backoff retry loop."""

    async def test_embed_texts_http_429_three_times_then_success_returns_result(
        self,
    ) -> None:
        """Verifies that embed_texts retries after three 429 responses and returns on the fourth call.

        The retry loop allows up to 3 retries (4 total attempts). Three consecutive
        RateLimitErrors followed by a successful response must return the embeddings,
        not raise an exception.
        """
        err = _rate_limit_error()
        success = _fake_response(n=1)

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                # Attempts 1,2,3 fail; attempt 4 (final retry) succeeds.
                mock_thread.side_effect = [err, err, err, success]

                result = await embed_texts(["hello world"])

        assert len(result) == 1
        assert len(result[0]) == 1536

    async def test_embed_texts_http_429_three_times_sleep_called_with_1_2_4_seconds(
        self,
    ) -> None:
        """Verifies that asyncio.sleep is called with 1 s, 2 s, 4 s between retries.

        Backoff schedule: retry 1 → sleep 1 s, retry 2 → sleep 2 s, retry 3 → sleep 4 s.
        The initial attempt has no sleep before it.
        """
        err = _rate_limit_error()
        success = _fake_response(n=1)

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_thread.side_effect = [err, err, err, success]

                await embed_texts(["hello world"])

        # Extract the positional arg from each sleep call: [1, 2, 4]
        sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_args == [1, 2, 4], (
            f"Expected backoff sleeps [1, 2, 4], got {sleep_args}"
        )

    async def test_embed_texts_http_429_four_times_raises_runtime_error_after_retries(
        self,
    ) -> None:
        """Verifies that embed_texts raises RuntimeError after all three retries are exhausted.

        Four consecutive RateLimitErrors (initial attempt + 3 retries) must raise
        RuntimeError with 'rate limit' in the message, not propagate openai.RateLimitError.
        """
        err = _rate_limit_error()

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                mock_thread.side_effect = [err, err, err, err]

                with pytest.raises(RuntimeError, match="rate limit"):
                    await embed_texts(["hello world"])

    async def test_embed_texts_http_429_four_times_calls_to_thread_exactly_four_times(
        self,
    ) -> None:
        """Verifies that asyncio.to_thread is called exactly 4 times when all retries fail.

        1 initial attempt + 3 retries = 4 total calls. Not 3, not 5.
        """
        err = _rate_limit_error()

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                mock_thread.side_effect = [err, err, err, err]

                with pytest.raises(RuntimeError):
                    await embed_texts(["hello"])

        assert mock_thread.call_count == 4

    async def test_embed_texts_connection_error_retries_then_raises_runtime_error(
        self,
    ) -> None:
        """Verifies that APIConnectionError (DNS/firewall failure) is retried and eventually raises.

        APIConnectionError has no HTTP status code — it is a network-level failure
        before any response is received. It must be treated as transient (retried),
        not as a permanent error.
        """
        err = _connection_error()

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                mock_thread.side_effect = [err, err, err, err]

                with pytest.raises(RuntimeError, match="unavailable"):
                    await embed_texts(["hello"])

    async def test_embed_texts_server_error_5xx_retries_then_raises_runtime_error(
        self,
    ) -> None:
        """Verifies that InternalServerError (HTTP 500) triggers the retry loop."""
        err = _server_error()

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            with patch("asyncio.sleep", new_callable=AsyncMock):
                mock_thread.side_effect = [err, err, err, err]

                with pytest.raises(RuntimeError, match="unavailable"):
                    await embed_texts(["hello"])

    async def test_embed_texts_first_attempt_succeeds_sleep_never_called(
        self,
    ) -> None:
        """Verifies that asyncio.sleep is never called when the first attempt succeeds.

        Sleep only happens before retries — a successful initial call must not
        introduce any unnecessary delay.
        """
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_thread.return_value = _fake_response(n=1)

                await embed_texts(["hello"])

        mock_sleep.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# Non-retryable errors
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmbedTextsErrorHandling:
    """Tests for errors that must raise immediately with no retry."""

    async def test_embed_texts_http_401_raises_runtime_error_immediately(
        self,
    ) -> None:
        """Verifies that AuthenticationError (HTTP 401) raises RuntimeError without retrying.

        A wrong or revoked API key will never succeed on retry — the function must
        raise immediately to avoid unnecessary delay and wasted API cost.
        """
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_thread.side_effect = _auth_error()

                with pytest.raises(RuntimeError, match="invalid or missing"):
                    await embed_texts(["hello"])

        mock_sleep.assert_not_called()
        assert mock_thread.call_count == 1, "must not retry after 401"

    async def test_embed_texts_http_403_raises_runtime_error_immediately(
        self,
    ) -> None:
        """Verifies that PermissionDeniedError (HTTP 403) raises RuntimeError without retrying.

        A valid key without permission for this model will never succeed on retry.
        The error message must mention 'permission' and 'HTTP 403'.
        """
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_thread.side_effect = _permission_error()

                with pytest.raises(RuntimeError, match="permission"):
                    await embed_texts(["hello"])

        mock_sleep.assert_not_called()
        assert mock_thread.call_count == 1, "must not retry after 403"

    async def test_embed_texts_empty_api_key_raises_runtime_error_before_network_call(
        self,
    ) -> None:
        """Verifies that an empty OPENAI_API_KEY raises RuntimeError before any API call.

        The pre-flight key check in _get_client() runs before asyncio.to_thread is
        ever called. A network call with an empty key would return 401, but we
        want to catch misconfiguration early with a clear error.
        """
        with patch.object(settings, "OPENAI_API_KEY", ""):
            with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
                with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
                    await embed_texts(["hello"])

            mock_thread.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# Response shape validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmbedTextsResponseValidation:
    """Tests for checks on the OpenAI response object after a successful call."""

    async def test_embed_texts_fewer_embeddings_than_inputs_raises_runtime_error(
        self,
    ) -> None:
        """Verifies that embed_texts raises RuntimeError when OpenAI returns fewer embeddings than inputs.

        This would silently corrupt output order if unchecked — output[1] would
        correspond to input[2], not input[1]. The mismatch must be caught explicitly.
        """
        # 2 inputs but response only has 1 embedding
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = _fake_response(n=1)

            with pytest.raises(RuntimeError, match="1.*2|2.*1"):
                await embed_texts(["chunk one", "chunk two"])

    async def test_embed_texts_more_embeddings_than_inputs_raises_runtime_error(
        self,
    ) -> None:
        """Verifies that embed_texts raises RuntimeError when OpenAI returns more embeddings than inputs.

        len(response.data) != len(texts) covers both fewer-than and more-than.
        A '>' mismatch is as dangerous as '<' — the extra embedding would map to no input.
        """
        # 1 input but response has 3 embeddings
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = _fake_response(n=3)

            with pytest.raises(RuntimeError, match="3.*1|1.*3"):
                await embed_texts(["only one chunk"])

    async def test_embed_texts_wrong_embedding_dimension_raises_runtime_error_with_actual_dim(
        self,
    ) -> None:
        """Verifies that embed_texts raises RuntimeError naming the actual dimension when it is not 1536.

        If OpenAI changes the model's output dimension, the downstream pgvector
        insert would fail silently with corrupt data. The check must catch it here.
        """
        # Response returns 512-dim vectors instead of the expected 1536
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = _fake_response(n=1, dims=512)

            with pytest.raises(RuntimeError, match="512"):
                await embed_texts(["a chunk"])


# ═══════════════════════════════════════════════════════════════════════════════
# embed_single()
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmbedSingle:
    """Tests for embed_single() — the single-string convenience wrapper."""

    async def test_embed_single_happy_path_returns_flat_list_of_1536_floats(
        self,
    ) -> None:
        """Verifies that embed_single returns a flat list[float] of exactly 1536 values.

        Unlike embed_texts which returns list[list[float]], embed_single unwraps
        the outer list so the caller gets a bare vector ready for pgvector.
        """
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = _fake_response(n=1)

            result = await embed_single("What is the refund policy?")

        assert isinstance(result, list)
        assert len(result) == 1536
        # Flat list — not [[...]] nested
        assert isinstance(result[0], float)

    async def test_embed_single_delegates_to_embed_texts_with_one_element_list(
        self,
    ) -> None:
        """Verifies that embed_single calls asyncio.to_thread exactly once with a one-element input.

        embed_single wraps the string in a list before passing to embed_texts(),
        so the API always receives a batch of one — no special single-item path needed.
        """
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = _fake_response(n=1)

            await embed_single("user question here")

        mock_thread.assert_called_once()
        # Verify the input kwarg was a one-element list
        call_kwargs = mock_thread.call_args.kwargs
        assert call_kwargs.get("input") == ["user question here"]

    async def test_embed_single_blank_string_raises_value_error(self) -> None:
        """Verifies that embed_single raises ValueError for a blank string.

        Validation is delegated to embed_texts() which calls _validate_texts().
        The error message refers to texts[0] since the string is wrapped in a list.
        """
        with pytest.raises(ValueError, match="empty or whitespace"):
            await embed_single("   ")

    async def test_embed_single_none_input_raises_type_error(self) -> None:
        """Verifies that embed_single raises TypeError when text is None.

        None is wrapped to [None] and caught by the per-element type check in
        _validate_texts(), which raises TypeError naming texts[0].
        """
        with pytest.raises(TypeError, match=r"texts\[0\]"):
            await embed_single(None)  # type: ignore[arg-type]

    async def test_embed_single_string_over_2000_chars_raises_value_error(
        self,
    ) -> None:
        """Verifies that embed_single raises ValueError for a string exceeding 2000 characters."""
        with pytest.raises(ValueError, match="2000"):
            await embed_single("x" * 2001)
