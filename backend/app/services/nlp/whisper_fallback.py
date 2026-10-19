import logging
import httpx
from typing import Tuple
from backend.app.config import settings

logger = logging.getLogger(__name__)

class WhisperFallbackService:
    """
    OpenAI Whisper STT fallback service.
    Invoked when Sarvam AI does not support a given language or encounters a service failure.
    Official Endpoint: POST https://api.openai.com/v1/audio/transcriptions
    """

    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip() and not self.api_key.startswith("your_"))

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        content_type: str = "audio/wav",
        language: str = "en"
    ) -> Tuple[str, str, str]:
        """
        Transcribe audio using OpenAI Whisper-1 API.
        Returns: (transcript, language, engine_used)
        """
        if not self.is_configured:
            logger.warning("[MOCK] OpenAI API key not configured for Whisper STT. Using clearly-labelled fallback mock.")
            return (
                "What is the fertilizer schedule for paddy rice in Kharif season?",
                language,
                "mock_whisper_fallback"
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        files = {
            "file": (filename, audio_bytes, content_type)
        }
        data = {
            "model": "whisper-1",
            "language": language
        }

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data
                )
                if response.status_code == 200:
                    res_json = response.json()
                    transcript = res_json.get("text", "")
                    return transcript, language, "openai_whisper_fallback"
                else:
                    logger.error(f"Whisper STT failed: HTTP {response.status_code} - {response.text}")
                    return f"[Whisper fallback error HTTP {response.status_code}]", language, "whisper_error"
        except Exception as e:
            logger.exception("Error calling OpenAI Whisper API")
            return f"[Whisper fallback exception: {str(e)}]", language, "whisper_exception"

whisper_service = WhisperFallbackService()
