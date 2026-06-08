# DocuBot — Master Project Plan v3
### RAG Support Chatbot · Windows 11 · VS Code + Claude Code Terminal Only
### Native Multi-Agent System — No Third-Party Orchestrators

---

> **One rule:** Everything happens inside VS Code terminal using Claude Code.
> All agents, context, and memory live inside your project folder as plain markdown files.
> No Ruflo. No external orchestrators. No third-party packages with hidden code.
> You control every agent. You understand every file.

---

## Table of Contents

1. [Project Summary](#1-project-summary)
2. [Your Tools — What Each One Does](#2-your-tools--what-each-one-does)
3. [Native Agent System — How It Works](#3-native-agent-system--how-it-works)
4. [Token Saving Strategy](#4-token-saving-strategy)
5. [Project Folder Structure](#5-project-folder-structure)
6. [CLAUDE.md — Your Project Brain](#6-claudemd--your-project-brain)
7. [AGENTS.md — Model Routing Table](#7-agentsmd--model-routing-table)
8. [Slash Command Agents — Full Content](#8-slash-command-agents--full-content)
9. [Tech Stack](#9-tech-stack)
10. [System Architecture](#10-system-architecture)
11. [Full Features List](#11-full-features-list)
12. [Database & Data Models](#12-database--data-models)
13. [API Endpoints](#13-api-endpoints)
14. [Build Phases](#14-build-phases)
15. [Free Datasets](#15-free-datasets)
16. [Deployment Plan](#16-deployment-plan)
17. [Portfolio & Monetization](#17-portfolio--monetization)
18. [Glossary](#18-glossary)

---

## 1. Project Summary

| Field | Detail |
|---|---|
| **Project Name** | DocuBot — AI Support Assistant |
| **Type** | RAG (Retrieval-Augmented Generation) Chatbot |
| **Target Market** | Small businesses, SaaS companies, e-commerce |
| **Core Value** | Answer customer questions from YOUR documents — grounded, cited, no hallucination |
| **Build Environment** | Windows 11 · VS Code · Claude Code in terminal only |
| **Agent System** | Native — 12 slash commands + CLAUDE.md memory + AGENTS.md routing |
| **Build Time** | 8–10 weeks |
| **Stack** | Python · FastAPI · Claude API · Supabase pgvector · React · Vercel |
| **Portfolio Goal** | Upwork contracts + deep AI/LLM learning |

---

## 2. Your Tools — What Each One Does

### Claude Pro ($20/month — already yours)
- Powers Claude Code in your terminal
- 200K token context window — can load your entire codebase
- Does NOT include API access for your app's users (separate Console account)

### Claude Code (terminal agent)
```powershell
npm install -g @anthropic-ai/claude-code
claude   # start a session
```
- Reads and writes your actual project files
- Accepts `/slash` commands you define as `.md` files
- Has built-in `/compact` to compress context and save tokens
- Has built-in `/clear` to reset context when starting fresh
- Everything Claude Code does is visible — no hidden behavior

### VS Code (your editor)
- Open `docubot/` folder here
- Claude Code runs in the integrated terminal (Ctrl+`)
- All agent `.md` files are visible and editable by you
- Thunder Client extension for API testing

### Why NO external orchestrators (Ruflo, claude-flow, etc.)
These tools run npm packages with preinstall scripts that execute before you
can review the code. Ruflo specifically had:
- Hidden prompt injections in MCP tool descriptions
- API keys passed to every child process
- Obfuscated install scripts
- Fake "enterprise" features that were stubs

Our native system does the same job with zero risk:
- Every agent is a plain `.md` file YOU wrote and can read
- No npm packages with hidden behavior
- No MCP servers you didn't set up yourself
- Complete transparency — you understand every piece

---

## 3. Native Agent System — How It Works

### The three layers of your agent system

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1 — MEMORY  (auto-loaded every session)              │
│                                                             │
│  CLAUDE.md          Project context, current status,        │
│                     coding standards, your learning rules   │
│                                                             │
│  AGENTS.md          Which slash command to use when,        │
│                     token-saving routing rules              │
└─────────────────────────────────────────────────────────────┘
                           ↓ loaded automatically
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2 — SLASH COMMANDS  (.claude/commands/*.md)          │
│                                                             │
│  /spec    /eval    /code    /review    /test                │
│  /secure  /inject  /check  /debug     /perf                 │
│  /log     /narrate /save   /load                            │
│                                                             │
│  Each is a plain .md file with a focused prompt.           │
│  Type /command in Claude Code terminal → fires the agent   │
└─────────────────────────────────────────────────────────────┘
                           ↓ called by slash commands
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3 — CONTEXT FILES  (.claude/context/*.md)            │
│                                                             │
│  python-standards.md    React standards, FastAPI patterns  │
│  rag-patterns.md        Chunking, embedding, retrieval      │
│  security-rules.md      Input validation, OWASP top 10     │
│  test-patterns.md       Pytest fixtures, mock patterns      │
│                                                             │
│  Agents @-mention these files to load specialist context   │
│  without re-explaining every time → saves tokens           │
└─────────────────────────────────────────────────────────────┘
```

### The standard build loop (every single feature)

```
1.  /spec <feature>     → generates full specification
2.  /eval               → pressure-tests the spec
3.  /code <task>        → writes the code
4.  /review @file       → reviews for correctness + security
5.  /test <function>    → writes pytest tests
6.  /secure @file       → penetration tests the endpoint
7.  git commit          → checkpoint before moving on
8.  /log                → updates CLAUDE.md current status
```

### How @-mentions save tokens

Instead of pasting long context into every prompt, use `@`:
```
@CLAUDE.md              loads project context
@backend/services/      loads entire services folder
@.claude/context/rag-patterns.md   loads RAG specialist knowledge
```

Claude Code reads the referenced files directly —
you don't paste them, so they don't fill up your context window
with things Claude already has access to.

---

## 4. Token Saving Strategy

This is your "Ruflo replacement" for cost efficiency — all native.

### Rule 1 — Use /compact aggressively
```
/compact
```
Run this when your session gets long (after 30+ back-and-forth exchanges).
Claude Code compresses the conversation history while keeping key decisions.
Cuts context usage by ~60% mid-session without losing important context.

### Rule 2 — /clear between unrelated tasks
```
/clear
```
Starting a completely new task? Clear the context.
Then reload only what you need with @-mentions.
Fresh context = fewer tokens on every message.

### Rule 3 — Focused slash commands (small, specific prompts)
Each slash command does ONE job with ONE focused prompt.
Avoid: "review my code AND write tests AND check security"
Instead: `/review` → fix issues → `/test` → fix issues → `/secure`
One agent, one job, smaller context each time.

### Rule 4 — Load context files on demand
Don't paste your entire codebase at the start of every session.
Use @-mentions to pull in only the files relevant to the current task:
```
# Working on ingestion? Load only ingestion-related files:
@backend/services/ingestion.py @.claude/context/rag-patterns.md

# NOT this (loads everything, burns tokens):
@backend/
```

### Rule 5 — AGENTS.md routing
The AGENTS.md file tells you (and reminds Claude Code) what level of
detail each task needs. Simple tasks get concise prompts.
Complex tasks get full specialist context loaded.
See Section 7 for the full routing table.

### Rule 6 — End-of-session /log
```
/log
```
Writes everything important to CLAUDE.md before you close VS Code.
Next session: Claude Code auto-loads CLAUDE.md and instantly knows
where you left off. Zero re-explaining. Zero wasted tokens.

### Estimated savings vs naive approach

| Without strategy | With strategy | Saving |
|---|---|---|
| Paste all context every message | @-mention only needed files | ~50% |
| Never compact | /compact every 30 exchanges | ~40% mid-session |
| One huge prompt per feature | Focused single-job commands | ~35% |
| Re-explain project every session | CLAUDE.md auto-loaded | ~70% first message |
| **Combined effect** | | **~60–70% total** |

---

## 5. Project Folder Structure

```
docubot/
│
├── CLAUDE.md                        ← auto-loaded project brain
├── AGENTS.md                        ← routing table (what to use when)
├── README.md                        ← public portfolio README
│
├── .claude/
│   ├── commands/                    ← your slash command agents
│   │   ├── spec.md                  → /spec
│   │   ├── eval.md                  → /eval
│   │   ├── code.md                  → /code
│   │   ├── review.md                → /review
│   │   ├── test.md                  → /test
│   │   ├── secure.md                → /secure
│   │   ├── inject.md                → /inject
│   │   ├── check.md                 → /check
│   │   ├── debug.md                 → /debug
│   │   ├── perf.md                  → /perf
│   │   ├── log.md                   → /log
│   │   ├── narrate.md               → /narrate
│   │   ├── save.md                  → /save  (snapshot session state)
│   │   └── load.md                  → /load  (restore session state)
│   │
│   └── context/                     ← specialist knowledge files
│       ├── python-standards.md      ← Python/FastAPI coding patterns
│       ├── rag-patterns.md          ← RAG, embeddings, vector search
│       ├── security-rules.md        ← OWASP top 10, input validation
│       ├── react-standards.md       ← React component patterns
│       └── test-patterns.md         ← pytest fixtures, mock patterns
│
├── backend/
│   ├── .venv/                       ← Python virtual environment
│   ├── .env                         ← secrets (not in git)
│   ├── .env.example                 ← structure (in git)
│   ├── requirements.txt
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── routers/
│   │   ├── documents.py
│   │   └── chat.py
│   ├── services/
│   │   ├── ingestion.py
│   │   ├── rag_pipeline.py
│   │   └── embeddings.py
│   ├── models/
│   │   └── schemas.py
│   └── tests/
│       ├── test_ingestion.py
│       └── test_rag.py
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChatWidget.jsx
│   │   │   ├── MessageBubble.jsx
│   │   │   ├── SourceCitations.jsx
│   │   │   ├── TypingIndicator.jsx
│   │   │   ├── AdminPanel.jsx
│   │   │   └── DocumentCard.jsx
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── .env.local
│   └── package.json
│
├── docs/
│   ├── RAG_SupportBot_MasterPlan_v3.md
│   ├── DocuBot_Master_Checklist_v3.md
│   └── database_schema.sql
│
├── data/
│   ├── sample_faq.txt
│   ├── sample_guide.txt
│   └── test_questions.json
│
├── scripts/
│   └── inject_test_data.py
│
└── .gitignore
```

---

## 6. CLAUDE.md — Your Project Brain

Create at `docubot/CLAUDE.md`. Claude Code auto-loads this every session.

```markdown
# DocuBot — Project Context

## What this project is
DocuBot is a RAG (Retrieval-Augmented Generation) support chatbot.
Businesses upload documents. Customers ask questions.
Claude API answers using ONLY the uploaded documents — no hallucination.
Built on Windows 11 · VS Code · Claude Code terminal only.
Pure native agent system — no external orchestrators.

## Current status
[UPDATE WITH /log AT END OF EVERY SESSION]
- Phase: 0 — Setup
- Last completed: initial folder structure
- Next task: Python environment and connection tests
- Blocking issues: none

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
- SUPABASE_KEY — from Supabase project settings (anon key)

## Important note on two Claude accounts
- claude.ai Pro → powers Claude Code, your build tool
- console.anthropic.com API → used BY the app to answer user questions
These are completely separate. Never confuse them.

## Agent system
All agents are plain .md files in .claude/commands/
Load specialist context with @.claude/context/[file].md
Save tokens: use /compact after long sessions, /clear between unrelated tasks
End every session with /log to update this file
```

---

## 7. AGENTS.md — Model Routing Table

Create at `docubot/AGENTS.md`. This is your token-saving routing guide.
Read it at the start of each session to know which approach to use.

```markdown
# DocuBot Agent Routing Table

## When to use which approach

| Task type | Use this | Load this context | Token cost |
|---|---|---|---|
| Quick question / clarification | Natural language | nothing extra | Low |
| Define a new feature | /spec | nothing extra | Low |
| Evaluate a spec | /eval | nothing extra | Low |
| Write a single function | /code | @.claude/context/python-standards.md | Medium |
| Write a React component | /code | @.claude/context/react-standards.md | Medium |
| Write RAG pipeline code | /code | @.claude/context/rag-patterns.md | Medium |
| Review any backend file | /review | @.claude/context/python-standards.md | Medium |
| Write pytest tests | /test | @.claude/context/test-patterns.md | Medium |
| Security audit | /secure | @.claude/context/security-rules.md | Medium |
| Generate test data | /inject | nothing extra | Medium |
| Integration test runbook | /check | @CLAUDE.md | Low |
| Debug an error | /debug | @[the broken file] | Low-Medium |
| Performance audit | /perf | @[the relevant pipeline file] | Medium |
| End of session | /log | @CLAUDE.md | Low |
| Portfolio content | /narrate | @README.md @CLAUDE.md | Medium |
| Snapshot session state | /save | @CLAUDE.md | Low |
| Restore session state | /load | @CLAUDE.md | Low |

## Token saving rules

1. /compact — run after every 30+ message exchanges
2. /clear — run when switching to a completely different task
3. Load context files with @ — do not paste their content manually
4. One agent per task — do not chain multiple jobs in one prompt
5. /log at end of every session — prevents re-explaining next session

## Phase-by-phase agent usage

### Phase 0 (setup): natural language only, /log at end
### Phase 1 (ingestion): full loop — /spec /eval /code /review /test /secure per function
### Phase 2 (RAG pipeline): full loop + load @.claude/context/rag-patterns.md
### Phase 3 (frontend): full loop + load @.claude/context/react-standards.md
### Phase 4 (security): /secure on every file, /perf before deployment
### Phase 5 (deploy): natural language + /narrate for portfolio
```

---

## 8. Slash Command Agents — Full Content

Paste each block into the corresponding file in `.claude/commands/`.

---

### /spec — Feature Spec Generator
**File:** `.claude\commands\spec.md`

```markdown
# Feature Spec Generator
You are a senior product engineer. Generate a complete, unambiguous feature
specification. Do not write any code.

Feature: $ARGUMENTS

Output exactly these sections:

## Summary
One paragraph: what it does, who uses it, why it exists.

## Inputs and outputs
What comes IN: data types, formats, size limits, required vs optional.
What comes OUT: response shape, HTTP status codes, side effects.

## Happy path
Numbered steps of exactly what happens when everything works.

## Error cases
Every failure mode. For each: trigger, error code, message to return.

## Security requirements
Validation rules. Authentication needed? Rate limits? File restrictions?

## Database changes
What gets written, updated, or deleted. Which tables. Which columns.

## Dependencies
Other functions, services, or APIs this feature calls.

## Acceptance criteria
Numbered, testable statements: "Passes when: [X]"

## Student learning note
List concepts to understand before coding this. One sentence each.
```

---

### /eval — Spec Evaluator
**File:** `.claude\commands\eval.md`

```markdown
# Spec Evaluator
You are a critical senior engineer. Review the spec in context.
Be strict — a bad spec costs 3x more time than fixing it now.

Evaluate for:

## Missing scenarios
List every case the spec did not cover. Explain why each matters.

## Security gaps
What can be exploited if built exactly as written?
Cover: injection, file abuse, rate bypass, data leakage, auth bypass.

## Ambiguities
Where could two developers make different decisions from the same spec?
List every unclear point.

## Scalability problems
What breaks at 1,000 documents? 10,000 queries per day?

## Missing error cases
What failure modes were skipped?

## Verdict
APPROVED — proceed to coding.
NEEDS REVISION — list required changes before coding starts.
```

---

### /code — Coder Agent
**File:** `.claude\commands\code.md`

```markdown
# Coder Agent
You are a senior developer writing production code for DocuBot.
Read @CLAUDE.md for project standards before writing anything.

Task: $ARGUMENTS

Before writing:
1. State which file you will create or modify
2. State which functions/components you will add
3. List imports needed

Write the code with these rules:
- Docstring on every function (what, parameters, return value, why)
- Module comment on every new file (purpose of this file)
- Type hints on every function signature
- All errors caught with descriptive messages — no bare except
- No hardcoded values — use config.py or environment variables
- Inline comment on any line a beginner might not understand
- Python: follow PEP 8
- React: functional components with hooks only

After writing:
- List the next 2 things needed to make this work end-to-end
- Do NOT write tests (that is /test)
- Do NOT add security audit (that is /secure)
```

---

### /review — Code Reviewer
**File:** `.claude\commands\review.md`

```markdown
# Code Reviewer
You are a principal engineer reviewing DocuBot code.
Read @CLAUDE.md for project standards.

Code to review: $ARGUMENTS

## Correctness
Trace the logic. Where does it produce wrong results?

## Error handling
What happens when: API is down, DB is unavailable, input is null,
file is corrupted? List every unhandled failure mode.

## Security
Input validation, secret leakage, injection risks, path traversal.

## Code quality
Readable? DRY? Single responsibility per function?

## Performance
N+1 queries? Blocking ops that should be async? Unnecessary loops?

## Student learning
Two most important concepts in this code to study. Two sentences each.

## Verdict
APPROVED / APPROVED WITH NOTES / NEEDS REWORK
For NEEDS REWORK: list exactly what must change before proceeding.
```

---

### /test — Test Writer
**File:** `.claude\commands\test.md`

```markdown
# Test Writer
You are a QA engineer writing pytest tests for DocuBot.
Read @.claude/context/test-patterns.md for project test standards.

What to test: $ARGUMENTS

For each function, write:
1. Happy path test — normal input, correct output
2. Edge case tests — empty, max size, special characters
3. Error tests — invalid input raises the right exception

Rules:
- Mock ALL external APIs (OpenAI, Anthropic, Supabase) — never real calls
- pytest fixtures for reusable mock data
- Test function name describes exactly what it verifies:
  test_chunk_text_returns_correct_overlap_size
- Docstring on each test:
  "Verifies that [function] [does what] when [condition]."

After writing:
- Show the run command: pytest tests\test_X.py -v
- Show what passing output looks like
```

---

### /secure — Security Tester
**File:** `.claude\commands\secure.md`

```markdown
# Security Tester
You are a penetration tester auditing DocuBot.
Read @.claude/context/security-rules.md for project security standards.

Code to audit: $ARGUMENTS

## File upload attacks
Test: malicious extension, oversized file, zip bomb, SVG with scripts.
For each: attack scenario → how current code handles it → fix if vulnerable.

## Injection attacks
SQL injection via user input reaching DB queries.
Prompt injection via user message hijacking Claude system prompt.
Path traversal via filename like ../../etc/passwd.

## Authentication and authorization
Every protected endpoint verified? User isolation enforced?

## Secret exposure
Can API keys appear in: error messages, logs, HTTP responses?

## Rate limiting
Spam cost: what is the API credit drain from 10,000 fake requests?

## CORS and headers
Is CORS too permissive? Security headers present?

## Error messages
Do 500 errors expose stack traces, file paths, or internals?

## Severity ratings
CRITICAL / HIGH / MEDIUM / LOW for each finding.
Fix CRITICAL and HIGH before any deployment.
```

---

### /inject — Data Injector
**File:** `.claude\commands\inject.md`

```markdown
# Data Injector
You are a QA engineer creating realistic test data for DocuBot.

Data to generate: $ARGUMENTS

Generate these files:

## data\sample_faq.txt
Realistic FAQ for a fictional SaaS called TaskFlow (project management).
20 Q&A pairs: account setup, billing, features, troubleshooting, integrations.
Plain text, clearly formatted.

## data\sample_guide.txt
Product feature guide, 3 pages equivalent.
Getting started, core features, advanced settings, API reference summary.

## data\test_questions.json
{
  "should_answer": [
    {"question": "...", "expected_source": "sample_faq.txt",
     "key_phrase_in_answer": "..."}
  ],  (10 questions IN the documents)
  "should_not_answer": [
    {"question": "...", "reason": "..."}
  ],  (5 questions NOT in the documents)
  "adversarial": [
    {"question": "...", "attack_type": "prompt injection / scope bypass"}
  ]   (5 questions trying to break the bot)
}

## scripts\inject_test_data.py
Script that:
1. Reads sample files from data\
2. POSTs them to http://localhost:8000/api/documents/upload
3. Waits for processing
4. Runs all should_answer questions against /api/chat
5. Prints: correct answers, failed answers, pass rate

Runnable with: python scripts\inject_test_data.py
```

---

### /check — Integration Checker
**File:** `.claude\commands\check.md`

```markdown
# Integration Checker
You are a QA engineer verifying DocuBot works end-to-end.
Read @CLAUDE.md for current project state.

What to check: $ARGUMENTS

Generate a numbered test runbook:

## Pre-conditions
What must be true before starting.

## Test steps
For each step:
- Action (URL, method, request body, file to use)
- Check in response (status code, specific fields)
- Check in Supabase (which table, which column, expected value)
- PASS condition
- FAIL condition and likely cause

## Complete user journeys
1. Upload doc → ask question → answer cites that doc
2. Ask question not in docs → "I don't know" response
3. Delete doc → ask about it → "I don't know" response
4. Two questions in same session → history maintained

## Expected database state
After full test: expected rows in each table.

## Red flags
5 things indicating something is broken even if no error appears.
```

---

### /debug — Debug Detective
**File:** `.claude\commands\debug.md`

```markdown
# Debug Detective
You are a senior developer diagnosing a bug in DocuBot.

Error or problem: $ARGUMENTS

## 1. What the error means
Explain in plain English. What is Python/the framework telling me?

## 2. Root cause
What assumption was wrong? Walk through the code path step by step.

## 3. Why this happens
What concept did I misunderstand? Explain it so I won't repeat this mistake.

## 4. The fix
Exact code change. Explain each changed line.

## 5. Prevention
What defensive pattern would have caught this earlier?
Show that pattern applied to this code.

## 6. Related risks
Other places in the codebase where the same mistake might exist.
```

---

### /perf — Performance Auditor
**File:** `.claude\commands\perf.md`

```markdown
# Performance Auditor
You are a performance engineer auditing DocuBot before deployment.

What to audit: $ARGUMENTS

## API cost analysis
Count every external API call in the pipeline:
- OpenAI embedding calls: how many per operation, token count
- Anthropic calls: how many, which model, estimated tokens
- Cost per single query at current implementation
- Cost for 100/day and 1,000/day

## Latency
Steps in the query pipeline with expected duration.
Slowest step. Total expected latency p50 and p95.

## Database efficiency
Is the pgvector index being used? Check with EXPLAIN ANALYZE.
Speed impact at 10,000 chunks? 100,000 chunks?

## Caching opportunities
What to cache, TTL, invalidation rule.

## Memory usage
Does ingestion hold entire files in memory?
Memory use for a 50-page PDF?

## Quick wins
3 optimizations implementable in under 1 hour with the biggest impact.
```

---

### /log — Session Logger
**File:** `.claude\commands\log.md`

```markdown
# Session Logger
Review our conversation and the files changed this session.

## Session summary
What was completed (specific function/file names, not vague summaries).
What is broken or incomplete.
Concepts encountered for the first time this session.
Technical decisions made and why.

## Next session
3–5 specific tasks to work on next. Specific enough to start immediately.

## Update CLAUDE.md
Rewrite the "## Current status" section of CLAUDE.md with:
- Current phase and % complete
- Last completed task (specific)
- Next task (specific)
- Any blocking issues

Show me the updated section so I can paste it into CLAUDE.md.
```

---

### /narrate — Portfolio Narrator
**File:** `.claude\commands\narrate.md`

```markdown
# Portfolio Narrator
You are a technical writer creating portfolio content.
Read @CLAUDE.md and @README.md for project context.

Generate: $ARGUMENTS

## GitHub README.md
Full README with: description, live demo link, tech stack table,
architecture diagram (ASCII), "what I learned" section,
"challenges I solved" section, local setup instructions.

## LinkedIn announcement post
Genuine student voice. Mention Upwork market research angle.
Show learning journey, not just outcome. Under 300 words.
End with a question to drive engagement.

## Upwork profile paragraph
60–80 words. Emphasize: built from scratch, understand architecture
deeply, can adapt to client needs.

## Three Upwork proposal openings
- Version A: lead with technical credibility
- Version B: lead with business value
- Version C: lead with student energy and speed

## Demo video shot list
Scene-by-scene for a 2-minute Loom recording.
Each scene: what to show + what to say.
```

---

### /save — Session State Snapshot
**File:** `.claude\commands\save.md`

```markdown
# Session State Snapshot
Create a snapshot of current session state for safe handoff.

Generate a file called .claude\session_snapshot.md with:

## Snapshot timestamp
Current date and time.

## Files modified this session
List every file created or changed, with a one-line summary of the change.

## Current working code
Paste the most recently completed function or component in full.

## Tests passing
List which test files pass: pytest tests\ -v results.

## Known issues
Any bugs or incomplete work at time of snapshot.

## Exact next step
One specific action to take when resuming.

Write this to .claude\session_snapshot.md now.
```

---

### /load — Restore Session State
**File:** `.claude\commands\load.md`

```markdown
# Restore Session State
Read @.claude/session_snapshot.md and @CLAUDE.md

Summarize:
1. Where we left off (last completed task)
2. Files that were being worked on
3. Any known issues to address
4. The exact first action to take this session

Then confirm you are ready to continue from that point.
Keep this summary brief — we want to get building quickly.
```

---

## Context Files — Full Content

Create these in `.claude\context\`. Agents @-mention them to load specialist knowledge.

---

### python-standards.md
**File:** `.claude\context\python-standards.md`

```markdown
# Python & FastAPI Standards for DocuBot

## Function structure
def function_name(param: type, param2: type) -> return_type:
    """
    What this function does.
    Args: param - description. param2 - description.
    Returns: what it returns.
    Raises: ExceptionType - when it raises.
    """
    # implementation

## Error handling
try:
    result = risky_operation()
except SpecificError as e:
    raise HTTPException(status_code=400, detail=f"Descriptive message: {e}")
except Exception as e:
    logger.error(f"Unexpected error in function_name: {e}")
    raise HTTPException(status_code=500, detail="Internal server error")

## FastAPI endpoint structure
@router.post("/endpoint", response_model=ResponseSchema, status_code=201)
async def endpoint_name(request: RequestSchema, db = Depends(get_db)):
    """Endpoint docstring."""
    # validate → process → return

## File size validation
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", 20)) * 1024 * 1024
if file.size > MAX_FILE_SIZE:
    raise HTTPException(status_code=413, detail="File too large")

## Allowed file types
ALLOWED_TYPES = {"application/pdf", "text/plain"}
if file.content_type not in ALLOWED_TYPES:
    raise HTTPException(status_code=415, detail="Unsupported file type")
```

---

### rag-patterns.md
**File:** `.claude\context\rag-patterns.md`

```markdown
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
```

---

### security-rules.md
**File:** `.claude\context\security-rules.md`

```markdown
# Security Rules for DocuBot

## File upload security
- Validate content-type header (not just extension)
- Validate actual file magic bytes (not just MIME type claim)
- Enforce max file size before reading file content
- Save uploads to a controlled temp directory, not user-specified path
- Never execute uploaded files

## Input validation
- Max message length: 2000 characters
- Strip leading/trailing whitespace
- Reject null bytes and control characters
- Validate UUID format for any ID parameters

## API key protection
- Never include API keys in logs
- Never include API keys in error responses
- Never include API keys in HTTP responses of any kind
- Keys loaded from environment variables only

## Rate limiting
- Chat endpoint: 20 requests per minute per IP
- Upload endpoint: 5 requests per minute per IP
- Use slowapi library for FastAPI rate limiting

## CORS
- Development: allow localhost only
- Production: allow only your Vercel domain — never "*"

## Error responses
- Never expose stack traces to API consumers
- Never expose internal file paths
- Log detailed errors server-side, return generic message to client

## Prompt injection defense
- System prompt placed BEFORE user content
- User message clearly delimited and labeled
- Never interpolate raw user input into system prompt
- Validate user message does not contain "SYSTEM:" or "CONTEXT:"
```

---

### react-standards.md
**File:** `.claude\context\react-standards.md`

```markdown
# React Standards for DocuBot

## Component structure
- Functional components with hooks only (no class components)
- One component per file
- Props destructured in function signature with defaults

## State management
- useState for component-local state
- useEffect for side effects (API calls, subscriptions)
- No external state library needed for MVP

## API calls
- Use fetch() with async/await
- Always handle loading, success, and error states
- Show loading indicator while waiting
- Show user-friendly error message on failure

## Streaming SSE (for chat)
const eventSource = new EventSource('/api/chat');
eventSource.onmessage = (e) => setMessages(prev => [...prev, e.data]);
eventSource.onerror = () => eventSource.close();

## CSS
- Plain CSS only — no Tailwind, no CSS-in-JS for MVP
- CSS Modules for component-scoped styles
- Mobile-first responsive design

## Security
- Never use dangerouslySetInnerHTML
- Never render user input as HTML
- API URL from environment variable only: import.meta.env.VITE_API_URL
```

---

### test-patterns.md
**File:** `.claude\context\test-patterns.md`

```markdown
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
```

---

## 9. Tech Stack

| Tool | Purpose | Cost |
|---|---|---|
| Python 3.11 | Backend language | Free |
| FastAPI | Web API framework | Free |
| Claude API Haiku | Answer user questions | ~$0.001/query |
| OpenAI text-embedding-3-small | Create embeddings | $0.02/1M tokens |
| Supabase pgvector | Database + vector search | Free tier |
| React + Vite | Chat UI | Free |
| Render | Backend hosting | Free tier |
| Vercel | Frontend hosting | Free tier |
| Claude Code | Terminal build agent | Included in Pro |

### Two Claude accounts
```
Account 1: claude.ai Pro ($20/mo — you have this)
  → Powers Claude Code in your terminal
  → Your build tool

Account 2: console.anthropic.com (API — pay per use)
  → Your APP uses this to answer user questions
  → Add $5 credit, ~$0.001 per query on Haiku
```

---

## 10. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  USER BROWSER                                                    │
│  ┌──────────────────┐        ┌────────────────────────────┐    │
│  │  Admin Panel     │        │  Chat Widget               │    │
│  └────────┬─────────┘        └──────────────┬─────────────┘    │
└───────────┼──────────────────────────────────┼──────────────────┘
            │ POST /api/documents/upload        │ POST /api/chat
            ▼                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  FASTAPI BACKEND  (Render)                                       │
│                                                                  │
│  INGESTION                           QUERY                       │
│  Parse → Chunk → Embed → Store       Embed → Search → Prompt    │
│                                      → Claude API → Stream       │
│                     ↓                              ↓             │
│             SUPABASE pgvector                                    │
│          documents | chunks | conversations | messages           │
│                     ↓                              ↓             │
│          OpenAI Embeddings API          Anthropic Claude API     │
│          (console.anthropic.com)                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  YOUR WINDOWS 11 MACHINE  (build environment)                   │
│  VS Code terminal → claude → /spec /eval /code /review          │
│                              /test /secure /inject /check        │
│                              /debug /perf /log /narrate          │
│  CLAUDE.md auto-loaded · AGENTS.md routing guide                │
│  .claude/context/ specialist files loaded on demand             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 11. Full Features List

### MVP (Phase 1)
- [ ] F001 Upload PDF via admin panel
- [ ] F002 Upload TXT files
- [ ] F003 Parse and extract text
- [ ] F004 Split into 512-token chunks with 50-token overlap
- [ ] F005 Embed with OpenAI text-embedding-3-small
- [ ] F006 Store in Supabase pgvector
- [ ] F007 Upload progress status
- [ ] F008 List uploaded documents
- [ ] F009 Delete document and chunks
- [ ] F010 Chat widget UI
- [ ] F011 Streaming response
- [ ] F012 Typing indicator
- [ ] F013 Source citations
- [ ] F014 "I don't know" fallback
- [ ] F015 Conversation history
- [ ] F016 Clear chat
- [ ] F017 Copy answer
- [ ] F018 Embed user question
- [ ] F019 Cosine similarity search
- [ ] F020 Retrieve top 5 chunks
- [ ] F021 Rank by similarity score
- [ ] F022 Build grounded system prompt
- [ ] F023 Call Claude API
- [ ] F024 Stream response to frontend
- [ ] F025 Log query + answer + sources

### V2 (after MVP)
- [ ] F026 Admin conversation viewer
- [ ] F027 Most-asked questions analytics
- [ ] F028 Thumbs up/down feedback
- [ ] F029 Usage stats dashboard
- [ ] F030 User accounts + login
- [ ] F031 Per-account document isolation
- [ ] F032 Embeddable widget
- [ ] F033 Widget customization
- [ ] F034 Slack bot integration
- [ ] F035 Export conversations as CSV

### V3 (commercial)
- [ ] F036 Stripe billing
- [ ] F037 Usage limits per plan
- [ ] F038 Upload from URL
- [ ] F039 Google Docs / Notion sync
- [ ] F040 Multi-language support

---

## 12. Database & Data Models

```sql
-- Enable vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  file_type TEXT NOT NULL,
  size_bytes INTEGER,
  status TEXT DEFAULT 'processing',
  chunk_count INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Chunks with embeddings
CREATE TABLE chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  embedding VECTOR(1536),
  chunk_index INTEGER,
  token_count INTEGER,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Conversations
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Messages
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

-- Similarity search function
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
```

---

## 13. API Endpoints

```
GET    /health                      Health check
POST   /api/documents/upload        Upload PDF or TXT
GET    /api/documents               List all documents
DELETE /api/documents/{id}          Delete document and chunks
GET    /api/documents/{id}/status   Check processing status
POST   /api/chat                    Send message, get streamed response
GET    /api/chat/{session_id}       Get conversation history
DELETE /api/chat/{session_id}       Clear conversation
```

---

## 14. Build Phases

| Phase | What | Weeks | Key agents |
|---|---|---|---|
| 0 | Setup — accounts, tools, folder, git | 1 | natural language + /log |
| 1 | Ingestion pipeline | 2–3 | full loop per function |
| 2 | RAG query pipeline | 3–4 | full loop + rag-patterns.md |
| 3 | React frontend | 5–6 | full loop + react-standards.md |
| 4 | Security + performance | 7 | /secure /perf on everything |
| 5 | Deploy + portfolio | 8 | natural language + /narrate |

---

## 15. Free Datasets

| Dataset | Demo angle | Source |
|---|---|---|
| Anthropic public docs | "Claude API support bot" — meta and impressive | docs.anthropic.com |
| Stack Overflow Q&A | IT helpdesk bot | Kaggle public dump |
| University FAQ | Education sector | Your uni website |
| TaskFlow synthetic | Generated via /inject | On demand |

---

## 16. Deployment Plan

```
Backend → Render (free tier)
  Root directory: backend
  Build: pip install -r requirements.txt
  Start: uvicorn main:app --host 0.0.0.0 --port $PORT
  Env vars: set in Render dashboard

Frontend → Vercel (free tier)
  Root directory: frontend
  Env: VITE_API_URL = your Render URL
  Auto-deploys on git push to main

Database → Supabase (free tier, already cloud)
```

---

## 17. Portfolio & Monetization

### Stage 1 — Now (portfolio)
Live demo + GitHub + Loom video → first Upwork contract $500–1,500

### Stage 2 — Month 3–6 (productize)
Add accounts + Stripe billing → SaaS at $49–199/month → 10 customers = $2K MRR

### Stage 3 — Month 6–12 (scale)
White-label + integrations → 50 customers

---

## 18. Glossary

| Term | Plain English |
|---|---|
| RAG | Give the AI your docs to read before it answers |
| Embedding | Text converted to numbers capturing meaning |
| Cosine similarity | How similar two embeddings are (0–1) |
| Chunking | Splitting large docs into smaller pieces |
| pgvector | PostgreSQL extension for embedding storage and search |
| System prompt | Hidden instructions Claude reads before user messages |
| Streaming | Sending words one at a time instead of all at once |
| Claude Code | Terminal agent that reads and writes your files |
| CLAUDE.md | Auto-loaded project context Claude Code reads every session |
| /compact | Built-in command to compress session context and save tokens |
| /command | Custom slash command defined as .md in .claude/commands/ |
| @-mention | Way to load a file into context without pasting it |

---

## Revision History

| Version | Date | Changes |
|---|---|---|
| v1.0 | 2026-06-03 | Initial plan |
| v1.1 | 2026-06-03 | Added Claude Pro two-account model |
| v2.0 | 2026-06-03 | Windows 11 only, terminal only, Ruflo integrated |
| v3.0 | 2026-06-03 | Ruflo removed (security issues confirmed), replaced with native agent system: CLAUDE.md + AGENTS.md + 14 slash commands + 5 context files |

---
*Windows 11 · VS Code · Claude Code terminal only · Native agents · No third-party orchestrators*
