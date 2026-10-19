import re
import logging
from typing import Tuple, Optional
from backend.app.services.nlp.sarvam_service import sarvam_service

logger = logging.getLogger(__name__)

class TranslationService:
    """
    Manages language detection, translation to canonical English for internal processing,
    and back-translation to the farmer's native language (Hindi, Kannada).
    """

    @staticmethod
    def detect_language(text: str) -> str:
        """
        Detects whether the input text is in Hindi ('hi'), Kannada ('kn'), or English ('en')
        based on Unicode character scripts.
        """
        if not text or not text.strip():
            return "en"

        hi_count = 0
        kn_count = 0
        en_count = 0

        for char in text:
            cp = ord(char)
            # Devanagari range: \u0900 - \u097F
            if 0x0900 <= cp <= 0x097F:
                hi_count += 1
            # Kannada range: \u0C80 - \u0CFF
            elif 0x0C80 <= cp <= 0x0CFF:
                kn_count += 1
            # Basic Latin range: A-Z, a-z
            elif 0x0041 <= cp <= 0x005A or 0x0061 <= cp <= 0x007A:
                en_count += 1

        if hi_count > kn_count and hi_count > en_count:
            return "hi"
        elif kn_count > hi_count and kn_count > en_count:
            return "kn"
        elif en_count > 0:
            return "en"

        # Default fallback
        return "hi" if hi_count > 0 else ("kn" if kn_count > 0 else "en")

    async def to_canonical(
        self,
        text: str,
        source_language: Optional[str] = None
    ) -> Tuple[str, str, str]:
        """
        Translates input query into canonical English for NLP pipeline and RAG ingestion.
        Returns: (canonical_text, detected_language, engine_used)
        """
        detected_lang = source_language or self.detect_language(text)

        if detected_lang.startswith("en"):
            return text.strip(), "en", "passthrough"

        translated_text, engine = await sarvam_service.translate(
            text=text,
            source_language=detected_lang,
            target_language="en"
        )
        return translated_text, detected_lang, engine

    async def from_canonical(
        self,
        canonical_text: str,
        target_language: str
    ) -> Tuple[str, str]:
        """
        Translates canonical English response back into farmer's requested language.
        Returns: (translated_response, engine_used)
        """
        if target_language.startswith("en"):
            return canonical_text, "passthrough"

        translated_text, engine = await sarvam_service.translate(
            text=canonical_text,
            source_language="en",
            target_language=target_language
        )
        return translated_text, engine

translation_service = TranslationService()
