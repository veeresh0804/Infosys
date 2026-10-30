import time
import logging
import base64
import hashlib
import re
import httpx
from typing import Optional, Tuple
from backend.app.config import settings

logger = logging.getLogger(__name__)

# Standard language mapping to Sarvam BCP-47 codes
# Reference: https://docs.sarvam.ai/api-reference/text-to-speech
SARVAM_LANG_MAP = {
    "hi": "hi-IN",
    "kn": "kn-IN",
    "en": "en-IN",
    "hi-IN": "hi-IN",
    "kn-IN": "kn-IN",
    "en-IN": "en-IN",
}

# Valid Bulbul v3 speakers from Sarvam AI documentation
# Reference: https://docs.sarvam.ai/api-reference/text-to-speech
VALID_BULBUL_SPEAKERS = ["shubh", "kavya", "aditya", "priya", "roopa", "rahul", "neha", "shreya"]

class SarvamService:
    """
    Hardened Sarvam AI client for Indic speech-to-text, text-to-speech, and translation.
    Conforms to official Sarvam API specifications (https://docs.sarvam.ai):
      - STT endpoint: https://api.sarvam.ai/speech-to-text (model: saaras:v2 / saaras:v1)
      - TTS endpoint: https://api.sarvam.ai/text-to-speech (model: bulbul:v3)
        Parameters: inputs, target_language_code, speaker, pace, speech_sample_rate, enable_preprocessing
        (Note: 'pitch' and 'loudness' are legacy bulbul:v2 only and omitted here per docs)
      - Translate endpoint: https://api.sarvam.ai/translate (model: mayura:v1)
      - Circuit breaker: Permanent trip for 401/402/403/credits exhausted; 60s cooldown for 429
      - Sentence-boundary TTS summarization (no mid-word truncation)
      - Translation input chunking for long texts (>900 chars)
    """

    def __init__(self):
        self.api_key = settings.SARVAM_API_KEY
        self.api_url = settings.SARVAM_API_URL.rstrip("/")
        self.circuit_broken = False
        self.circuit_broken_reason = None
        self.cooldown_until: Optional[float] = None  # For HTTP 429 rate limit backoff

    @property
    def is_configured(self) -> bool:
        if not (settings.SARVAM_ENABLED and self.api_key and self.api_key.strip() and not self.api_key.startswith("your_")):
            return False
        if self.circuit_broken:
            return False
        if self.cooldown_until and time.time() < self.cooldown_until:
            return False
        return True

    def _trip_circuit(self, reason: str):
        if not self.circuit_broken:
            self.circuit_broken = True
            self.circuit_broken_reason = reason
            logger.error(f"🚨 [CIRCUIT BREAKER] Sarvam AI disabled permanently for session. Reason: {reason}. Switching to free fallbacks.")

    def _handle_rate_limit(self, retry_after: int = 60):
        self.cooldown_until = time.time() + retry_after
        logger.warning(f"⚠️ [SARVAM 429] Rate limit reached. Cooling down for {retry_after}s until {self.cooldown_until}.")

    async def _get_cached_tts(self, audio_hash: str) -> Optional[str]:
        try:
            from backend.app.database import AsyncSessionLocal
            from backend.app.models.schemas import TTSCacheModel
            from sqlalchemy.future import select
            async with AsyncSessionLocal() as db:
                res = await db.execute(select(TTSCacheModel).where(TTSCacheModel.audio_hash == audio_hash))
                item = res.scalars().first()
                if item:
                    return item.audio_base64
        except Exception:
            pass
        return None

    async def _save_cached_tts(self, audio_hash: str, text: str, language: str, speaker: str, audio_b64: str):
        try:
            from backend.app.database import AsyncSessionLocal
            from backend.app.models.schemas import TTSCacheModel
            from sqlalchemy.future import select
            async with AsyncSessionLocal() as db:
                existing = await db.execute(select(TTSCacheModel).where(TTSCacheModel.audio_hash == audio_hash))
                if not existing.scalars().first():
                    db.add(TTSCacheModel(
                        audio_hash=audio_hash,
                        text=text,
                        language=language,
                        speaker=speaker,
                        audio_base64=audio_b64,
                        engine="sarvam_bulbul"
                    ))
                    await db.commit()
        except Exception:
            pass

    async def speech_to_text(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        content_type: str = "audio/wav",
        language_code: Optional[str] = None
    ) -> Tuple[str, str, str]:
        """
        Transcribes Indic speech using Sarvam Saaras STT API.
        Reference: https://docs.sarvam.ai/api-reference/speech-to-text
        """
        if not self.is_configured:
            raise RuntimeError("Sarvam STT unavailable or in cooldown")

        sarvam_lang = SARVAM_LANG_MAP.get(language_code or "hi", "hi-IN")
        headers = {"api-subscription-key": self.api_key}
        files = {"file": (filename, audio_bytes, content_type)}
        data = {"model": "saaras:v2", "language_code": sarvam_lang}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/speech-to-text",
                    headers=headers,
                    files=files,
                    data=data
                )
                if response.status_code == 200:
                    res_json = response.json()
                    transcript = res_json.get("transcript", "").strip()
                    detected_lang = res_json.get("language_code", sarvam_lang)
                    return transcript, detected_lang, "sarvam_saaras:v2"
                elif response.status_code == 429:
                    retry_sec = int(response.headers.get("Retry-After", 60))
                    self._handle_rate_limit(retry_sec)
                    raise RuntimeError("Sarvam STT rate limit 429")
                elif response.status_code in [401, 402, 403]:
                    self._trip_circuit(f"HTTP {response.status_code} - {response.text}")
                    raise RuntimeError(f"Sarvam STT permanent authorization/quota error: {response.status_code}")
                else:
                    raise RuntimeError(f"Sarvam STT error: HTTP {response.status_code}")
        except Exception as e:
            if "402" in str(e) or "403" in str(e) or "credit" in str(e).lower():
                self._trip_circuit(str(e))
            raise e

    def _extract_clean_summary(self, text: str, max_chars: int = 250) -> str:
        """
        Extracts whole sentences ending on '.' or '।' (Devanagari danda).
        Prevents mid-word or mid-sentence truncation for speech synthesis (Task 7).
        """
        # Split on sentence boundary characters
        tokens = re.split(r'([.।\n])', text)
        sentences = []
        for i in range(0, len(tokens) - 1, 2):
            s = (tokens[i] + tokens[i+1]).strip()
            if s:
                sentences.append(s)

        if not sentences:
            return text[:max_chars].strip()

        accumulated = []
        cur_len = 0
        for sent in sentences:
            if cur_len + len(sent) > max_chars and accumulated:
                break
            accumulated.append(sent)
            cur_len += len(sent)

        return " ".join(accumulated).strip() or sentences[0]

    async def text_to_speech(
        self,
        text: str,
        target_language: str = "hi",
        speaker: str = "kavya"
    ) -> Tuple[str, str]:
        """
        Synthesizes speech using Sarvam Bulbul TTS API with clean sentence boundary summaries.
        Reference: https://docs.sarvam.ai/api-reference/text-to-speech
        """
        sarvam_lang = SARVAM_LANG_MAP.get(target_language, "hi-IN")
        valid_speaker = speaker if speaker in VALID_BULBUL_SPEAKERS else "kavya"

        # Extract clean whole sentence summary up to ~250 chars
        clean_text = self._extract_clean_summary(text, max_chars=250)

        # 1. Check SQLite TTS cache
        audio_hash = hashlib.sha256(f"{clean_text}:{target_language}:{valid_speaker}".encode("utf-8")).hexdigest()
        cached_b64 = await self._get_cached_tts(audio_hash)
        if cached_b64:
            logger.info("🎯 TTS Cache hit (SQLite). Saved Sarvam credits.")
            return cached_b64, "sarvam_bulbul_cached"

        # 2. Check if Sarvam is configured and circuit intact
        if not self.is_configured:
            logger.info("Sarvam TTS bypassed (disabled or in cooldown). Returning synthetic fallback WAV.")
            mock_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
            return base64.b64encode(mock_wav).decode("utf-8"), "fallback_browser_speech"

        # Official bulbul:v3 payload schema (pitch & loudness omitted per docs)
        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "inputs": [clean_text],
            "target_language_code": sarvam_lang,
            "speaker": valid_speaker,
            "pace": 1.0,
            "speech_sample_rate": 16000,
            "enable_preprocessing": True,
            "model": "bulbul:v3"
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/text-to-speech",
                    headers=headers,
                    json=payload
                )
                if response.status_code == 200:
                    res_json = response.json()
                    audios = res_json.get("audios", [])
                    if audios:
                        b64 = audios[0]
                        await self._save_cached_tts(audio_hash, clean_text, target_language, valid_speaker, b64)
                        return b64, "sarvam_bulbul"
                    raise RuntimeError("No audio in Sarvam TTS response")
                elif response.status_code == 429:
                    retry_sec = int(response.headers.get("Retry-After", 60))
                    self._handle_rate_limit(retry_sec)
                elif response.status_code in [401, 402, 403]:
                    self._trip_circuit(f"HTTP {response.status_code} - {response.text}")
                else:
                    logger.error(f"Sarvam TTS error: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            if "402" in str(e) or "403" in str(e) or "credit" in str(e).lower():
                self._trip_circuit(str(e))

        mock_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        return base64.b64encode(mock_wav).decode("utf-8"), "fallback_browser_speech"

    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str
    ) -> Tuple[Optional[str], str]:
        """
        Translates text using Sarvam Mayura translation API with sentence chunking (Task 7).
        Reference: https://docs.sarvam.ai/api-reference/translate
        """
        source_code = SARVAM_LANG_MAP.get(source_language, "hi-IN")
        target_code = SARVAM_LANG_MAP.get(target_language, "en-IN")

        if source_code == target_code or not text.strip():
            return text, "passthrough"

        if not self.is_configured:
            return None, "translation_unavailable"

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json"
        }

        # Chunk text if over 800 chars on sentence boundaries
        chunks = []
        if len(text) > 800:
            sentences = re.split(r'([.।\n])', text)
            cur = ""
            for i in range(0, len(sentences) - 1, 2):
                s = sentences[i] + sentences[i+1]
                if len(cur) + len(s) > 750 and cur:
                    chunks.append(cur.strip())
                    cur = s
                else:
                    cur += s
            if cur.strip():
                chunks.append(cur.strip())
        else:
            chunks = [text]

        translated_chunks = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for chunk in chunks:
                    payload = {
                        "input": chunk,
                        "source_language_code": source_code,
                        "target_language_code": target_code,
                        "speaker_gender": "Female",
                        "mode": "formal",
                        "model": "mayura:v1"
                    }
                    response = await client.post(
                        f"{self.api_url}/translate",
                        headers=headers,
                        json=payload
                    )
                    if response.status_code == 200:
                        res_json = response.json()
                        tr = res_json.get("translated_text", "")
                        translated_chunks.append(tr)
                    elif response.status_code == 429:
                        self._handle_rate_limit(60)
                        return None, "sarvam_rate_limited"
                    elif response.status_code in [401, 402, 403]:
                        self._trip_circuit(f"HTTP {response.status_code} - {response.text}")
                        return None, "sarvam_credits_exhausted"
                    else:
                        return None, f"sarvam_error_{response.status_code}"

            if translated_chunks:
                return " ".join(translated_chunks), "sarvam_mayura"
        except Exception as e:
            if "402" in str(e) or "403" in str(e) or "credit" in str(e).lower():
                self._trip_circuit(str(e))
            logger.debug(f"Sarvam translation exception: {e}")

        return None, "translation_unavailable"

sarvam_service = SarvamService()
