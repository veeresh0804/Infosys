import logging
from fastapi import APIRouter, HTTPException
from backend.app.models.schemas import IngestionResult
from backend.app.config import settings
from data.ingestion.ingest import run_ingestion

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingestion", tags=["Knowledge Base Ingestion"])

@router.post("/reindex", response_model=IngestionResult)
async def reindex_knowledge_base():
    """
    Ingests and embeds curated ICAR guidance, KCC FAQs, and Government Schemes
    into the configured vector database (Pinecone or ChromaDB).
    """
    try:
        count = await run_ingestion()
        return IngestionResult(
            documents_ingested=14,  # Raw document records
            chunks_created=count,
            vector_db_type=settings.VECTOR_DB_TYPE,
            status="success",
            message=f"Successfully chunked and indexed {count} items into {settings.VECTOR_DB_TYPE} vector store."
        )
    except Exception as e:
        logger.exception("Knowledge base ingestion failed")
        raise HTTPException(status_code=500, detail=str(e))
