import re
import logging
from typing import List, Dict, Any
from backend.app.models.schemas import EntityItem
from backend.app.config import settings

logger = logging.getLogger(__name__)

# Agricultural Domain Gazetteers
CROPS_GAZETTEER = [
    "paddy", "rice", "wheat", "tomato", "cotton", "maize", "corn",
    "sugarcane", "soybean", "groundnut", "mustard", "gram", "onion",
    "potato", "chilli", "turmeric", "banana", "mango", "pulses"
]

PESTS_DISEASES_GAZETTEER = [
    "yellow stem borer", "stem borer", "fall armyworm", "armyworm",
    "leaf curl virus", "leaf curl", "yellow rust", "stripe rust", "rust",
    "pink bollworm", "bollworm", "whitefly", "aphid", "thrips", "bacterial wilt",
    "early blight", "late blight", "powdery mildew", "downy mildew", "dead heart"
]

INPUTS_GAZETTEER = [
    "urea", "dap", "npk", "mop", "zinc sulfate", "zinc", "manure", "fym",
    "pretilachlor", "chlorantraniliprole", "pendimethalin", "sulfosulfuron",
    "imidacloprid", "emamectin benzoate", "propiconazole", "neem oil", "biofertilizer"
]

SCHEMES_GAZETTEER = [
    "pm-kisan", "pm kisan", "pmfby", "fasal bima", "kcc", "kisan credit card",
    "soil health card", "pkvy", "pmksy", "krishi sinchayee"
]

LOCATIONS_GAZETTEER = [
    "karnataka", "bengaluru", "bangalore", "mandya", "mysore", "mysuru",
    "dharwad", "belagavi", "shimoga", "shivamogga", "hassan", "punjab",
    "haryana", "maharashtra", "madhya pradesh", "uttar pradesh", "rajasthan"
]

class AgriculturalNERService:
    """
    Named Entity Recognition for Agricultural Vocabulary.
    Extracts CROP, PEST_DISEASE, INPUT, SCHEME, and LOCATION entities
    using Hugging Face dslim/bert-base-NER combined with a verified Agricultural Gazetteer.
    """

    def __init__(self):
        self.model_name = settings.HF_NER_MODEL
        self._pipeline = None
        self._hf_loaded = False

    def _load_hf_pipeline(self):
        if not settings.ENABLE_HF_LOCAL:
            return
        if self._pipeline is not None or self._hf_loaded:
            return
        try:
            from transformers import pipeline
            logger.info(f"Loading Hugging Face NER pipeline ({self.model_name})...")
            token = settings.HF_TOKEN.strip() if (settings.HF_TOKEN and settings.HF_TOKEN.strip()) else None
            self._pipeline = pipeline("ner", model=self.model_name, aggregation_strategy="simple", token=token)
            self._hf_loaded = True
            logger.info("HF NER pipeline loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not load Hugging Face NER model {self.model_name}: {e}. Utilizing Agri Gazetteer extraction.")
            self._hf_loaded = True

    def extract_entities(self, text: str) -> List[EntityItem]:
        """
        Extracts agricultural and general entities from canonical text.
        """
        entities: List[EntityItem] = []
        seen_spans = set()
        text_lower = text.lower()

        # 1. Agricultural Domain Gazetteer Extraction (Prioritized)
        def match_gazetteer(gazetteer: List[str], label: str):
            for item in sorted(gazetteer, key=len, reverse=True):
                pattern = r"\b" + re.escape(item) + r"\b"
                for m in re.finditer(pattern, text_lower):
                    span = (m.start(), m.end())
                    if span not in seen_spans:
                        seen_spans.add(span)
                        matched_text = text[m.start():m.end()]
                        entities.append(EntityItem(
                            text=matched_text,
                            label=label,
                            confidence=0.95
                        ))

        match_gazetteer(CROPS_GAZETTEER, "CROP")
        match_gazetteer(PESTS_DISEASES_GAZETTEER, "PEST_DISEASE")
        match_gazetteer(INPUTS_GAZETTEER, "INPUT")
        match_gazetteer(SCHEMES_GAZETTEER, "SCHEME")
        match_gazetteer(LOCATIONS_GAZETTEER, "LOCATION")

        # 2. General NER extraction using Hugging Face (e.g. general locations/organizations)
        try:
            self._load_hf_pipeline()
            if self._pipeline is not None:
                hf_results = self._pipeline(text)
                for res in hf_results:
                    word = res.get("word", "").strip()
                    entity_group = res.get("entity_group", "MISC")
                    score = float(res.get("score", 0.8))
                    # Avoid duplicate or sub-word fragments
                    if len(word) > 2 and not any(e.text.lower() == word.lower() for e in entities):
                        entities.append(EntityItem(
                            text=word,
                            label=entity_group,
                            confidence=round(score, 2)
                        ))
        except Exception as e:
            logger.debug(f"HF NER extraction skipped: {e}")

        return entities

ner_service = AgriculturalNERService()
