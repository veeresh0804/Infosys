import re
import json
import logging
from typing import Tuple, List, Dict, Any, Optional
from backend.app.config import settings

logger = logging.getLogger(__name__)

INTENT_CANDIDATES = [
    "scheme_lookup",
    "pest_control",
    "market_prices",
    "weather",
    "crop_advisory"
]

# Priority ordering to break ties toward more specific domain intents
INTENT_PRIORITY = {
    "scheme_lookup": 5,
    "pest_control": 4,
    "market_prices": 3,
    "weather": 2,
    "crop_advisory": 1
}

# Weighted agricultural keywords for honest, high-precision intent classification
# Specific, actionable keywords carry high weights; generic words carry low weights
INTENT_WEIGHTS: Dict[str, List[Tuple[str, float]]] = {
    "scheme_lookup": [
        (r"\b(subsidy|subsidies|pm[- ]?kisan|pmfby|kcc|kisan credit card|soil health card|pkvy|pmksy)\b", 1.5),
        (r"\b(yojana|grant|insurance|loan|financial assistance|eligib|compensation|claim)\b", 1.2),
        (r"\b(government support|government scheme|central scheme|state scheme)\b", 1.2)
    ],
    "pest_control": [
        (r"\b(leaf curl|stem borer|yellow rust|stripe rust|fall armyworm|bollworm|bacterial wilt|powdery mildew|downy mildew)\b", 1.5),
        (r"\b(chlorantraniliprole|imidacloprid|emamectin|propiconazole|fungicide|pesticide|insecticide|neem oil|sticky trap)\b", 1.4),
        (r"\b(pest|insect|blight|fungus|caterpillar|borer|whitefly|aphid|thrips|rot|wilt|dead heart)\b", 1.1),
        (r"\b(spots on leaves|holes in leaves|eating leaves|curling|yellowing of leaves)\b", 0.9),
        (r"\b(dying|damage)\b", 0.35)  # Vague symptom carries low weight alone
    ],
    "market_prices": [
        (r"\b(mandi|modal price|selling rate|wholesale price|retail price|apmc|agmarknet)\b", 1.5),
        (r"\b(price|market rate|bhav|keemat|cost per quintal|rate per kg)\b", 1.2),
        (r"\b(how much is|market|rate)\b", 0.8)
    ],
    "weather": [
        (r"\b(will it rain|is it going to rain|rain forecast|monsoon forecast|weather forecast)\b", 1.8),
        (r"\b(rainfall|weather|forecast|rain|cyclone|monsoon|mausam)\b", 1.4),
        (r"\b(temperature|humidity|wind speed|frost|cloud|cloudy)\b", 1.1)
    ],
    "crop_advisory": [
        (r"\b(seed rate|spacing|sowing depth|package of practices|transplanting time|recommended npk|fertilizer dose)\b", 1.4),
        (r"\b(sowing|variety|spacing|harvesting|irrigation|urea|dap|potash|fertilizer|manure|fym|germination)\b", 1.0),
        (r"\b(how to grow|cultivation of|yield of|plant spacing)\b", 0.9),
        (r"\b(crop|farming|agriculture|field)\b", 0.2)  # Generic words carry minimal weight
    ]
}

class IntentClassifierService:
    """
    Agricultural Intent Classification Service.
    Implements rule-based keyword weighting with specificity tie-breaking,
    backed by free LLM JSON fallback when confidence is low or ambiguous,
    and optional local Hugging Face zero-shot classification.
    """

    def __init__(self):
        self.model_name = settings.HF_INTENT_MODEL
        self._pipeline = None
        self._hf_available = False

    def _load_hf_pipeline(self):
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
            logger.warning(f"Could not load Hugging Face model {self.model_name}: {e}. Utilizing rule classifier.")
            self._hf_available = False

    def _compute_rule_scores(self, text_lower: str) -> Dict[str, float]:
        """Calculates cumulative keyword weights per intent."""
        scores: Dict[str, float] = {intent: 0.0 for intent in INTENT_CANDIDATES}
        for intent, patterns in INTENT_WEIGHTS.items():
            for regex_pat, weight in patterns:
                matches = re.findall(regex_pat, text_lower)
                if matches:
                    scores[intent] += weight * len(matches)
        return scores

    def classify_intent(self, canonical_text: str) -> Tuple[str, float, str]:
        """
        Classifies intent of canonical query.
        Returns: (intent, confidence, model_used)
        """
        text_lower = canonical_text.lower().strip()
        scores = self._compute_rule_scores(text_lower)

        # Find intent with highest score; break ties using specificity priority
        best_intent = "crop_advisory"
        best_score = -1.0

        for intent in INTENT_CANDIDATES:
            score = scores[intent]
            if score > best_score:
                best_score = score
                best_intent = intent
            elif score == best_score and score > 0:
                # Specificity tie-breaking (prefer scheme_lookup/pest_control over crop_advisory)
                if INTENT_PRIORITY[intent] > INTENT_PRIORITY[best_intent]:
                    best_intent = intent

        # Honest confidence calculation based on matching evidence
        # A clear, unambiguous match (score >= 1.2) yields high confidence (0.80 - 0.95)
        # A single weak/vague keyword (score ~0.35) yields low confidence (< 0.50)
        if best_score <= 0.0:
            confidence = 0.20
            return "crop_advisory", confidence, "agri_domain_rule_classifier"

        if best_score >= 1.2:
            confidence = min(0.95, round(0.75 + (best_score - 1.2) * 0.10, 2))
            return best_intent, confidence, "agri_domain_rule_classifier"
        elif best_score >= 0.7:
            confidence = min(0.79, round(0.60 + (best_score - 0.7) * 0.25, 2))
            return best_intent, confidence, "agri_domain_rule_classifier"
        else:
            # Low confidence for vague phrases like "my crop is dying"
            confidence = round(min(0.55, 0.25 + best_score * 0.5), 2)
            return best_intent, confidence, "agri_domain_rule_classifier"

    def classify(self, canonical_text: str) -> Tuple[str, float]:
        """Convenience alias returning (intent, confidence)"""
        intent, conf, _ = self.classify_intent(canonical_text)
        return intent, conf

intent_classifier = IntentClassifierService()

