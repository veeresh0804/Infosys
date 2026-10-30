import logging
from typing import List, Tuple, Optional, Dict, Any
from backend.app.config import settings
from backend.app.models.schemas import RetrievedChunk, EntityItem, FlaggedReviewModel
from backend.app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

class QualityScorer:
    """
    Response Quality Scoring Module.
    Calculates holistic confidence score based on vector retrieval similarity,
    intent classification confidence, and agricultural entity coverage.
    Automatically flags low-confidence responses and stores them in SQLite
    for extension worker review.
    """

    def __init__(self):
        self.threshold = settings.QUALITY_CONFIDENCE_THRESHOLD

    def calculate_confidence(
        self,
        retrieved_chunks: List[RetrievedChunk],
        intent_confidence: float,
        entities: List[EntityItem],
        query: str,
        sub_agent: str = "crop_advisory",
        live_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, bool, Optional[str], bool]:
        """
        Calculates confidence score (0.0 - 1.0), determines whether it should be flagged,
        and detects if the response relied on mock or fallback data.

        Scoring Formula (Design Choice):
        - Live Data Sub-Agents (Weather, Mandi):
            If live API verified: 0.60 * (1.0) + 0.40 * intent_confidence (yielding 0.90 - 0.96)
            If mock / fallback: 0.30 (penalty) + 0.30 * intent_confidence + 0.10 (yielding ~0.65, flagged)
        - Document RAG Sub-Agents:
            0.50 * top_vector_similarity + 0.30 * intent_confidence + 0.20 * entity_match_score
        """
        is_fallback = False

        if sub_agent == "weather":
            w = live_data.get("weather", {}) if live_data else {}
            is_live_api = "Open-Meteo" in w.get("source", "") and "MOCK" not in w.get("source", "")
            if is_live_api:
                overall_score = 0.60 * 1.0 + 0.40 * intent_confidence
                is_fallback = False
            else:
                overall_score = 0.30 + 0.30 * intent_confidence + 0.10
                is_fallback = True
        elif sub_agent == "market_prices":
            prices = live_data.get("mandi_prices", []) if live_data else []
            has_live_prices = bool(prices and not any("MOCK" in p.get("source", "") for p in prices))
            if has_live_prices:
                overall_score = 0.60 * 1.0 + 0.40 * intent_confidence
                is_fallback = False
            else:
                overall_score = 0.30 + 0.30 * intent_confidence + 0.10
                is_fallback = True
        else:
            top_sim = retrieved_chunks[0].similarity_score if retrieved_chunks else 0.40
            entity_matches = 0
            if entities and retrieved_chunks:
                all_chunk_text = " ".join([c.content.lower() for c in retrieved_chunks])
                for ent in entities:
                    if ent.text.lower() in all_chunk_text:
                        entity_matches += 1
                entity_score = entity_matches / len(entities)
            else:
                entity_score = 0.70

            overall_score = (
                0.50 * top_sim +
                0.30 * intent_confidence +
                0.20 * entity_score
            )
            is_fallback = not bool(retrieved_chunks)

        overall_score = round(max(0.10, min(0.99, overall_score)), 2)
        is_low = overall_score < self.threshold
        flag_reason = None

        if is_low:
            reasons = []
            if is_fallback:
                reasons.append("Response generated from mock/fallback data source")
            if sub_agent in ["crop_advisory", "pest_control", "scheme_lookup"]:
                top_sim = retrieved_chunks[0].similarity_score if retrieved_chunks else 0.40
                if top_sim < 0.60:
                    reasons.append(f"Low semantic similarity to verified knowledge base ({top_sim:.2f})")
            if intent_confidence < 0.65:
                reasons.append(f"Low intent routing certainty ({intent_confidence:.2f})")
            flag_reason = "; ".join(reasons) if reasons else f"Overall confidence ({overall_score}) below review threshold ({self.threshold})"

        return overall_score, is_low, flag_reason, is_fallback

    async def record_flagged_review(
        self,
        session_id: str,
        original_query: str,
        canonical_query: str,
        detected_language: str,
        detected_intent: str,
        response_text: str,
        confidence_score: float,
        sub_agent: str,
        flag_reason: str,
        retrieved_chunks: List[RetrievedChunk]
    ):
        """
        Persists flagged low-confidence answer to SQLite database.
        """
        try:
            async with AsyncSessionLocal() as db:
                chunks_json = [
                    {
                        "id": c.id,
                        "source": c.source,
                        "similarity_score": c.similarity_score,
                        "content": c.content[:300]
                    }
                    for c in retrieved_chunks
                ]
                record = FlaggedReviewModel(
                    session_id=session_id,
                    original_query=original_query,
                    canonical_query=canonical_query,
                    detected_language=detected_language,
                    detected_intent=detected_intent,
                    response_text=response_text,
                    confidence_score=confidence_score,
                    sub_agent=sub_agent,
                    flag_reason=flag_reason,
                    retrieved_chunks=chunks_json
                )
                db.add(record)
                await db.commit()
                logger.info(f"Flagged low-confidence query recorded in SQLite: {flag_reason}")
        except Exception as e:
            logger.error(f"Error persisting flagged review to SQLite: {e}")

quality_scorer = QualityScorer()
