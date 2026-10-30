import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
from backend.app.models.schemas import STTResponse, TTSRequest, TTSResponse
from backend.app.services.nlp.sarvam_service import sarvam_service
from backend.app.services.nlp.whisper_fallback import whisper_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/speech", tags=["Speech Processing"])

from fastapi.responses import JSONResponse

@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language_code: Optional[str] = Form(None)
):
    """
    Transcribes audio using Sarvam AI Indic STT (Saaras).
    Automatically falls back to Groq Whisper if Sarvam is unavailable or unsupported.
    Never invents a transcript; returns 503 if all STT engines fail.
    """
    try:
        content = await file.read()
        if not content:
            return JSONResponse(status_code=400, content={"detail": "Empty audio file uploaded"})

        # 1. Try Sarvam AI STT
        try:
            transcript, lang, engine = await sarvam_service.speech_to_text(
                audio_bytes=content,
                filename=file.filename or "audio.wav",
                content_type=file.content_type or "audio/wav",
                language_code=language_code
            )
            return STTResponse(
                transcript=transcript,
                language_code=lang,
                engine_used=engine,
                confidence=None  # Only report confidence if engine provides it
            )
        except Exception as e:
            logger.warning(f"Sarvam STT failed: {e}. Attempting Groq Whisper fallback...")

        # 2. Fallback to Groq Whisper
        try:
            transcript, lang, engine = await whisper_service.transcribe(
                audio_bytes=content,
                filename=file.filename or "audio.wav",
                content_type=file.content_type or "audio/wav",
                language=language_code or "hi"
            )
            return STTResponse(
                transcript=transcript,
                language_code=lang,
                engine_used=engine,
                confidence=None  # Only report confidence if engine provides it
            )
        except Exception as sue:
            logger.warning(f"STT engines unavailable: {sue}")
            return JSONResponse(
                status_code=503,
                content={
                    "error": "stt_unavailable",
                    "message": f"Speech-to-text engines unavailable: {sue}"
                }
            )
    except Exception as e:
        logger.exception("Audio transcription failed")
        return JSONResponse(
            status_code=503,
            content={"error": "stt_unavailable", "message": str(e)}
        )

@router.post("/synthesize", response_model=TTSResponse)
async def synthesize_speech(req: TTSRequest):
    """
    Converts agricultural text response to Indic speech audio using Sarvam AI Bulbul TTS.
    """
    try:
        audio_b64, engine = await sarvam_service.text_to_speech(
            text=req.text,
            target_language=req.target_language,
            speaker=req.speaker or "meera"
        )
        return TTSResponse(
            audio_base64=audio_b64,
            format="wav",
            engine_used=engine
        )
    except Exception as e:
        logger.exception("Text to speech synthesis failed")
        raise HTTPException(status_code=500, detail=str(e))
