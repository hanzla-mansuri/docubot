# routers/documents.py — API routes for document upload and management.
# Groups all /documents endpoints together using FastAPI's APIRouter.
# Full implementation is added in Section 5 (document ingestion pipeline).

from fastapi import APIRouter

# prefix="/documents" means every route defined here automatically starts with /documents.
# tags=["Documents"] groups these endpoints together in the /docs Swagger UI.
router = APIRouter(prefix="/documents", tags=["Documents"])

# Section 5 will add:
# POST   /documents/upload   — upload a file, trigger chunking and embedding
# GET    /documents          — list all documents for a given business_id
# DELETE /documents/{id}     — delete a document and all its associated chunks
