# Test Patterns for DocuBot

## File structure
tests/
  test_ingestion.py    ← tests for services/ingestion.py
  test_rag.py          ← tests for services/rag_pipeline.py
  test_documents.py    ← tests for routers/documents.py
  test_chat.py         ← tests for routers/chat.py
  conftest.py          ← shared fixtures

## Fixture patterns
@pytest.fixture
def sample_pdf_bytes():
    """Returns minimal valid PDF bytes for upload testing."""
    return b"%PDF-1.4 minimal pdf content"

@pytest.fixture
def mock_openai_embedding():
    """Returns a fake 1536-dimension embedding vector."""
    return [0.1] * 1536

## Mocking external services
from unittest.mock import patch, MagicMock

@patch('services.embeddings.openai_client.embeddings.create')
def test_embed_texts(mock_embed):
    mock_embed.return_value = MagicMock(data=[MagicMock(embedding=[0.1]*1536)])
    result = embed_texts(["hello"])
    assert len(result[0]) == 1536

## FastAPI test client
from fastapi.testclient import TestClient
from main import app
client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

## Test naming convention
test_[function]_[condition]_[expected_result]
Example: test_chunk_text_with_empty_string_raises_value_error