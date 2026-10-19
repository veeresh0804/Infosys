import logging
from fastapi import APIRouter, HTTPException, Query
from backend.app.models.schemas import (
    TranslationRequest, TranslationResponse,
    IntentEntityRequest, IntentEntityResponse
)
from backend.app.services.nlp.translation_service import translation_service
from backend.app.services.nlp.intent_classifier import intent_classifier
from backend.app.services.nlp.ner_service import ner_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/nlp", tags=["NLP & Multilingual"])

@router.post("/translate", response_model=TranslationResponse)
async def translate_text(req: TranslationRequest):
    """
    Translates text between Indic languages (Hindi, Kannada) and Canonical English.
    """
    try:
        detected_lang = req.source_language or translation_service.detect_language(req.text)

        if req.target_language.startswith("en"):
            translated, detected_lang, engine = await translation_service.to_canonical(
                text=req.text,
                source_language=detected_lang
            )
        else:
            translated, engine = await translation_service.from_canonical(
                canonical_text=req.text,
                target_language=req.target_language
            )

        is_failed = (translated is None or engine == "translation_failed")
        return TranslationResponse(
            original_text=req.text,
            detected_language=detected_lang,
            translated_text=translated or "",
            engine_used=engine,
            translation_failed=is_failed
        )
    except Exception as e:
        logger.exception("Translation request failed")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/intent-entities", response_model=IntentEntityResponse)
async def classify_intent_and_entities(req: IntentEntityRequest):
    """
    Identifies query intent and extracts agricultural domain entities (Crops, Pests, Inputs, Schemes).
    """
    try:
        intent, conf, model = intent_classifier.classify_intent(req.text)
        entities = ner_service.extract_entities(req.text)

        return IntentEntityResponse(
            intent=intent,
            intent_confidence=conf,
            entities=entities,
            model_used=model
        )
    except Exception as e:
        logger.exception("Intent/entity classification failed")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/detect-language")
async def detect_lang(text: str = Query(..., description="Input text to detect")):
    """
    Detects language (hi, kn, en) from input text.
    """
    lang = translation_service.detect_language(text)
    return {"text": text, "detected_language": lang}
