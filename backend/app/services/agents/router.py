import logging
import re
from typing import Dict, Any, Optional
from backend.app.services.nlp.intent_classifier import intent_classifier
from backend.app.services.nlp.ner_service import ner_service
from backend.app.services.nlp.translation_service import translation_service
from backend.app.services.rag.quality_scorer import quality_scorer
from backend.app.services.agents.crop_advisory_agent import crop_advisory_agent
from backend.app.services.agents.pest_control_agent import pest_control_agent
from backend.app.services.agents.market_price_agent import market_price_agent
from backend.app.services.agents.weather_agent import weather_agent
from backend.app.services.agents.scheme_lookup_agent import scheme_lookup_agent
from backend.app.models.schemas import QueryPipelineResponse

logger = logging.getLogger(__name__)

class AgentRouter:
    """
    Central Agent Orchestrator.
    Routes queries to specialized sub-agents based on detected intent:
      - crop_advisory
      - pest_control
      - market_prices
      - weather
      - scheme_lookup
    Performs quality confidence scoring, flags low-confidence responses,
    and handles back-translation into the farmer's target language.
    """

    async def route_and_process(
        self,
        session_id: str,
        original_query: str,
        canonical_query: str,
        detected_language: str,
        farmer_profile: Dict[str, Any],
        answer_language: Optional[str] = None
    ) -> QueryPipelineResponse:
        # 1. Intent classification & Agricultural NER
        intent, intent_confidence, intent_model = intent_classifier.classify_intent(canonical_query)
        entities = ner_service.extract_entities(canonical_query)

        # 2. Decide target language explicitly (Task 3)
        # Never fall back to Hindi for an English request!
        target_lang = answer_language or (
            detected_language if detected_language in ["hi", "kn"]
            else farmer_profile.get("preferred_language") or "en"
        )

        retrieved_chunks = []
        live_data = None
        sub_agent_name = intent

        if intent == "market_prices":
            answer_canonical, retrieved_chunks, live_data = await market_price_agent.execute(
                canonical_query, farmer_profile, entities
            )
        elif intent == "weather":
            answer_canonical, retrieved_chunks, live_data = await weather_agent.execute(
                canonical_query, farmer_profile, entities
            )
        elif intent == "pest_control":
            answer_canonical, retrieved_chunks, live_data = await pest_control_agent.execute(
                canonical_query, farmer_profile, target_language=target_lang
            )
        elif intent == "scheme_lookup":
            answer_canonical, retrieved_chunks, live_data = await scheme_lookup_agent.execute(
                canonical_query, farmer_profile
            )
        else:
            sub_agent_name = "crop_advisory"
            answer_canonical, retrieved_chunks, live_data = await crop_advisory_agent.execute(
                canonical_query, farmer_profile, target_language=target_lang
            )

        # 3. Response Quality Scoring & Human Review Flagging
        confidence_score, is_low_confidence, flag_reason, is_fallback = quality_scorer.calculate_confidence(
            retrieved_chunks=retrieved_chunks,
            intent_confidence=intent_confidence,
            entities=entities,
            query=canonical_query,
            sub_agent=sub_agent_name,
            live_data=live_data
        )

        # 4. Generate Short Answer
        short_answer_canonical = self._extract_short_answer(answer_canonical, sub_agent_name, live_data)

        # 5. Direct translation reuse or back-translation
        if target_lang == "en":
            answer_translated = answer_canonical
            short_answer_translated = short_answer_canonical
        elif live_data and live_data.get("direct_translated_answer") and target_lang in ["hi", "kn"]:
            answer_translated = live_data["direct_translated_answer"]
            short_answer_translated = live_data.get("direct_translated_short") or self._extract_short_answer(answer_translated, sub_agent_name, live_data)
        else:
            tr_res, _ = await translation_service.from_canonical(
                canonical_text=answer_canonical,
                target_language=target_lang
            )
            answer_translated = tr_res or answer_canonical
            sh_res, _ = await translation_service.from_canonical(
                canonical_text=short_answer_canonical,
                target_language=target_lang
            )
            short_answer_translated = sh_res or short_answer_canonical

        # Task 8: Record flagged review with English response plus translated one
        if is_low_confidence and flag_reason:
            await quality_scorer.record_flagged_review(
                session_id=session_id,
                original_query=original_query,
                canonical_query=canonical_query,
                detected_language=detected_language,
                detected_intent=intent,
                response_text=f"[Canonical EN]: {answer_canonical}\n\n[Translated {target_lang}]: {answer_translated}",
                confidence_score=confidence_score,
                sub_agent=sub_agent_name,
                flag_reason=flag_reason,
                retrieved_chunks=retrieved_chunks
            )

        # Check if any retrieved chunk is unverified (Task 9)
        has_unverified = any(c.metadata.get("verified") is False for c in retrieved_chunks)
        engine_used = (live_data.get("synthesis_engine") if live_data else None) or intent_model

        return QueryPipelineResponse(
            session_id=session_id,
            original_query=original_query,
            detected_language=detected_language,
            canonical_query=canonical_query,
            intent=intent,
            intent_confidence=intent_confidence,
            entities=entities,
            sub_agent=sub_agent_name,
            answer_canonical=answer_canonical,
            answer_translated=answer_translated,
            short_answer_canonical=short_answer_canonical,
            short_answer_translated=short_answer_translated,
            confidence_score=confidence_score,
            is_low_confidence=is_low_confidence,
            is_fallback=is_fallback,
            engine_used=engine_used,
            has_unverified_sources=has_unverified,
            flag_reason=flag_reason,
            retrieved_chunks=retrieved_chunks,
            live_data=live_data
        )

    def _extract_short_answer(self, full_answer: str, sub_agent: str, live_data: Optional[Dict[str, Any]]) -> str:
        """Extracts a 1-2 sentence core practical answer suitable for voice read-out."""
        if sub_agent == "weather" and live_data and "weather" in live_data:
            w = live_data["weather"]
            return f"Weather in {w.get('location')}: {w.get('temperature')}°C. {w.get('advisory')}"
        if sub_agent == "market_prices" and live_data and "mandi_prices" in live_data and live_data["mandi_prices"]:
            p = live_data["mandi_prices"][0]
            return f"{p.get('commodity')} modal price at {p.get('market')} is ₹{p.get('modal_price')} per quintal."

        # For text advisories, take the first 1-2 sentences supporting Latin '.' and Indic '।'
        clean = full_answer.strip()
        lines = [line.strip() for line in clean.split("\n") if line.strip() and not line.strip().startswith("According to")]
        if lines:
            first_block = lines[0]
            parts = re.split(r'([.।\n])', first_block)
            if len(parts) >= 4:
                return (parts[0] + parts[1] + " " + parts[2] + parts[3]).strip()
            elif len(parts) >= 2:
                return (parts[0] + parts[1]).strip()
            return first_block[:160]
        return clean[:160]

agent_router = AgentRouter()
