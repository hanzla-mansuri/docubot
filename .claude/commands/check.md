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