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