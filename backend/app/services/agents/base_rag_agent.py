from typing import Any, Dict, List, Tuple
from backend.app.models.schemas import RetrievedChunk
from backend.app.services.rag.rag_engine import rag_engine
from backend.app.services.rag.vector_store import get_vector_store


class BaseRAGAdvisoryAgent:
    """
    Shared retrieval + synthesis pipeline for knowledge-base-backed sub-agents.
    Subclasses only declare their ``sub_agent_name``; vector retrieval (top_k=3),
    LLM synthesis, and extra_data assembly behave identically for all of them.
    """

    sub_agent_name: str = "crop_advisory"

    async def execute(
        self,
        query: str,
        farmer_profile: Dict[str, Any],
        target_language: str = "en"
    ) -> Tuple[str, List[RetrievedChunk], Dict[str, Any]]:
        vector_store = get_vector_store()
        chunks = await vector_store.similarity_search(query, top_k=3)
        ans_tr, short_tr, ans_en, short_en, engine = await rag_engine.generate_response(
            query=query,
            retrieved_chunks=chunks,
            farmer_profile=farmer_profile,
            target_language=target_language
        )

        extra_data = {
            "sub_agent": self.sub_agent_name,
            "chunks_retrieved": len(chunks),
            "synthesis_engine": engine,
            "direct_translated_answer": ans_tr if target_language in ["hi", "kn"] else None,
            "direct_translated_short": short_tr if target_language in ["hi", "kn"] else None
        }
        return ans_en, chunks, extra_data
