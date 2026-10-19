import re
import logging
from typing import Tuple, Optional, Dict
from backend.app.config import settings
from backend.app.services.nlp.sarvam_service import sarvam_service

logger = logging.getLogger(__name__)

# Real last-resort agricultural domain dictionary fallback (Task 4)
AGRICULTURAL_DICTIONARY: Dict[str, str] = {
    # Hindi Keywords & Crops
    "टमाटर": "tomato",
    "धान": "paddy rice",
    "चावल": "rice",
    "गेहूं": "wheat",
    "कपास": "cotton",
    "मक्का": "maize",
    "गन्ना": "sugarcane",
    "सोयाबीन": "soybean",
    "मूंगफली": "groundnut",
    "सरसों": "mustard",
    "चना": "gram chickpea",
    "प्याज": "onion",
    "आलू": "potato",
    "मिर्च": "chilli",
    "कीट": "pest insect",
    "रोग": "disease",
    "रोकथाम": "prevention control",
    "इलाज": "treatment control",
    "उपाय": "remedy control",
    "दवा": "medicine pesticide",
    "खाद": "fertilizer manure",
    "उर्वरक": "fertilizer",
    "बीज": "seed",
    "सिंचाई": "irrigation water",
    "भाव": "mandi market price",
    "दाम": "market price",
    "मौसम": "weather forecast",
    "बारिश": "rain rainfall",
    "योजना": "government scheme",
    "सब्सिडी": "subsidy",
    "पत्ता मरोड़": "leaf curl virus",
    "पीले": "yellowing",
    "पत्ते": "leaves",
    # Kannada Keywords & Crops
    "ಟೊಮೆಟೊ": "tomato",
    "ಭತ್ತ": "paddy rice",
    "ಅಕ್ಕಿ": "rice",
    "ಗೋಧಿ": "wheat",
    "ಹತ್ತಿ": "cotton",
    "ಮೆಕ್ಕೆಜೋಳ": "maize",
    "ಕಬ್ಬು": "sugarcane",
    "ಸೋಯಾಬೀನ್": "soybean",
    "ಕಡಲೆಕಾಯಿ": "groundnut",
    "ಈರುಳ್ಳಿ": "onion",
    "ಆಲೂಗಡ್ಡೆ": "potato",
    "ಮೆಣಸಿನಕಾಯಿ": "chilli",
    "ರಾಗಿ": "ragi finger millet",
    "ಜೋಳ": "jowar sorghum",
    "ಬದನೆಕಾಯಿ": "brinjal eggplant",
    "ಅಡಿಕೆ": "arecanut",
    "ತೆಂಗು": "coconut",
    "ಕಾಫಿ": "coffee",
    "ಬಾಳೆ": "banana",
    "ಸೂರ್ಯಕಾಂತಿ": "sunflower",
    "ರೋಗ": "disease",
    "ಕೀಟ": "pest insect",
    "ಹಾನಿ": "damage",
    "ನಿಯಂತ್ರಣ": "control prevention",
    "ಔಷಧಿ": "medicine pesticide",
    "ಗೊಬ್ಬರ": "fertilizer manure",
    "ಬೀಜ": "seed",
    "ನೀರಾವರಿ": "irrigation water",
    "ಬೆಲೆ": "market price",
    "ದರ": "market rate",
    "ಮಾರುಕಟ್ಟೆ": "market mandi",
    "ಹವಾಮಾನ": "weather forecast",
    "ಮಳೆ": "rain rainfall",
    "ಯೋಜನೆ": "government scheme subsidy",
    "ಕಾಂಡ ಕೊರೆಯುವ ಹುಳು": "stem borer",
    "ಎಲೆ ಸುಡುವ ರೋಗ": "leaf blast disease",
    "ಎಲೆಗಳು": "leaves"
}

class TranslationService:
    """
    Manages language detection, translation to canonical English for internal processing,
    and back-translation to the farmer's native language (Hindi, Kannada).
    Provides honest failure flagging without silent fabrication or dummy [en] tags.
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

        return "hi" if hi_count > 0 else ("kn" if kn_count > 0 else "en")

    def _dictionary_fallback_translate(self, text: str) -> Optional[str]:
        """
        Deterministic last-resort agricultural dictionary fallback.
        Matches agricultural concepts and returns structured canonical English.
        """
        matched_en_terms = []
        # Check longer phrases first
        for term in sorted(AGRICULTURAL_DICTIONARY.keys(), key=len, reverse=True):
            if term in text:
                matched_en_terms.append(AGRICULTURAL_DICTIONARY[term])

        if matched_en_terms:
            # Deduplicate while preserving order
            unique_terms = list(dict.fromkeys(matched_en_terms))
            return " ".join(unique_terms)
        return None

    async def to_canonical(
        self,
        text: str,
        source_language: Optional[str] = None
    ) -> Tuple[Optional[str], str, str]:
        """
        Translates input query into canonical English for NLP pipeline and RAG ingestion.
        Returns: (canonical_text, detected_language, engine_used)
        If all translation engines fail, returns (None, detected_language, "translation_failed").
        """
        detected_lang = source_language or self.detect_language(text)

        if detected_lang.startswith("en"):
            return text.strip(), "en", "passthrough"

        # 1. Try Sarvam Mayura if enabled
        if settings.SARVAM_ENABLED and sarvam_service.is_configured and not sarvam_service.circuit_broken:
            try:
                translated_text, engine = await sarvam_service.translate(
                    text=text,
                    source_language=detected_lang,
                    target_language="en"
                )
                if engine and "mock" not in engine and "failed" not in engine:
                    return translated_text, detected_lang, engine
            except Exception as e:
                logger.warning(f"Sarvam translation failed ({e}). Falling back to free LLM chain.")

        # 2. Free LLM chain translation fallback (Gemini / Groq)
        from backend.app.services.rag.rag_engine import rag_engine
        translated_text, engine = await rag_engine.translate_text(
            text=text,
            source_language=detected_lang,
            target_language="en"
        )
        if engine and "mock" not in engine and "failed" not in engine and translated_text:
            return translated_text, detected_lang, engine

        # 3. Deterministic Domain Dictionary Fallback (Task 4)
        dict_trans = self._dictionary_fallback_translate(text)
        if dict_trans:
            logger.info("Used agricultural dictionary fallback translation.")
            return dict_trans, detected_lang, "domain_dictionary_fallback"

        # 4. Honest failure: never return fake [en] tags
        logger.warning(f"All translation engines failed for text: '{text[:50]}...'. Flagging translation_failed.")
        return None, detected_lang, "translation_failed"

    async def from_canonical(
        self,
        canonical_text: str,
        target_language: str
    ) -> Tuple[Optional[str], str]:
        """
        Translates canonical English response back into farmer's requested language.
        Returns: (translated_response, engine_used)
        """
        if target_language.startswith("en"):
            return canonical_text, "passthrough"

        # 1. Try Sarvam Mayura if enabled
        if settings.SARVAM_ENABLED and sarvam_service.is_configured and not sarvam_service.circuit_broken:
            try:
                translated_text, engine = await sarvam_service.translate(
                    text=canonical_text,
                    source_language="en",
                    target_language=target_language
                )
                if engine and "mock" not in engine and "failed" not in engine:
                    return translated_text, engine
            except Exception as e:
                logger.warning(f"Sarvam back-translation failed ({e}). Falling back to free LLM chain.")

        # 2. Free LLM chain translation fallback
        from backend.app.services.rag.rag_engine import rag_engine
        translated_text, engine = await rag_engine.translate_text(
            text=canonical_text,
            source_language="en",
            target_language=target_language
        )
        if engine and "mock" not in engine and "failed" not in engine and translated_text:
            return translated_text, engine

        # 3. Honest failure
        return None, "translation_failed"

translation_service = TranslationService()
