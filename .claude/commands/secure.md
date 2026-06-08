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