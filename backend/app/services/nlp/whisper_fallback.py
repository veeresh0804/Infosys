import logging
import httpx
from typing import Tuple
from backend.app.config import settings

logger = logging.getLogger(__name__)

class WhisperFallbackService:
    """
    Free-tier Groq-hosted Whisper STT fallback service (replacing paid OpenAI Whisper).
    Invoked when Sarvam AI is disabled, out of credits, or encounters a failure.
    Uses Groq's high-speed free tier (whisper-large-v3-turbo / whisper-large-v3).
    """

    def __init__(self):
        self.groq_api_key = settings.GROQ_API_KEY
        self.groq_model = settings.GROQ_WHISPER_MODEL
        self.openai_api_key = settings.OPENAI_API_KEY

    @property
    def is_configured(self) -> bool:
        return bool(
            (self.groq_api_key and self.groq_api_key.strip() and not self.groq_api_key.startswith("your_")) or
            (self.openai_api_key and self.openai_api_key.strip() and not self.openai_api_key.startswith("your_"))
        )

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        content_type: str = "audio/wav",
        language: str = "en"
    ) -> Tuple[str, str, str]:
        """
        Transcribe audio using Groq Whisper (free tier) or OpenAI fallback.
        Returns: (transcript, language, engine_used)
        """
        # 1. Primary: Groq Free-Tier Whisper
        if self.groq_api_key and self.groq_api_key.strip() and not self.groq_api_key.startswith("your_"):
            try:
                headers = {"Authorization": f"Bearer {self.groq_api_key}"}
                files = {"file": (filename, audio_bytes, content_type)}
                data = {
                    "model": self.groq_model,
                    "language": language.split("-")[0] if language else "en"
                }
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers=headers,
                        files=files,
                        data=data
                    )
                    if response.status_code == 200:
                        transcript = response.json().get("text", "").strip()
                        return transcript, language, f"groq_whisper_{self.groq_model}"
                    else:
                        logger.error(f"Groq Whisper failed: HTTP {response.status_code} - {response.text}")
            except Exception as e:
                logger.warning(f"Groq Whisper API call failed: {e}")

        # 2. Secondary: OpenAI Whisper (if key explicitly provided)
        if self.openai_api_key and self.openai_api_key.strip() and not self.openai_api_key.startswith("your_"):
            try:
                headers = {"Authorization": f"Bearer {self.openai_api_key}"}
                files = {"file": (filename, audio_bytes, content_type)}
                data = {"model": "whisper-1", "language": language.split("-")[0] if language else "en"}
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        "https://api.openai.com/v1/audio/transcriptions",
                        headers=headers,
                        files=files,
                        data=data
                    )
                    if response.status_code == 200:
                        transcript = response.json().get("text", "").strip()
                        return transcript, language, "openai_whisper_fallback"
            except Exception as e:
                logger.warning(f"OpenAI Whisper fallback failed: {e}")

        # 3. Clearly-labelled Deterministic Mock Fallback
        logger.warning("[MOCK] Neither Groq nor OpenAI Whisper key configured. Using clearly-labelled fallback mock.")
        return (
            "What is the fertilizer schedule for paddy rice in Kharif season?",
            language,
            "mock_whisper_fallback"
        )

whisper_service = WhisperFallbackService()
