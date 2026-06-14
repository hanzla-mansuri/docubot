# tests/test_schemas.py — tests for all Pydantic models in models/schemas.py.
#
# What Pydantic does automatically:
#   - Validates field types (e.g. "abc" is rejected for a UUID field)
#   - Enforces constraints (min_length, max_length, Literal values)
#   - Coerces compatible types (string "uuid..." → UUID object)
#   - Raises ValidationError for any violation — these tests confirm that contract.

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from models.schemas import ChatRequest, ChatResponse, Chunk, Document, Message

# ── Shared test data ──────────────────────────────────────────────────────────
# Using fixed UUIDs so test failure messages are predictable and readable.
SAMPLE_UUID = uuid4()
SAMPLE_UUID_2 = uuid4()
SAMPLE_DATETIME = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


# ── Document ──────────────────────────────────────────────────────────────────

class TestDocumentSchema:
    """Tests for the Document model (maps to the 'documents' table in Supabase)."""

    def _valid_doc(self, **overrides) -> dict:
        """Returns a dict of valid Document fields with optional overrides."""
        return {
            "id": SAMPLE_UUID,
            "business_id": SAMPLE_UUID_2,
            "filename": "annual_report.pdf",
            "file_type": "pdf",
            "status": "ready",
            "created_at": SAMPLE_DATETIME,
            **overrides,
        }

    def test_document_accepts_valid_data(self) -> None:
        """Verifies that Document accepts all required fields with valid values."""
        doc = Document(**self._valid_doc())

        assert doc.filename == "annual_report.pdf"
        assert doc.status == "ready"

    def test_document_accepts_all_four_status_values(self) -> None:
        """Verifies that all four allowed status values are accepted by the Literal field."""
        for status in ("pending", "processing", "ready", "error"):
            doc = Document(**self._valid_doc(status=status))
            assert doc.status == status

    def test_document_rejects_unlisted_status(self) -> None:
        """Verifies that a status not in the Literal raises ValidationError."""
        with pytest.raises(ValidationError):
            Document(**self._valid_doc(status="uploaded"))

    def test_document_rejects_empty_status(self) -> None:
        """Verifies that an empty string status raises ValidationError."""
        with pytest.raises(ValidationError):
            Document(**self._valid_doc(status=""))

    def test_document_rejects_invalid_uuid_for_id(self) -> None:
        """Verifies that a non-UUID string for id raises ValidationError."""
        with pytest.raises(ValidationError):
            Document(**self._valid_doc(id="not-a-uuid"))

    def test_document_coerces_string_uuid_to_uuid_type(self) -> None:
        """Verifies that a valid UUID string is coerced into a UUID object by Pydantic."""
        doc = Document(**self._valid_doc(id=str(SAMPLE_UUID)))

        assert isinstance(doc.id, UUID)

    def test_document_rejects_missing_required_fields(self) -> None:
        """Verifies that omitting any required field raises ValidationError."""
        with pytest.raises(ValidationError):
            Document(id=SAMPLE_UUID)  # type: ignore[call-arg]

    def test_document_rejects_missing_status(self) -> None:
        """Verifies that omitting status raises ValidationError (no default provided)."""
        data = self._valid_doc()
        del data["status"]
        with pytest.raises(ValidationError):
            Document(**data)


# ── Chunk ─────────────────────────────────────────────────────────────────────

class TestChunkSchema:
    """Tests for the Chunk model (maps to the 'chunks' table — one row per text chunk)."""

    def _valid_chunk(self, **overrides) -> dict:
        """Returns a dict of valid Chunk fields with optional overrides."""
        return {
            "id": SAMPLE_UUID,
            "document_id": SAMPLE_UUID_2,
            "content": "The refund policy allows returns within 30 days.",
            "chunk_index": 0,
            "token_count": 9,
            **overrides,
        }

    def test_chunk_accepts_valid_data(self) -> None:
        """Verifies that Chunk accepts all required fields with valid values."""
        chunk = Chunk(**self._valid_chunk())

        assert chunk.content == "The refund policy allows returns within 30 days."
        assert chunk.chunk_index == 0

    def test_chunk_accepts_zero_chunk_index(self) -> None:
        """Verifies chunk_index=0 is accepted (first chunk in a document)."""
        chunk = Chunk(**self._valid_chunk(chunk_index=0))

        assert chunk.chunk_index == 0

    def test_chunk_accepts_large_chunk_index(self) -> None:
        """Verifies that large chunk_index values are accepted for long documents."""
        chunk = Chunk(**self._valid_chunk(chunk_index=9999))

        assert chunk.chunk_index == 9999

    def test_chunk_accepts_empty_string_content(self) -> None:
        """Verifies that content="" is accepted — no min_length constraint on content."""
        chunk = Chunk(**self._valid_chunk(content=""))

        assert chunk.content == ""

    def test_chunk_rejects_string_chunk_index(self) -> None:
        """Verifies that a non-integer chunk_index raises ValidationError."""
        with pytest.raises(ValidationError):
            Chunk(**self._valid_chunk(chunk_index="first"))

    def test_chunk_rejects_float_chunk_index(self) -> None:
        """Verifies that a float chunk_index raises ValidationError (must be int)."""
        with pytest.raises(ValidationError):
            Chunk(**self._valid_chunk(chunk_index=1.5))

    def test_chunk_rejects_missing_content(self) -> None:
        """Verifies that omitting content raises ValidationError."""
        data = self._valid_chunk()
        del data["content"]
        with pytest.raises(ValidationError):
            Chunk(**data)

    def test_chunk_rejects_invalid_document_id(self) -> None:
        """Verifies that a non-UUID string for document_id raises ValidationError."""
        with pytest.raises(ValidationError):
            Chunk(**self._valid_chunk(document_id="not-a-uuid"))


# ── ChatRequest ───────────────────────────────────────────────────────────────

class TestChatRequestSchema:
    """Tests for the ChatRequest model (JSON body sent to POST /chat)."""

    def _valid_request(self, **overrides) -> dict:
        """Returns a dict of valid ChatRequest fields with optional overrides."""
        return {
            "message": "What is the return policy?",
            "business_id": SAMPLE_UUID,
            **overrides,
        }

    def test_chat_request_accepts_valid_data_without_conversation_id(self) -> None:
        """Verifies that ChatRequest works without conversation_id (starts new conversation)."""
        req = ChatRequest(**self._valid_request())

        assert req.conversation_id is None
        assert req.message == "What is the return policy?"

    def test_chat_request_accepts_valid_data_with_conversation_id(self) -> None:
        """Verifies that ChatRequest accepts an optional conversation_id UUID."""
        req = ChatRequest(**self._valid_request(conversation_id=SAMPLE_UUID_2))

        assert req.conversation_id == SAMPLE_UUID_2

    def test_chat_request_defaults_conversation_id_to_none(self) -> None:
        """Verifies that conversation_id defaults to None when omitted from the body."""
        req = ChatRequest(**self._valid_request())

        assert req.conversation_id is None

    def test_chat_request_rejects_empty_message(self) -> None:
        """Verifies that message="" raises ValidationError (min_length=1)."""
        with pytest.raises(ValidationError):
            ChatRequest(**self._valid_request(message=""))

    def test_chat_request_accepts_single_char_message(self) -> None:
        """Verifies that a single-character message is accepted (boundary: min_length=1)."""
        req = ChatRequest(**self._valid_request(message="?"))

        assert req.message == "?"

    def test_chat_request_accepts_exactly_2000_char_message(self) -> None:
        """Verifies that a 2000-character message is accepted (boundary: max_length=2000)."""
        req = ChatRequest(**self._valid_request(message="a" * 2000))

        assert len(req.message) == 2000

    def test_chat_request_rejects_message_over_2000_chars(self) -> None:
        """Verifies that a 2001-character message raises ValidationError (max_length=2000)."""
        with pytest.raises(ValidationError):
            ChatRequest(**self._valid_request(message="x" * 2001))

    def test_chat_request_accepts_unicode_and_special_chars(self) -> None:
        """Verifies that message accepts unicode and punctuation — real user questions do."""
        message = "What's the cost? — £100 → €85 (50% off) 🎉"
        req = ChatRequest(**self._valid_request(message=message))

        assert "£" in req.message
        assert "€" in req.message

    def test_chat_request_rejects_missing_message(self) -> None:
        """Verifies that omitting message raises ValidationError (it is required)."""
        with pytest.raises(ValidationError):
            ChatRequest(business_id=SAMPLE_UUID)  # type: ignore[call-arg]

    def test_chat_request_rejects_missing_business_id(self) -> None:
        """Verifies that omitting business_id raises ValidationError (it is required)."""
        with pytest.raises(ValidationError):
            ChatRequest(message="Hello")  # type: ignore[call-arg]

    def test_chat_request_rejects_invalid_business_id(self) -> None:
        """Verifies that a non-UUID business_id raises ValidationError."""
        with pytest.raises(ValidationError):
            ChatRequest(**self._valid_request(business_id="not-a-uuid"))


# ── ChatResponse ──────────────────────────────────────────────────────────────

class TestChatResponseSchema:
    """Tests for the ChatResponse model (JSON body returned by POST /chat)."""

    def _valid_response(self, **overrides) -> dict:
        """Returns a dict of valid ChatResponse fields with optional overrides."""
        return {
            "conversation_id": SAMPLE_UUID,
            "answer": "Returns are accepted within 30 days with a receipt.",
            "sources": ["policy.pdf"],
            **overrides,
        }

    def test_chat_response_accepts_valid_data(self) -> None:
        """Verifies that ChatResponse accepts all required fields with valid values."""
        resp = ChatResponse(**self._valid_response())

        assert resp.answer == "Returns are accepted within 30 days with a receipt."
        assert resp.sources == ["policy.pdf"]

    def test_chat_response_accepts_empty_sources_list(self) -> None:
        """Verifies that sources=[] is accepted (no documents found is a valid state)."""
        resp = ChatResponse(**self._valid_response(sources=[]))

        assert resp.sources == []

    def test_chat_response_accepts_multiple_sources(self) -> None:
        """Verifies that all source filenames are stored when multiple sources provided."""
        sources = ["policy.pdf", "terms.pdf", "faq.pdf", "guide.pdf", "manual.pdf"]
        resp = ChatResponse(**self._valid_response(sources=sources))

        assert len(resp.sources) == 5
        assert "faq.pdf" in resp.sources

    def test_chat_response_coerces_string_conversation_id_to_uuid(self) -> None:
        """Verifies that a valid UUID string is coerced to a UUID object by Pydantic."""
        resp = ChatResponse(**self._valid_response(conversation_id=str(SAMPLE_UUID)))

        assert isinstance(resp.conversation_id, UUID)

    def test_chat_response_rejects_missing_answer(self) -> None:
        """Verifies that omitting answer raises ValidationError."""
        data = self._valid_response()
        del data["answer"]
        with pytest.raises(ValidationError):
            ChatResponse(**data)

    def test_chat_response_rejects_missing_conversation_id(self) -> None:
        """Verifies that omitting conversation_id raises ValidationError."""
        data = self._valid_response()
        del data["conversation_id"]
        with pytest.raises(ValidationError):
            ChatResponse(**data)

    def test_chat_response_rejects_invalid_conversation_id(self) -> None:
        """Verifies that a non-UUID conversation_id raises ValidationError."""
        with pytest.raises(ValidationError):
            ChatResponse(**self._valid_response(conversation_id="not-a-uuid"))


# ── Message ───────────────────────────────────────────────────────────────────

class TestMessageSchema:
    """Tests for the Message model (maps to the 'messages' table in Supabase)."""

    def _valid_message(self, **overrides) -> dict:
        """Returns a dict of valid Message fields with optional overrides."""
        return {
            "id": SAMPLE_UUID,
            "conversation_id": SAMPLE_UUID_2,
            "role": "user",
            "content": "What is the return policy?",
            "created_at": SAMPLE_DATETIME,
            **overrides,
        }

    def test_message_accepts_user_role(self) -> None:
        """Verifies that role='user' is accepted."""
        msg = Message(**self._valid_message(role="user"))

        assert msg.role == "user"

    def test_message_accepts_assistant_role(self) -> None:
        """Verifies that role='assistant' is accepted."""
        msg = Message(**self._valid_message(role="assistant"))

        assert msg.role == "assistant"

    def test_message_rejects_system_role(self) -> None:
        """Verifies that role='system' raises ValidationError (not in Literal)."""
        with pytest.raises(ValidationError):
            Message(**self._valid_message(role="system"))

    def test_message_rejects_uppercase_user_role(self) -> None:
        """Verifies that role='USER' raises ValidationError (Literal is case-sensitive)."""
        with pytest.raises(ValidationError):
            Message(**self._valid_message(role="USER"))

    def test_message_rejects_all_invalid_roles(self) -> None:
        """Verifies that every non-allowed role string raises ValidationError."""
        for bad_role in ("bot", "admin", "system", "USER", "ASSISTANT", ""):
            with pytest.raises(ValidationError, match=""):
                Message(**self._valid_message(role=bad_role))  # type: ignore[arg-type]

    def test_message_rejects_missing_role(self) -> None:
        """Verifies that omitting role raises ValidationError."""
        data = self._valid_message()
        del data["role"]
        with pytest.raises(ValidationError):
            Message(**data)

    def test_message_accepts_empty_content(self) -> None:
        """Verifies that content="" is accepted — no min_length on message content."""
        msg = Message(**self._valid_message(content=""))

        assert msg.content == ""

    def test_message_coerces_string_id_to_uuid(self) -> None:
        """Verifies that a valid UUID string for id is coerced to a UUID object."""
        msg = Message(**self._valid_message(id=str(SAMPLE_UUID)))

        assert isinstance(msg.id, UUID)

    def test_message_rejects_invalid_id(self) -> None:
        """Verifies that a non-UUID string for id raises ValidationError."""
        with pytest.raises(ValidationError):
            Message(**self._valid_message(id="not-a-uuid"))
