# schemas.py — Pydantic data models (schemas) for DocuBot.
# These classes define the exact shape of data flowing in and out of the API.
# Pydantic validates all fields automatically — invalid data raises a 422 Unprocessable Entity.
# Field names match database column names exactly so Supabase responses map without transformation.

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class Document(BaseModel):
    """
    Represents a document uploaded by a business.

    Maps directly to the `documents` table in Supabase.
    The status field tracks where the document is in the processing pipeline.

    Args: id, business_id, filename, file_type, status, created_at — all required.
    Returns: a validated Document instance.
    Raises: ValidationError if status is not one of the four allowed values.
    """

    id: UUID
    business_id: UUID
    filename: str
    file_type: str
    # Literal restricts to exactly these four strings — any other value is a validation error
    status: Literal["pending", "processing", "ready", "error"]
    created_at: datetime


class Chunk(BaseModel):
    """
    Represents a single text chunk extracted from a document.

    Maps directly to the `chunks` table in Supabase.
    Each document is split into many chunks; vector embeddings are stored per chunk.

    Args: id, document_id, content, chunk_index, token_count — all required.
    Returns: a validated Chunk instance.
    """

    id: UUID
    document_id: UUID
    content: str
    chunk_index: int   # zero-based position of this chunk within its parent document
    token_count: int


class ChatRequest(BaseModel):
    """
    The JSON body sent by the frontend on POST /chat.

    Args:
        conversation_id: UUID of an existing conversation to continue, or None to start a new one.
        message: the user's question, maximum 2000 characters.
        business_id: identifies which business's document set to search against.
    Returns: a validated ChatRequest instance.
    Raises: ValidationError if message exceeds 2000 chars or business_id is missing.
    """

    # Optional[UUID] = None — this field can be omitted from the request body entirely.
    # A value of None tells the backend to create a fresh conversation and return its UUID.
    conversation_id: Optional[UUID] = None
    # Field(...) means required; max_length adds a validation rule Pydantic enforces automatically
    message: str = Field(..., min_length=1, max_length=2000)
    business_id: UUID


class ChatResponse(BaseModel):
    """
    The JSON body returned by POST /chat.

    Args: conversation_id, answer, sources — all required.
    Returns: a validated ChatResponse instance.

    conversation_id is always populated — either the existing one from the request
    or the newly created one if the request had conversation_id=None.
    """

    conversation_id: UUID
    answer: str
    sources: list[str]  # filenames of the documents used to generate the answer


class Message(BaseModel):
    """
    Represents a single message within a conversation.

    Maps directly to the `messages` table in Supabase.

    Args: id, conversation_id, role, content, created_at — all required.
    Returns: a validated Message instance.
    Raises: ValidationError if role is not exactly "user" or "assistant".
    """

    id: UUID
    conversation_id: UUID
    # Literal is stricter than str — rejects any value that isn't "user" or "assistant"
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
