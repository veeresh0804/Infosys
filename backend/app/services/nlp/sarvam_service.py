import logging
import base64
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
    Official Sarvam AI client for Indic speech-to-text, text-to-speech, and translation.
    Documentation: https://docs.sarvam.ai/
    Models:
      - STT: Saaras (saaras:v1 / saaras:v2)
      - TTS: Bulbul (bulbul:v1)
      - Translation: Mayura (mayura:v1)
    """

    def __init__(self):
        self.api_key = settings.SARVAM_API_KEY
        self.api_url = settings.SARVAM_API_URL.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip() and not self.api_key.startswith("your_"))

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
            logger.warning("[MOCK] Sarvam AI API key not configured. Using clearly-labelled mock STT.")
            # Mock transcript based on default testing scenario
            return (
                "टमाटर की फसल में पत्ता मरोड़ रोग का क्या उपाय है?",
                "hi-IN",
                "mock_sarvam_stt"
            )

        sarvam_lang = SARVAM_LANG_MAP.get(language_code or "hi", "hi-IN")
        headers = {
            "api-subscription-key": self.api_key
        }
        files = {
            "file": (filename, audio_bytes, content_type)
        }
        data = {
            "model": "saaras:v1",
            "language_code": sarvam_lang
        }

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
                else:
                    logger.error(f"Sarvam STT error: HTTP {response.status_code} - {response.text}")
                    raise RuntimeError(f"Sarvam STT failed with status {response.status_code}")
        except Exception as e:
            logger.exception("Error contacting Sarvam STT API")
            raise e

    async def text_to_speech(
        self,
        text: str,
        target_language: str = "hi",
        speaker: str = "anushka"
    ) -> Tuple[str, str]:
        """
        Synthesize speech using Sarvam Bulbul TTS API.
        Returns: (base64_audio, engine_used)
        """
        sarvam_lang = SARVAM_LANG_MAP.get(target_language, "hi-IN")

        if not self.is_configured:
            logger.warning("[MOCK] Sarvam AI API key not configured. Returning clearly-labelled synthetic audio payload.")
            # Minimal valid WAV header for zero-cost testing
            mock_wav = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
            return base64.b64encode(mock_wav).decode("utf-8"), "mock_sarvam_tts"

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json"
        }
        # Valid Sarvam speakers for bulbul:v3 include: 'kavya', 'priya', 'roopa', 'aditya', 'rahul'
        valid_speaker = speaker if speaker in ["kavya", "priya", "roopa", "aditya", "rahul", "shreya", "neha"] else "kavya"
        payload = {
            "inputs": [text[:500]],
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
                        return audios[0], "sarvam_bulbul"
                    raise RuntimeError("No audio in Sarvam TTS response")
                else:
                    logger.error(f"Sarvam TTS error: HTTP {response.status_code} - {response.text}")
                    raise RuntimeError(f"Sarvam TTS failed with status {response.status_code}")
        except Exception as e:
            logger.exception("Error contacting Sarvam TTS API")
            raise e

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
            logger.info("[MOCK] Sarvam AI API key not configured. Using domain-specific dictionary & translation mock.")
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
                else:
                    logger.error(f"Sarvam translate error: HTTP {response.status_code} - {response.text}")
                    # Fallback to mock on API error
                    return self._mock_translate(text, source_language, target_language), "mock_sarvam_mayura_fallback"
        except Exception as e:
            logger.exception("Sarvam translation call failed, falling back to mock")
            return self._mock_translate(text, source_language, target_language), "mock_sarvam_mayura_fallback"

    def _mock_translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        Clearly-labelled deterministic mock translator for agricultural queries and advisories
        used when Sarvam API key is not yet configured.
        """
        # Hindi -> English common agricultural mappings
        hi_to_en = {
            "टमाटर": "tomato",
            "धान": "paddy",
            "चावल": "rice",
            "गेहूं": "wheat",
            "मक्का": "maize",
            "कपास": "cotton",
            "मंडी": "mandi market",
            "भाव": "price",
            "कीमत": "price",
            "मौसम": "weather",
            "बारिश": "rainfall",
            "कीट": "pest",
            "रोकथाम": "control remedy",
            "योजना": "scheme",
            "सब्सिडी": "subsidy",
            "खाद": "fertilizer",
            "पत्ता मरोड़": "leaf curl virus",
            "तना छेदक": "stem borer",
            "पीला रतुआ": "yellow rust"
        }

        # Kannada -> English common agricultural mappings
        kn_to_en = {
            "ಟೊಮೆಟೊ": "tomato",
            "ಭತ್ತ": "paddy",
            "ಗೋಧಿ": "wheat",
            "ಮೆಕ್ಕೆಜೋಳ": "maize",
            "ಹತ್ತಿ": "cotton",
            "ಮಾರುಕಟ್ಟೆ": "market",
            "ಬೆಲೆ": "price",
            "ಹವಾಮಾನ": "weather",
            "ಮಳೆ": "rain",
            "ಹುಳು": "pest",
            "ರೋಗ": "disease",
            "ಯೋಜನೆ": "scheme",
            "ಸಹಾಯಧನ": "subsidy",
            "ಗೊಬ್ಬರ": "fertilizer"
        }

        if target_lang.startswith("en"):
            # Translating to canonical English
            words = text.split()
            translated_words = []
            lookup = hi_to_en if source_lang.startswith("hi") else kn_to_en
            for w in words:
                cleaned = w.strip("।,?!")
                if cleaned in lookup:
                    translated_words.append(lookup[cleaned])
                else:
                    translated_words.append(w)
            return f"[Canonical EN] {' '.join(translated_words)}"
        else:
            # Back-translating from English to Hindi or Kannada
            lang_label = "Hindi" if target_lang.startswith("hi") else "Kannada"
            return f"[{lang_label} Response] {text}"

sarvam_service = SarvamService()
