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