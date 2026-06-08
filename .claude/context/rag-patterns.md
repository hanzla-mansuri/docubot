# RAG Patterns for DocuBot

## Chunking strategy
- Size: 512 tokens per chunk
- Overlap: 50 tokens (preserves sentence context across boundaries)
- Use tiktoken cl100k_base encoder for accurate token counting
- Split on sentence boundaries when possible

## Embedding
- Model: text-embedding-3-small (1536 dimensions)
- Batch embed for efficiency (max 100 texts per API call)
- Store as VECTOR(1536) in Supabase pgvector

## Similarity search
- Method: cosine similarity via pgvector <=> operator
- Retrieve top 5 chunks (TOP_K_RESULTS env var)
- Minimum similarity threshold: 0.75 (below = "I don't know")

## Grounded system prompt template
SYSTEM:
You are a helpful support assistant.
Answer ONLY using the CONTEXT below.
If the answer is not in the CONTEXT, respond exactly:
"I don't have information about that in my knowledge base.
Please contact support for help with this question."
Always end your answer with: Source: [document name]
Be concise. Be friendly. Never invent information.

CONTEXT:
{chunk_1} — Source: {doc_name_1}
{chunk_2} — Source: {doc_name_2}
{chunk_3} — Source: {doc_name_3}

## Streaming response
Use Anthropic SDK streaming: client.messages.stream()
Yield tokens as they arrive via FastAPI StreamingResponse
Content-Type: text/event-stream