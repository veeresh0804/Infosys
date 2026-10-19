import base64
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.database import get_db
from backend.app.models.schemas import (
    QueryPipelineRequest, QueryPipelineResponse,
    FlaggedReviewModel, RetrievedChunk
)
from backend.app.services.nlp.translation_service import translation_service
from backend.app.services.nlp.sarvam_service import sarvam_service
from backend.app.services.nlp.whisper_fallback import whisper_service
from backend.app.services.session.session_service import session_service
from backend.app.services.agents.router import agent_router

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rag", tags=["RAG & Orchestration"])

@router.post("/query", response_model=QueryPipelineResponse)
async def process_farmer_query(
    req: QueryPipelineRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Main End-to-End Multilingual Agricultural Pipeline.
    Pipeline flow:
    1. Audio / Text Input -> Language Detection
    2. Translation to Canonical English
    3. Intent Classification & Agricultural NER
    4. Routing to Specialized Sub-Agent (RAG, Mandi, Weather, Schemes, Pest)
    5. Quality Scoring & Flagging (if confidence < 0.70)
    6. Back-translation to farmer's language
    7. Audio synthesis (optional TTS) & Session State update
    """
    try:
        session_id = req.session_id or "default-session"
        session_obj = await session_service.get_or_create_session(session_id, db)

        # 1. Handle Voice Input vs Text Input
        raw_query_text = (req.text or "").strip()
        detected_lang = req.language

        if req.audio_base64:
            try:
                audio_bytes = base64.b64decode(req.audio_base64)
                # Attempt Sarvam STT first
                try:
                    transcript, lang, _ = await sarvam_service.speech_to_text(
                        audio_bytes=audio_bytes,
                        language_code=req.language or session_obj.preferred_language
                    )
                    raw_query_text = transcript
                    detected_lang = lang
                except Exception:
                    transcript, lang, _ = await whisper_service.transcribe(
                        audio_bytes=audio_bytes,
                        language=req.language or "hi"
                    )
                    raw_query_text = transcript
                    detected_lang = lang
            except Exception as e:
                logger.error(f"Failed to process audio payload: {e}")
                if not raw_query_text:
                    raise HTTPException(status_code=400, detail="Invalid audio base64 data and no text provided")

        if not raw_query_text:
            raise HTTPException(status_code=400, detail="Either query text or audio_base64 is required")

        # 2. Canonical Translation
        canonical_text, detected_lang, _ = await translation_service.to_canonical(
            text=raw_query_text,
            source_language=detected_lang or session_obj.preferred_language
        )

        # 3. Assemble Farmer Profile from Session
        farmer_profile = {
            "session_id": session_obj.session_id,
            "preferred_language": session_obj.preferred_language,
            "state": session_obj.state or "Karnataka",
            "district": session_obj.district or "Bengaluru Rural",
            "landholding_acres": session_obj.landholding_acres or 2.0,
            "crops_grown": session_obj.crops_grown or ["Tomato", "Paddy"]
        }

        # 4. Agent Router Execution
        pipeline_res = await agent_router.route_and_process(
            session_id=session_id,
            original_query=raw_query_text,
            canonical_query=canonical_text,
            detected_language=detected_lang,
            farmer_profile=farmer_profile
        )

        # 5. Persist Exchange in Session History
        await session_service.append_history(
            session_id=session_id,
            role="farmer",
            text=raw_query_text,
            canonical_text=canonical_text,
            metadata={"language": detected_lang},
            db=db
        )
        await session_service.append_history(
            session_id=session_id,
            role="assistant",
            text=pipeline_res.answer_translated,
            canonical_text=pipeline_res.answer_canonical,
            metadata={
                "sub_agent": pipeline_res.sub_agent,
                "confidence_score": pipeline_res.confidence_score,
                "is_low_confidence": pipeline_res.is_low_confidence
            },
            db=db
        )

        return pipeline_res

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("RAG Query Pipeline failure")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/flagged-reviews")
async def get_flagged_reviews(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieves low-confidence queries flagged for human review by extension workers.
    """
    reviews = await session_service.get_flagged_reviews(db, limit=limit)
    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "original_query": r.original_query,
            "canonical_query": r.canonical_query,
            "detected_language": r.detected_language,
            "detected_intent": r.detected_intent,
            "response_text": r.response_text,
            "confidence_score": r.confidence_score,
            "sub_agent": r.sub_agent,
            "flag_reason": r.flag_reason,
            "retrieved_chunks": r.retrieved_chunks,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in reviews
    ]
