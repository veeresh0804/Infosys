import logging
from typing import Dict, Any, Tuple, List
from backend.app.services.rag.vector_store import get_vector_store
from backend.app.services.rag.rag_engine import rag_engine
from backend.app.models.schemas import RetrievedChunk

logger = logging.getLogger(__name__)

class CropAdvisoryAgent:
    """
    Specialized Sub-Agent for Crop Advisory.
    Retrieves ICAR package of practices and generates tailored agronomic advice.
    """

    async def execute(
        self,
        query: str,
        farmer_profile: Dict[str, Any],
        target_language: str = "en"
    ) -> Tuple[str, List[RetrievedChunk], Dict[str, Any]]:
        vector_store = get_vector_store()
        chunks = await vector_store.similarity_search(query, top_k=3)
        full_answer, short_answer, engine = await rag_engine.generate_response(
            query=query,
            retrieved_chunks=chunks,
            farmer_profile=farmer_profile,
            target_language=target_language
        )

        extra_data = {
            "sub_agent": "crop_advisory",
            "chunks_retrieved": len(chunks),
            "synthesis_engine": engine,
            "direct_translated_answer": full_answer if target_language in ["hi", "kn"] else None,
            "direct_translated_short": short_answer if target_language in ["hi", "kn"] else None
        }
        return full_answer, chunks, extra_data

crop_advisory_agent = CropAdvisoryAgent()
