# routers/chat.py — API routes for the chat interface.
# Groups all /chat endpoints together using FastAPI's APIRouter.
# Full implementation is added in Section 6 (RAG query pipeline).

from fastapi import APIRouter

# prefix="/chat" means every route defined here automatically starts with /chat.
# tags=["Chat"] groups these endpoints together in the /docs Swagger UI.
router = APIRouter(prefix="/chat", tags=["Chat"])

# Section 6 will add:
# POST /chat          — send a message, receive a grounded answer streamed from Claude
# GET  /chat/{id}     — retrieve the full message history for a conversation
