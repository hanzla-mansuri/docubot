-- DocuBot Database Schema
-- Run in Supabase SQL Editor in this exact order

-- Step 1: Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Step 2: Documents table
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  file_type TEXT NOT NULL,
  size_bytes INTEGER,
  status TEXT DEFAULT 'processing',
  chunk_count INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Step 3: Chunks table with vector embeddings
CREATE TABLE chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  embedding VECTOR(1536),
  chunk_index INTEGER,
  token_count INTEGER,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ivfflat index for fast cosine similarity search
CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Step 4: Conversations table
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Step 5: Messages table
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  source_chunks UUID[],
  feedback TEXT CHECK (feedback IN ('positive', 'negative')),
  tokens_used INTEGER,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Step 6: Vector similarity search function
CREATE OR REPLACE FUNCTION search_chunks(
  query_embedding VECTOR(1536), match_count INT DEFAULT 5
)
RETURNS TABLE (id UUID, document_id UUID, content TEXT,
               similarity FLOAT, document_name TEXT)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT c.id, c.document_id, c.content,
    1 - (c.embedding <=> query_embedding) AS similarity,
    d.name AS document_name
  FROM chunks c JOIN documents d ON c.document_id = d.id
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END; $$;