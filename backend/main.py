# main.py — FastAPI application entry point for DocuBot.
# Creates the app instance, registers middleware, and mounts all route groups.
# Start the server with: uvicorn main:app --reload  (run from the backend/ directory)

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# config must be imported before database so the settings singleton exists
# when database.py runs create_client() during its own import
from config import settings

# Configure the root logger before any other local import so database.py startup
# logs are not silently dropped (logging.basicConfig has no effect after first handler is set)
logging.basicConfig(level=settings.LOG_LEVEL, force=True)
logger = logging.getLogger(__name__)

# Importing database triggers the Supabase singleton initialisation at startup.
# If the connection fails, the app refuses to start — which is the correct behaviour.
from database import supabase  # noqa: F401

from routers import chat, documents

# version comes from settings so the /health response and /docs header always agree
app = FastAPI(
    title="DocuBot API",
    version=settings.APP_VERSION,
    description="RAG-powered document Q&A API. Businesses upload documents; customers ask questions.",
)

# CORSMiddleware tells browsers which origins may call this API.
# Without it, the React frontend (localhost:5173) is blocked by the browser's same-origin policy.
app.add_middleware(
    CORSMiddleware,
    # In development allow all origins for convenience.
    # In production this MUST be set to the specific Vercel frontend URL.
    allow_origins=["*"] if settings.APP_ENV == "development" else [],
    allow_credentials=False,  # credentials (cookies/auth headers) require explicit allow_origins
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# Mount routers — each owns its own URL prefix defined in its own file
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """
    Liveness probe — confirms the server process is running and reachable.

    Does NOT verify database connectivity (that is a readiness probe, added later).
    Render uses this endpoint to decide whether to route traffic to this instance.

    Args: none.
    Returns: dict with "status" and "version" keys.
    """
    return {"status": "ok", "version": settings.APP_VERSION}
