import logging
import base64
import hashlib
import httpx
from typing import Optional, Dict, Any, Tuple
from backend.app.config import settings

logger = logging.getLogger(__name__)

# Standard language mapping to Sarvam BCP-47 codes
SARVAM_LANG_MAP = {
    "hi": "hi-IN",
    "kn": "kn-IN",
    "en": "en-IN",
    "hi-IN": "hi-IN",
    "kn-IN": "kn-IN",
    "en-IN": "en-IN",
}

class SarvamService:
    """
    Sarvam AI client for Indic speech-to-text, text-to-speech, and translation.
    Equipped with:
      - Circuit breaker on credit exhaustion (HTTP 402/403/429) that logs once and switches to fallbacks
      - SARVAM_ENABLED toggle for zero-credit local development
      - SQLite audio caching by hash of (text, language, speaker)
      - Text length capping to save credits
    """

    def __init__(self):
        self.api_key = settings.SARVAM_API_KEY
        self.api_url = settings.SARVAM_API_URL.rstrip("/")
        self.circuit_broken = False
        self.circuit_broken_reason = None

    @property
    def is_configured(self) -> bool:
        return bool(
            settings.SARVAM_ENABLED and
            self.api_key and
            self.api_key.strip() and
            not self.api_key.startswith("your_") and
            not self.circuit_broken
        )

    def _trip_circuit(self, reason: str):
        if not self.circuit_broken:
            self.circuit_broken = True
            self.circuit_broken_reason = reason
            logger.error(f"🚨 [CIRCUIT BREAKER] Sarvam AI disabled for rest of session. Reason: {reason}. Switching to free-tier fallbacks.")

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
        Transcribe Indic speech using Sarvam Saaras STT API.
        Returns: (transcript, language_code, engine_used)
        """
        if not self.is_configured:
            logger.info(f"Sarvam STT not active (enabled={settings.SARVAM_ENABLED}, broken={self.circuit_broken}). Falling back to secondary STT.")
            raise RuntimeError("Sarvam STT unavailable or disabled")

        sarvam_lang = SARVAM_LANG_MAP.get(language_code or "hi", "hi-IN")
        headers = {"api-subscription-key": self.api_key}
        files = {"file": (filename, audio_bytes, content_type)}
        data = {"model": "saaras:v1", "language_code": sarvam_lang}

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
                    transcript = res_json.get("transcript", "")
                    detected_lang = res_json.get("language_code", sarvam_lang)
                    return transcript, detected_lang, "sarvam_saaras"
                elif response.status_code in [401, 402, 403, 429]:
                    self._trip_circuit(f"HTTP {response.status_code} - {response.text}")
                    raise RuntimeError(f"Sarvam STT credit limit reached: {response.status_code}")
                else:
                    logger.error(f"Sarvam STT error: HTTP {response.status_code} - {response.text}")
                    raise RuntimeError(f"Sarvam STT failed with status {response.status_code}")
        except Exception as e:
            if "credit limit" in str(e) or "402" in str(e) or "403" in str(e):
                self._trip_circuit(str(e))
            raise e

    async def text_to_speech(
        self,
        text: str,
        target_language: str = "hi",
        speaker: str = "kavya"
    ) -> Tuple[str, str]:
        """
        Synthesize speech using Sarvam Bulbul TTS API with SQLite caching and length capping.
        Returns: (base64_audio, engine_used)
        """
        sarvam_lang = SARVAM_LANG_MAP.get(target_language, "hi-IN")
        # Cap text to ~250 characters (short farmer summary) to minimize credit consumption
        capped_text = text[:250].strip()
        valid_speaker = speaker if speaker in ["kavya", "priya", "roopa", "aditya", "rahul", "shreya", "neha"] else "kavya"

        # 1. Check SQLite TTS cache
        audio_hash = hashlib.sha256(f"{capped_text}:{target_language}:{valid_speaker}".encode("utf-8")).hexdigest()
        cached_b64 = await self._get_cached_tts(audio_hash)
        if cached_b64:
            logger.info("🎯 TTS Cache hit (SQLite). Saved Sarvam credits.")
            return cached_b64, "sarvam_bulbul_cached"

        # 2. Check if Sarvam is configured and circuit intact
        if not self.is_configured:
            logger.info("Sarvam TTS bypassed (disabled or unconfigured). Returning synthetic fallback WAV.")
            mock_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
            return base64.b64encode(mock_wav).decode("utf-8"), "mock_sarvam_tts"

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "inputs": [capped_text],
            "target_language_code": sarvam_lang,
            "speaker": valid_speaker,
            "pitch": 0,
            "pace": 1.0,
            "loudness": 1.5,
            "speech_sample_rate": 8000,
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
                        await self._save_cached_tts(audio_hash, capped_text, target_language, valid_speaker, b64)
                        return b64, "sarvam_bulbul"
                    raise RuntimeError("No audio in Sarvam TTS response")
                elif response.status_code in [401, 402, 403, 429]:
                    self._trip_circuit(f"HTTP {response.status_code} - {response.text}")
                    # Return synthetic WAV on credit exhaustion
                    mock_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
                    return base64.b64encode(mock_wav).decode("utf-8"), "fallback_browser_speech"
                else:
                    logger.error(f"Sarvam TTS error: HTTP {response.status_code} - {response.text}")
                    mock_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
                    return base64.b64encode(mock_wav).decode("utf-8"), "fallback_browser_speech"
        except Exception as e:
            if "402" in str(e) or "credit" in str(e).lower():
                self._trip_circuit(str(e))
            mock_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
            return base64.b64encode(mock_wav).decode("utf-8"), "fallback_browser_speech"

    async def translate(
        self,
        text: str,
        source_language: str,
        target_language: str
    ) -> Tuple[str, str]:
        """
        Translate text using Sarvam Mayura translation API.
        Returns: (translated_text, engine_used)
        """
        source_code = SARVAM_LANG_MAP.get(source_language, "hi-IN")
        target_code = SARVAM_LANG_MAP.get(target_language, "en-IN")

        if source_code == target_code or not text.strip():
            return text, "passthrough"

        if not self.is_configured:
            logger.info("Sarvam translate disabled or unconfigured. Falling back to dictionary/LLM.")
            return self._mock_translate(text, source_language, target_language), "mock_sarvam_mayura"

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "input": text[:950],
            "source_language_code": source_code,
            "target_language_code": target_code,
            "speaker_gender": "Female",
            "mode": "formal",
            "model": "mayura:v1"
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.api_url}/translate",
                    headers=headers,
                    json=payload
                )
                if response.status_code == 200:
                    res_json = response.json()
                    translated = res_json.get("translated_text", text)
                    return translated, "sarvam_mayura"
                elif response.status_code in [401, 402, 403, 429]:
                    self._trip_circuit(f"HTTP {response.status_code} - {response.text}")
                    return self._mock_translate(text, source_language, target_language), "mock_sarvam_mayura_fallback"
                else:
                    return self._mock_translate(text, source_language, target_language), "mock_sarvam_mayura_fallback"
        except Exception as e:
            if "402" in str(e) or "credit" in str(e).lower():
                self._trip_circuit(str(e))
            return self._mock_translate(text, source_language, target_language), "mock_sarvam_mayura_fallback"

    def _mock_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Deterministic domain dictionary translator fallback."""
        hi_to_en = {
            "टमाटर": "tomato", "धान": "paddy", "चावल": "rice", "गेहूं": "wheat",
            "मक्का": "maize", "कपास": "cotton", "मंडी": "mandi market", "भाव": "price",
            "कीमत": "price", "मौसम": "weather", "बारिश": "rainfall", "कीट": "pest",
            "रोकथाम": "control remedy", "योजना": "scheme", "सब्सिडी": "subsidy",
            "खाद": "fertilizer", "पत्ता मरोड़": "leaf curl virus", "तना छेदक": "stem borer",
            "पीला रतुआ": "yellow rust", "गन्ना": "sugarcane", "सोयाबीन": "soybean",
            "मूंगफली": "groundnut", "सरसों": "mustard", "आलू": "potato", "प्याज": "onion", "मिर्च": "chilli"
        }
        kn_to_en = {
            "ಟೊಮೆಟೊ": "tomato", "ಭತ್ತ": "paddy", "ಗೋಧಿ": "wheat", "ಮೆಕ್ಕೆಜೋಳ": "maize",
            "ಹತ್ತಿ": "cotton", "ಮಾರುಕಟ್ಟೆ": "market", "ಬೆಲೆ": "price", "ಹವಾಮಾನ": "weather",
            "ಮಳೆ": "rain", "ಹುಳು": "pest", "ರೋಗ": "disease", "ಯೋಜನೆ": "scheme",
            "ಸಹಾಯಧನ": "subsidy", "ಗೊಬ್ಬರ": "fertilizer", "ಕಬ್ಬು": "sugarcane", "ಸೋಯಾಬೀನ್": "soybean",
            "ಕಡಲೆಕಾಯಿ": "groundnut", "ಸಾಸಿವೆ": "mustard", "ಆಲೂಗಡ್ಡೆ": "potato", "ಈರುಳ್ಳಿ": "onion", "ಮೆಣಸಿನಕಾಯಿ": "chilli"
        }
        if target_lang.startswith("en"):
            words = text.split()
            translated_words = []
            lookup = hi_to_en if source_lang.startswith("hi") else kn_to_en
            for w in words:
                cleaned = w.strip("।,?!")
                translated_words.append(lookup.get(cleaned, w))
            return f"[Canonical EN] {' '.join(translated_words)}"
        else:
            lang_label = "Hindi" if target_lang.startswith("hi") else "Kannada"
            return f"[{lang_label} Response] {text}"

sarvam_service = SarvamService()
