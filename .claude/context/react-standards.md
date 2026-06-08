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