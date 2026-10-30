import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from backend.app.models.schemas import IngestionResult
from backend.app.config import settings
from data.ingestion.ingest import run_ingestion

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingestion", tags=["Knowledge Base Ingestion"])

@router.post("/reindex", response_model=IngestionResult)
async def reindex_knowledge_base(x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token")):
    """
    Ingests and embeds curated ICAR guidance, KCC FAQs, and Government Schemes
    into the configured vector database (Pinecone, ChromaDB, or Local Fallback).
    Protected by X-Admin-Token.
    """
    if settings.ADMIN_API_KEY:
        if not x_admin_token or x_admin_token != settings.ADMIN_API_KEY:
            raise HTTPException(status_code=403, detail="Forbidden: Invalid or missing X-Admin-Token")

    try:
        docs_count, chunks_count = await run_ingestion()
        return IngestionResult(
            documents_ingested=docs_count,
            chunks_created=chunks_count,
            vector_db_type=settings.VECTOR_DB_TYPE,
            status="success",
            message=f"Successfully indexed {docs_count} documents ({chunks_count} chunks) into {settings.VECTOR_DB_TYPE} vector store."
        )
    except Exception as e:
        logger.exception("Knowledge base ingestion failed")
        raise HTTPException(status_code=500, detail=str(e))

