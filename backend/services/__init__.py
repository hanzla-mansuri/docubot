# services/ — business logic layer for DocuBot.
# Each module in this package implements one stage of the RAG pipeline:
#   ingestion.py  → parse raw file bytes into plain text
#   (future) chunker.py   → split text into overlapping chunks
#   (future) embedder.py  → call OpenAI to embed chunks
