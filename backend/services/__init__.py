# services/ — business logic layer for DocuBot.
# Each module in this package implements one stage of the RAG pipeline:
#   ingestion.py   → parse raw file bytes into plain text, chunk into tokens
#   embeddings.py  → call OpenAI to embed chunks and user queries
