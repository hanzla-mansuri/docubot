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