import re
import logging
from typing import Tuple, List, Dict
from backend.app.config import settings

logger = logging.getLogger(__name__)

INTENT_CANDIDATES = [
    "crop_advisory",
    "market_prices",
    "weather",
    "pest_control",
    "scheme_lookup"
]

# Domain agricultural keyword patterns for high-precision intent routing
INTENT_PATTERNS = {
    "market_prices": [
        r"\b(price|mandi|market|rate|cost|apmc|modal price|bhav|keemat)\b",
        r"\b(how much is|selling rate|wholesale|retail price)\b"
    ],
    "weather": [
        r"\b(weather|rain|rainfall|forecast|temperature|humidity|wind|cloud|cyclone|monsoon|mausam)\b",
        r"\b(will it rain|is it going to rain)\b"
    ],
    "pest_control": [
        r"\b(pest|insect|disease|fungus|blight|caterpillar|borer|armyworm|leaf curl|rust|bollworm|rot|wilt|damage)\b",
        r"\b(pesticide|insecticide|fungicide|spray|chlorantraniliprole|neem oil|yellow sticky trap)\b",
        r"\b(yellowing|spots|holes|eating leaves|curling)\b"
    ],
    "scheme_lookup": [
        r"\b(scheme|subsidy|pm[- ]?kisan|pmfby|kcc|kisan credit card|insurance|loan|grant|financial assistance|eligib|yojana)\b",
        r"\b(government support|claim|soil health card)\b"
    ],
    "crop_advisory": [
        r"\b(crop|sowing|seed|transplant|fertilizer|npk|urea|dap|irrigation|water|harvest|spacing|variety|yield|soil)\b",
        r"\b(how to grow|cultivation|package of practices|management)\b"
    ]
}

class IntentClassifierService:
    """
    Agricultural Intent Classification Service.
    Uses Hugging Face zero-shot classification (facebook/bart-large-mnli)
    with domain-specialized agricultural keyword and regex fallback.
    """

    def __init__(self):
        self.model_name = settings.HF_INTENT_MODEL
        self._pipeline = None
        self._hf_available = False

    def _load_hf_pipeline(self):
        """Lazy load Hugging Face pipeline only when explicitly enabled for local development."""
        if not settings.ENABLE_HF_LOCAL:
            return

        if self._pipeline is not None or self._hf_available:
            return

        try:
            from transformers import pipeline
            logger.info(f"Loading Hugging Face intent classification pipeline ({self.model_name})...")
            token = settings.HF_TOKEN.strip() if (settings.HF_TOKEN and settings.HF_TOKEN.strip()) else None
            self._pipeline = pipeline("zero-shot-classification", model=self.model_name, token=token)
            self._hf_available = True
            logger.info("Hugging Face intent pipeline loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not load Hugging Face model {self.model_name}: {e}. Using high-precision rule-based agricultural classifier.")
            self._hf_available = False

    def classify_intent(self, canonical_text: str) -> Tuple[str, float, str]:
        """
        Classifies intent of canonical query.
        Returns: (intent, confidence, model_used)
        """
        text_lower = canonical_text.lower()

        # 1. Check domain-specific agricultural patterns first for instant high-confidence routing
        matched_scores: Dict[str, float] = {intent: 0.0 for intent in INTENT_CANDIDATES}
        for intent, patterns in INTENT_PATTERNS.items():
            for p in patterns:
                matches = re.findall(p, text_lower)
                if matches:
                    matched_scores[intent] += 0.45 * len(matches)

        top_rule_intent = max(matched_scores, key=matched_scores.get)
        top_rule_score = matched_scores[top_rule_intent]

        if top_rule_score >= 0.45:
            confidence = min(0.98, 0.70 + top_rule_score * 0.15)
            return top_rule_intent, round(confidence, 2), "agri_domain_rule_classifier"

        # 2. If ambiguous, attempt Hugging Face zero-shot classification
        try:
            self._load_hf_pipeline()
            if self._pipeline is not None:
                labels = [
                    "crop management and cultivation practice",
                    "agricultural mandi market prices",
                    "weather forecast and rain",
                    "crop pest control and plant diseases",
                    "government agricultural schemes and subsidy"
                ]
                label_to_intent = {
                    "crop management and cultivation practice": "crop_advisory",
                    "agricultural mandi market prices": "market_prices",
                    "weather forecast and rain": "weather",
                    "crop pest control and plant diseases": "pest_control",
                    "government agricultural schemes and subsidy": "scheme_lookup"
                }

                result = self._pipeline(canonical_text, candidate_labels=labels)
                top_label = result["labels"][0]
                hf_intent = label_to_intent.get(top_label, "crop_advisory")
                hf_confidence = float(result["scores"][0])
                return hf_intent, round(hf_confidence, 2), f"hf_{self.model_name}"
        except Exception as e:
            logger.warning(f"HF intent inference error: {e}")

        # 3. Default fallback
        return "crop_advisory", 0.65, "fallback_default_crop_advisory"

intent_classifier = IntentClassifierService()
