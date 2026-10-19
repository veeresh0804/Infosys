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
        session_id = req.session_id.strip() if req.session_id and req.session_id.strip() else None
        session_obj = await session_service.get_or_create_session(session_id, db)
        session_id = session_obj.session_id

        # 1. Handle Voice Input vs Text Input
        raw_query_text = (req.text or "").strip()
        audio_filename = req.audio_filename or "audio.wav"
        audio_mime = req.audio_mime or "audio/wav"

        if req.audio_base64:
            try:
                audio_bytes = base64.b64decode(req.audio_base64)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid audio base64 data")

            stt_transcript = None
            stt_lang = None

            # Attempt Sarvam STT first
            try:
                stt_transcript, stt_lang, _ = await sarvam_service.speech_to_text(
                    audio_bytes=audio_bytes,
                    filename=audio_filename,
                    content_type=audio_mime,
                    language_code=req.language or session_obj.preferred_language
                )
            except Exception as e:
                logger.warning(f"Sarvam STT failed: {e}. Trying Whisper fallback...")

            # Fallback to Groq Whisper
            if not stt_transcript:
                try:
                    from backend.app.exceptions import STTUnavailableError
                    stt_transcript, stt_lang, _ = await whisper_service.transcribe(
                        audio_bytes=audio_bytes,
                        filename=audio_filename,
                        content_type=audio_mime,
                        language=req.language or "hi"
                    )
                except STTUnavailableError as sue:
                    logger.warning(f"STT unavailable: {sue}")
                    raise HTTPException(
                        status_code=503,
                        detail={"error": "stt_unavailable", "message": str(sue)}
                    )
                except Exception as e:
                    logger.warning(f"Whisper STT failed: {e}")

            if not stt_transcript or not stt_transcript.strip():
                raise HTTPException(
                    status_code=503,
                    detail={"error": "stt_unavailable", "message": "Speech-to-text service is unavailable. Please try again or type your question."}
                )

            raw_query_text = stt_transcript.strip()

        if not raw_query_text:
            raise HTTPException(status_code=400, detail="Either query text or audio_base64 is required")

        # 2. Language Detection & Answer Language Decision (Task 3)
        script_lang = translation_service.detect_language(raw_query_text)

        if script_lang in ["hi", "kn"]:
            detected_lang = script_lang
            answer_lang = script_lang  # Kannada text with UI set to Hindi is treated as Kannada
        elif script_lang == "en":
            detected_lang = "en"
            if req.language and req.language.strip() in ["hi", "kn"]:
                answer_lang = req.language.strip()
            else:
                answer_lang = "en"  # English text with no language field is answered in English
        else:
            detected_lang = req.language or session_obj.preferred_language or "en"
            answer_lang = detected_lang

        # 3. Canonical Translation & Honest Failure Handling (Task 4)
        canonical_text = raw_query_text
        if detected_lang != "en":
            translated_text, _, trans_engine = await translation_service.to_canonical(
                text=raw_query_text,
                source_language=detected_lang
            )
            if trans_engine == "translation_failed" or not translated_text:
                # Do NOT run intent/RAG on untranslated text. Return localized service busy message
                busy_messages = {
                    "hi": "कृषि सेवा वर्तमान में व्यस्त है। कृपया कुछ समय बाद पुनः प्रयास करें या अंग्रेजी में टाइप करें।",
                    "kn": "ಕೃಷಿ ಸೇವೆಯು ಪ್ರಸ್ತುತ ಕಾರ್ಯನಿರತವಾಗಿದೆ. ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಸಮಯದ ನಂತರ ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ ಅಥವಾ ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ ಟೈಪ್ ಮಾಡಿ.",
                    "en": "Agricultural guidance service is temporarily busy. Please try again later or type in English."
                }
                busy_msg = busy_messages.get(answer_lang, busy_messages["en"])
                return QueryPipelineResponse(
                    session_id=session_id,
                    original_query=raw_query_text,
                    detected_language=detected_lang,
                    canonical_query=raw_query_text,
                    intent="unknown",
                    intent_confidence=0.0,
                    entities=[],
                    sub_agent="none",
                    answer_canonical="Agricultural guidance service is temporarily busy. Please try again later or type in English.",
                    answer_translated=busy_msg,
                    short_answer_canonical="Service temporarily busy.",
                    short_answer_translated=busy_msg,
                    confidence_score=0.0,
                    is_low_confidence=True,
                    is_fallback=True,
                    engine_used="translation_unavailable_fallback",
                    has_unverified_sources=False
                )
            canonical_text = translated_text

        # 4. Assemble Honest Farmer Profile from Session (Task 6: no invented default facts)
        farmer_profile = {
            "session_id": session_obj.session_id,
            "preferred_language": answer_lang,
            "state": session_obj.state,
            "district": session_obj.district,
            "landholding_acres": session_obj.landholding_acres,
            "crops_grown": session_obj.crops_grown or []
        }

        # 5. Agent Router Execution
        pipeline_res = await agent_router.route_and_process(
            session_id=session_id,
            original_query=raw_query_text,
            canonical_query=canonical_text,
            detected_language=detected_lang,
            farmer_profile=farmer_profile,
            answer_language=answer_lang
        )

        # 6. Persist Exchange in Session History
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
