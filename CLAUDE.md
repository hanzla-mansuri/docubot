# DocuBot — Project Context

## What this project is
DocuBot is a RAG (Retrieval-Augmented Generation) support chatbot.
Businesses upload documents. Customers ask questions.
Claude API answers using ONLY the uploaded documents — no hallucination.
Built on Windows 11 · VS Code · Claude Code terminal only.
Pure native agent system — no external orchestrators.

## Current status
[UPDATE WITH /log AT END OF EVERY SESSION]
- Phase: 1 — Section 2 complete
- Last completed: Python 3.11 venv (backend\.venv), all packages installed, all 3 APIs PASS. Committed & pushed.
- Next task: Section 3 — Supabase database setup in browser
- Blocking issues: backend/.env.example not yet created — do this alongside Section 3

## Architecture in one paragraph
FastAPI backend (Python) receives file uploads and chat messages.
Documents are parsed, chunked, and embedded using OpenAI embeddings API,
then stored in Supabase with pgvector. When a user asks a question, the
backend embeds the question, finds the 5 most similar chunks via cosine
similarity search, builds a grounded prompt, and streams a response from
Claude API (claude-haiku-4-5). The React frontend handles the chat UI
and admin panel. Hosted on Render (backend) and Vercel (frontend).

## Tech stack
- Backend: Python 3.11, FastAPI, Supabase (pgvector)
- Embeddings: OpenAI text-embedding-3-small (1536 dimensions)
- LLM for user queries: Claude API, claude-haiku-4-5, console.anthropic.com
- Frontend: React + Vite, plain CSS
- Hosting: Render (backend free tier), Vercel (frontend free tier)

## Coding standards — always follow
- Every function: docstring (what it does, parameters, return value)
- Every file: module-level comment explaining its purpose
- Type hints on every function signature
- Handle all errors — never use bare except
- Proper HTTP status codes: 400, 404, 422, 500
- Never log API keys or secrets
- Validate all user inputs before use
- No hardcoded values — use config.py or environment variables

## Learning rules — I am a student developer
- Explain the concept BEFORE writing the code
- Add inline comments on any line a beginner might not understand
- When I hit an error: explain WHY it happens before showing the fix
- Point out which concept to study when introducing a new pattern

## File locations
- Backend: docubot\backend\
- Frontend: docubot\frontend\
- Slash agents: docubot\.claude\commands\
- Context files: docubot\.claude\context\
- Test data: docubot\data\

## Environment variables (in backend\.env — NEVER hardcode)
- ANTHROPIC_API_KEY — from console.anthropic.com (NOT claude.ai login)
- OPENAI_API_KEY — from platform.openai.com
- SUPABASE_URL — from Supabase project settings
- SUPABASE_ANON_KEY — from Supabase project settings (anon key)

## Important note on two Claude accounts
- claude.ai Pro → powers Claude Code, your build tool
- console.anthropic.com API → used BY the app to answer user questions
These are completely separate. Never confuse them.

## Agent system
All agents are plain .md files in .claude/commands/
Load specialist context with @.claude/context/[file].md
Save tokens: use /compact after long sessions, /clear between unrelated tasks
End every session with /log to update this file