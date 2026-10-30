import re
import asyncio
import logging
from typing import Tuple, List, Dict, Optional

from backend.app.config import settings
from backend.app.services.rag.rag_engine import rag_engine

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
    Implements rule-based keyword weighting with specificity tie-breaking
    and honest, evidence-based confidence scoring.

    Full chain (per docs/FREE_TIER_DEVIATIONS.md §5):
      1. High-precision domain keyword/regex classifier (default, 0 MB RAM)
      2. Optional heavy HF zero-shot model `facebook/bart-large-mnli`
         (guarded behind ENABLE_HF_LOCAL=true; isolated in requirements-local.txt)
      3. Free LLM chain fallback (Gemini -> Groq) for ambiguous queries
    """

    def __init__(self):
        # Lazily-initialized HF zero-shot pipeline; only loaded when ENABLE_HF_LOCAL=true
        self._hf_pipeline = None

    def _compute_rule_scores(self, text_lower: str) -> Dict[str, float]:
        """Calculates cumulative keyword weights per intent."""
        scores: Dict[str, float] = {intent: 0.0 for intent in INTENT_CANDIDATES}
        for intent, patterns in INTENT_WEIGHTS.items():
            for regex_pat, weight in patterns:
                matches = re.findall(regex_pat, text_lower)
                if matches:
                    scores[intent] += weight * len(matches)
        return scores

    async def classify_intent_async(self, canonical_text: str) -> Tuple[str, float, str]:
        """
        Full classification chain for the Agent Router.
        Returns: (intent, confidence, model_used)
        """
        # 1. High-precision domain rule classifier (always applicable, zero-cost)
        rule_intent, rule_confidence, _ = self.classify_intent(canonical_text)
        if rule_confidence >= 0.60:
            return rule_intent, rule_confidence, "agri_domain_rule_classifier"

        # 2. Optional heavy HF zero-shot model (only when ENABLE_HF_LOCAL=true on >2GB RAM hosts)
        if settings.ENABLE_HF_LOCAL:
            hf_result = await self._classify_hf_local(canonical_text)
            if hf_result:
                return hf_result

        # 3. Free LLM chain fallback for ambiguous queries (Gemini -> Groq)
        llm_result = await rag_engine.classify_intent_llm(canonical_text)
        if llm_result:
            llm_intent, llm_confidence, engine_used = llm_result
            return llm_intent, llm_confidence, engine_used

        # Honest fallback: keep the rule decision with its honest low confidence
        return rule_intent, rule_confidence, "agri_domain_rule_classifier"

    async def _classify_hf_local(self, canonical_text: str) -> Optional[Tuple[str, float, str]]:
        """
        Zero-shot intent classification with facebook/bart-large-mnli.
        Heavy: ~1.63 GB on disk and >2 GB RAM at init - therefore guarded behind
        ENABLE_HF_LOCAL=true and only ever loaded lazily in a worker thread.
        """
        try:
            if self._hf_pipeline is None:
                def _init_pipeline():
                    from transformers import pipeline
                    return pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
                self._hf_pipeline = await asyncio.to_thread(_init_pipeline)

            label_phrases = {
                "crop_advisory": "general crop advisory and farm management",
                "pest_control": "pest or disease control on crops",
                "market_prices": "market prices for crops in the mandi",
                "weather": "weather and rainfall forecast",
                "scheme_lookup": "government scheme eligibility, subsidy or insurance"
            }

            def _classify():
                return self._hf_pipeline(
                    canonical_text,
                    candidate_labels=list(label_phrases.keys()),
                    hypothesis_template="This farmer query is about {}."
                )

            result = await asyncio.to_thread(_classify)
            top_intent = result["labels"][0]
            if top_intent not in INTENT_CANDIDATES:
                return None
            confidence = round(min(0.95, max(0.50, float(result["scores"][0]))), 2)
            return top_intent, confidence, "facebook_bart_large_mnli"
        except Exception as e:
            logger.warning(f"HF intent model unavailable (falling back to rule/LLM chain): {e}")
            self._hf_pipeline = None
            return None

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

