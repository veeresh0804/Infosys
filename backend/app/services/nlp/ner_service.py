import re
import logging
from typing import List, Tuple
from backend.app.models.schemas import EntityItem
from backend.app.config import settings

logger = logging.getLogger(__name__)

# Agricultural Domain Gazetteers expanded with common Karnataka crops & pests
CROPS_GAZETTEER = [
    # Core Staples & Commercial Crops
    "paddy", "rice", "wheat", "cotton", "maize", "corn", "sugarcane", "soybean",
    "groundnut", "peanut", "mustard", "gram", "chickpea", "onion", "potato",
    "chilli", "turmeric", "pulses", "mango",
    # Karnataka Specific Major Crops (Task 5 requirement)
    "finger millet", "ragi",
    "sorghum", "jowar",
    "brinjal", "eggplant",
    "arecanut", "betel nut", "supari",
    "coconut",
    "coffee",
    "banana",
    "sunflower"
]

PESTS_DISEASES_GAZETTEER = [
    # Rice / Paddy
    "yellow stem borer", "stem borer", "blast disease", "neck blast", "finger blast", "blast",
    "sheath blight", "brown plant hopper", "leaf folder",
    # Tomato / Chilli / Vegetables
    "leaf curl virus", "leaf curl", "early blight", "late blight", "bacterial wilt",
    "fruit and shoot borer", "fruit borer", "shoot borer", "whitefly", "aphid", "thrips",
    # Karnataka Specific Crop Pests & Diseases (Ragi, Sorghum, Arecanut, Coconut, Coffee, Banana, Sunflower)
    "shoot fly",
    "koleroga", "mahali", "yellow leaf disease", "bud rot",
    "basal stem rot", "root wilt", "rhinoceros beetle", "red palm weevil",
    "coffee berry borer", "white stem borer", "coffee leaf rust", "rust",
    "panama wilt", "sigatoka leaf spot", "sigatoka", "bunchy top",
    "alternaria leaf spot", "head rot",
    # Cotton & General
    "fall armyworm", "armyworm", "pink bollworm", "bollworm", "yellow rust",
    "stripe rust", "powdery mildew", "downy mildew", "dead heart", "tikka disease"
]

INPUTS_GAZETTEER = [
    "urea", "dap", "npk", "mop", "zinc sulfate", "zinc", "manure", "fym",
    "pretilachlor", "chlorantraniliprole", "pendimethalin", "sulfosulfuron",
    "imidacloprid", "emamectin benzoate", "propiconazole", "tricyclazole",
    "kasugamycin", "neem oil", "biofertilizer", "trichoderma"
]

SCHEMES_GAZETTEER = [
    "pm-kisan", "pm kisan", "pmfby", "fasal bima", "kcc", "kisan credit card",
    "soil health card", "pkvy", "pmksy", "krishi sinchayee"
]

LOCATIONS_GAZETTEER = [
    "karnataka", "bengaluru", "bangalore", "mandya", "mysore", "mysuru",
    "dharwad", "belagavi", "shimoga", "shivamogga", "hassan", "kolar",
    "tumakuru", "tumkur", "chikkamagaluru", "kodagu", "coorg", "punjab",
    "haryana", "maharashtra", "madhya pradesh", "uttar pradesh", "rajasthan"
]

class AgriculturalNERService:
    """
    Named Entity Recognition for Agricultural Vocabulary.
    Extracts CROP, PEST_DISEASE, INPUT, SCHEME, and LOCATION entities.
    Filters overlapping duplicate entities by preserving the longest span.
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
        Eliminates overlapping duplicates, preserving the longest span.
        """
        raw_candidates: List[Tuple[int, int, str, str, float]] = []
        text_lower = text.lower()

        def collect_matches(gazetteer: List[str], label: str):
            for item in gazetteer:
                pattern = r"\b" + re.escape(item) + r"\b"
                for m in re.finditer(pattern, text_lower):
                    start, end = m.start(), m.end()
                    matched_text = text[start:end]
                    raw_candidates.append((start, end, matched_text, label, 0.95))

        collect_matches(CROPS_GAZETTEER, "CROP")
        collect_matches(PESTS_DISEASES_GAZETTEER, "PEST_DISEASE")
        collect_matches(INPUTS_GAZETTEER, "INPUT")
        collect_matches(SCHEMES_GAZETTEER, "SCHEME")
        collect_matches(LOCATIONS_GAZETTEER, "LOCATION")

        # 2. General NER extraction using Hugging Face if enabled locally
        try:
            self._load_hf_pipeline()
            if self._pipeline is not None:
                hf_res = self._pipeline(text)
                for item in hf_res:
                    word = item.get("word", "").strip()
                    entity_group = item.get("entity_group", "")
                    start = item.get("start", 0)
                    end = item.get("end", 0)
                    score = float(item.get("score", 0.8))
                    if entity_group in ["LOC", "GPE"]:
                        raw_candidates.append((start, end, word, "LOCATION", round(score, 2)))
        except Exception as e:
            logger.debug(f"HF NER extraction skipped: {e}")

        # 3. Disambiguate overlapping spans: Sort by length descending, keep longest
        # Candidate format: (start, end, text, label, score)
        raw_candidates.sort(key=lambda x: (x[1] - x[0]), reverse=True)

        accepted_spans: List[Tuple[int, int]] = []
        filtered_entities: List[EntityItem] = []

        for start, end, matched_text, label, score in raw_candidates:
            # Check if this candidate overlaps with any already-accepted span
            overlaps = any(max(start, s) < min(end, e) for s, e in accepted_spans)
            if not overlaps:
                accepted_spans.append((start, end))
                filtered_entities.append(EntityItem(
                    text=matched_text,
                    label=label,
                    confidence=score
                ))

        # Sort entities by their original position in text
        filtered_entities.sort(key=lambda item: text.find(item.text))
        return filtered_entities

ner_service = AgriculturalNERService()
