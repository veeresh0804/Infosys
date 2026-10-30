import re
import json
import logging
import hashlib
import datetime
import asyncio
from typing import List, Dict, Any, Tuple, Optional
import httpx
from sqlalchemy.future import select

from backend.app.config import settings
from backend.app.models.schemas import RetrievedChunk, LLMCacheModel
from backend.app.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Language names for LLM prompting
LANGUAGE_NAMES = {
    "hi": "Hindi (हिन्दी)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "en": "English"
}

# Mandatory pesticide safety standing line (Task 9)
PESTICIDE_SAFETY_LINE = (
    "Safety notice: Follow the product label, use only products registered for that crop, "
    "wear protective gear, respect the waiting period, and consult the local KVK or Kisan Call Centre."
)

# In-memory daily request tracking to monitor free tier quotas
DAILY_REQUEST_COUNTERS = {
    "date": datetime.date.today().isoformat(),
    "gemini": 0,
    "groq": 0
}

GEMINI_DAILY_LIMIT = 1500  # Google AI Studio free tier limit
GROQ_DAILY_LIMIT = 14400   # Groq free tier limit

def _check_and_increment_counter(provider: str) -> int:
    today = datetime.date.today().isoformat()
    if DAILY_REQUEST_COUNTERS["date"] != today:
        DAILY_REQUEST_COUNTERS["date"] = today
        DAILY_REQUEST_COUNTERS["gemini"] = 0
        DAILY_REQUEST_COUNTERS["groq"] = 0

    DAILY_REQUEST_COUNTERS[provider] += 1
    cnt = DAILY_REQUEST_COUNTERS[provider]

    if provider == "gemini" and cnt >= (GEMINI_DAILY_LIMIT * 0.85):
        logger.warning(f"⚠️ Gemini daily requests ({cnt}) approaching free-tier quota ({GEMINI_DAILY_LIMIT} RPD)!")
    elif provider == "groq" and cnt >= (GROQ_DAILY_LIMIT * 0.85):
        logger.warning(f"⚠️ Groq daily requests ({cnt}) approaching free-tier quota ({GROQ_DAILY_LIMIT} RPD)!")

    return cnt

def scrub_pii(text: str) -> str:
    """Strips personal identifiable information before sending prompts to free-tier LLM endpoints."""
    if not text:
        return text
    text = re.sub(r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b", "[PHONE_REDACTED]", text)
    text = re.sub(
        r"(?i)\b(my name is|i am|mera naam|nanna hesaru|naan)\s+([A-Z][a-z]+|[a-z]+)\b",
        r"\1 [FARMER]",
        text
    )
    return text

def split_sentence_boundary(text: str) -> str:
    """Splits at first sentence boundary, supporting both Latin '.' and Indic '।'"""
    parts = re.split(r'([.।\n])', text)
    if len(parts) >= 2:
        res = (parts[0] + parts[1]).strip()
        if len(res) > 15:
            return res[:220].strip()
    return text[:180].strip()

class RAGEngine:
    """
    Retrieval-Augmented Generation (RAG) synthesis engine with free-tier provider chain:
      1. Google Gemini free tier (AI Studio)
      2. Groq free tier (Llama-3.3-70b-versatile)
      3. Domain-grounded deterministic localized expert synthesis fallback
    """

    def __init__(self):
        self.gemini_model = settings.GEMINI_MODEL
        self.groq_model = settings.GROQ_MODEL
        logger.info(f"RAG Engine initialized: Gemini ({self.gemini_model}) -> Groq ({self.groq_model}) -> Domain Mock")

    def _cache_key(self, query: str, language: str) -> str:
        clean = f"{query.strip().lower()}:{language.strip().lower()}"
        return hashlib.sha256(clean.encode("utf-8")).hexdigest()

    async def get_cached_answer(self, query: str, language: str) -> Optional[Tuple[str, str, str, str, str]]:
        """Retrieves cached response from SQLite if less than 24 hours old."""
        try:
            key = self._cache_key(query, language)
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(LLMCacheModel).where(LLMCacheModel.cache_key == key))
                cached = result.scalars().first()
                if cached:
                    now = datetime.datetime.utcnow()
                    diff = now - (cached.created_at or now)
                    if diff.total_seconds() < 86400:
                        logger.info(f"🎯 Cache hit (SQLite 24h) for query in '{language}'. Cost: 0 API calls.")
                        # full_ans, short_ans, canonical_ans, short_canonical, provider
                        return (
                            cached.full_answer,
                            cached.short_answer or cached.full_answer,
                            cached.full_answer,
                            cached.short_answer or cached.full_answer,
                            f"{cached.provider}_cached"
                        )
        except Exception as e:
            logger.debug(f"Cache lookup bypassed: {e}")
        return None

    async def set_cached_answer(
        self,
        query: str,
        language: str,
        full_answer: str,
        short_answer: str,
        provider: str
    ):
        """Persists response to SQLite cache for 24 hours."""
        try:
            key = self._cache_key(query, language)
            async with AsyncSessionLocal() as db:
                existing = await db.execute(select(LLMCacheModel).where(LLMCacheModel.cache_key == key))
                obj = existing.scalars().first()
                if obj:
                    obj.full_answer = full_answer
                    obj.short_answer = short_answer
                    obj.provider = provider
                    obj.created_at = datetime.datetime.utcnow()
                else:
                    new_item = LLMCacheModel(
                        cache_key=key,
                        query=query,
                        language=language,
                        full_answer=full_answer,
                        short_answer=short_answer,
                        provider=provider,
                        created_at=datetime.datetime.utcnow()
                    )
                    db.add(new_item)
                await db.commit()
        except Exception as e:
            logger.debug(f"Failed to persist cache: {e}")

    async def generate_response(
        self,
        query: str,
        retrieved_chunks: List[RetrievedChunk],
        farmer_profile: Dict[str, Any],
        target_language: str = "en"
    ) -> Tuple[str, str, str, str, str]:
        """
        Synthesizes grounded agricultural answer.
        Returns: (answer_translated, short_answer_translated, answer_canonical, short_answer_canonical, engine_used)
        """
        # 1. Check 24-hour cache first
        cached = await self.get_cached_answer(query, target_language)
        if cached:
            return cached

        # 2. Format context and assemble honest profile (Task 6: never invent profile facts)
        if retrieved_chunks:
            context_text = "\n\n".join([
                f"[Source: {c.source} | Score: {c.similarity_score}]\n{c.content}"
                for c in retrieved_chunks
            ])
        else:
            context_text = "No direct knowledge base chunk retrieved."

        safe_query = scrub_pii(query)

        # Assemble profile honestly
        state = farmer_profile.get("state")
        district = farmer_profile.get("district")
        landholding = farmer_profile.get("landholding_acres")
        crops_list = farmer_profile.get("crops_grown", [])
        crops = ", ".join(crops_list) if crops_list else None

        loc_str = f"{district}, {state}" if (district and state) else (state or "Unknown / Not specified")
        land_str = f"{landholding} acres" if landholding else "Not specified"
        crops_str = crops if crops else "Not specified"

        lang_label = LANGUAGE_NAMES.get(target_language, "English")

        # Standing pesticide safety notice instruction (Task 9)
        system_instruction = (
            f"You are an expert Indian Agricultural Extension Specialist advising smallholder farmers. "
            f"Ground your answer strictly in the provided verified agricultural context. "
            f"You MUST provide your response directly and fluently in {lang_label}.\n"
            f"Always include this mandatory safety advisory when recommending chemical controls:\n"
            f"'{PESTICIDE_SAFETY_LINE}'\n"
            f"If a farmer profile field is Unknown or Not specified, do not assume or invent facts.\n"
            f"Output your final response strictly as valid JSON with four fields:\n"
            f'{{\n'
            f' "answer_translated": "Complete, detailed advisory directly in {lang_label}",\n'
            f' "short_answer_translated": "1-2 short, crystal-clear sentences suitable for speech playback in {lang_label}",\n'
            f' "answer_canonical": "Complete equivalent advisory in English",\n'
            f' "short_answer_canonical": "1-2 short sentences in English"\n'
            f'}}'
        )

        user_content = (
            f"Verified Agricultural Context:\n{context_text}\n\n"
            f"Farmer Location: {loc_str} | Land: {land_str} | Crops: {crops_str}\n\n"
            f"Farmer Question: {safe_query}"
        )

        # 3. Try Gemini Free Tier
        if settings.GOOGLE_API_KEY and settings.GOOGLE_API_KEY.strip() and not settings.GOOGLE_API_KEY.startswith("your_"):
            ans_tr, short_tr, ans_en, short_en, engine = await self._call_gemini(system_instruction, user_content, target_language)
            if ans_tr:
                _check_and_increment_counter("gemini")
                await self.set_cached_answer(query, target_language, ans_tr, short_tr, engine)
                return ans_tr, short_tr, ans_en, short_en, engine

        # 4. Try Groq Free Tier
        if settings.GROQ_API_KEY and settings.GROQ_API_KEY.strip() and not settings.GROQ_API_KEY.startswith("your_"):
            ans_tr, short_tr, ans_en, short_en, engine = await self._call_groq(system_instruction, user_content, target_language)
            if ans_tr:
                _check_and_increment_counter("groq")
                await self.set_cached_answer(query, target_language, ans_tr, short_tr, engine)
                return ans_tr, short_tr, ans_en, short_en, engine

        # 5. Localized Domain Mock Fallback (Task 4: genuine localized messages, never English with Hindi tag)
        logger.info("[MOCK] LLM providers unavailable or unconfigured. Using domain-grounded synthesis fallback.")
        ans_tr, short_tr, ans_en, short_en = self._synthesize_grounded_answer(query, retrieved_chunks, target_language)
        return ans_tr, short_tr, ans_en, short_en, "domain_grounded_mock_engine"

    async def _call_gemini(
        self,
        system_instruction: str,
        user_content: str,
        target_language: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={settings.GOOGLE_API_KEY}"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"{system_instruction}\n\n{user_content}"}]}
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1024,
                "responseMimeType": "application/json"
            }
        }

        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            ans_tr, short_tr, ans_en, short_en = self._parse_llm_json(raw_text, target_language)
                            return ans_tr, short_tr, ans_en, short_en, f"google_gemini_{self.gemini_model}"
                    elif resp.status_code in [429, 500, 503]:
                        logger.warning(f"Gemini API returned status {resp.status_code}. Backing off {1 + attempt * 2}s...")
                        await asyncio.sleep(1 + attempt * 2)
                    else:
                        logger.error(f"Gemini error {resp.status_code}: {resp.text[:200]}")
                        break
            except Exception as e:
                logger.warning(f"Gemini call exception on attempt {attempt}: {e}")
                await asyncio.sleep(1)

        return None, None, None, None, None

    async def _call_groq(
        self,
        system_instruction: str,
        user_content: str,
        target_language: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.groq_model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.2,
            "max_tokens": 1024,
            "response_format": {"type": "json_object"}
        }

        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            raw_text = choices[0].get("message", {}).get("content", "")
                            ans_tr, short_tr, ans_en, short_en = self._parse_llm_json(raw_text, target_language)
                            return ans_tr, short_tr, ans_en, short_en, f"groq_{self.groq_model}"
                    elif resp.status_code in [429, 500, 503]:
                        logger.warning(f"Groq API returned {resp.status_code}. Backoff {1 + attempt * 2}s...")
                        await asyncio.sleep(1 + attempt * 2)
                    else:
                        logger.error(f"Groq error {resp.status_code}: {resp.text[:200]}")
                        break
            except Exception as e:
                logger.warning(f"Groq call exception on attempt {attempt}: {e}")
                await asyncio.sleep(1)

        return None, None, None, None, None

    def _parse_intent_json(self, raw_text: str) -> Optional[Tuple[str, float]]:
        """Parses {"intent": ..., "confidence": ...} and validates against the agri intent list."""
        try:
            data = json.loads(raw_text)
            intent = (data.get("intent") or "").strip()
            if intent not in ("crop_advisory", "pest_control", "market_prices", "weather", "scheme_lookup"):
                return None
            confidence = float(data.get("confidence", 0.6))
            confidence = round(min(0.85, max(0.40, confidence)), 2)
            return intent, confidence
        except Exception:
            return None

    async def classify_intent_llm(self, canonical_text: str) -> Optional[Tuple[str, float, str]]:
        """
        Free-LLM intent fallback for ambiguous farmer queries (docs/FREE_TIER_DEVIATIONS.md §5):
        rule classifier first; this chain (Gemini -> Groq) disambiguates the uncertain remainder.
        Returns (intent, confidence, engine_used) or None so the caller keeps the honest rule result.
        """
        prompt = (
            "Classify this Indian farmer query into exactly ONE agricultural intent from this list: "
            "crop_advisory, pest_control, market_prices, weather, scheme_lookup.\n\n"
            f"Farmer query: {scrub_pii(canonical_text)}\n\n"
            'Output ONLY valid JSON: {"intent": "<one intent from the list>", "confidence": <0.0-1.0>}'
        )

        # 1. Try Gemini free tier
        if settings.GOOGLE_API_KEY and not settings.GOOGLE_API_KEY.startswith("your_"):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={settings.GOOGLE_API_KEY}"
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.0, "maxOutputTokens": 96, "responseMimeType": "application/json"}
                }
                async with httpx.AsyncClient(timeout=12.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        _check_and_increment_counter("gemini")
                        parts = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])
                        parsed = self._parse_intent_json(parts[0].get("text", ""))
                        if parsed:
                            intent, confidence = parsed
                            return intent, confidence, f"gemini_{self.gemini_model}_intent_router"
            except Exception as e:
                logger.debug(f"Gemini intent classification failed: {e}")

        # 2. Try Groq free tier
        if settings.GROQ_API_KEY and not settings.GROQ_API_KEY.startswith("your_"):
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": self.groq_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "max_tokens": 96,
                    "response_format": {"type": "json_object"}
                }
                async with httpx.AsyncClient(timeout=12.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        _check_and_increment_counter("groq")
                        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                        parsed = self._parse_intent_json(content)
                        if parsed:
                            intent, confidence = parsed
                            return intent, confidence, f"groq_{self.groq_model}_intent_router"
            except Exception as e:
                logger.debug(f"Groq intent classification failed: {e}")

        # Honest failure: caller falls back to the rule decision (no fabricated confidence)
        return None

    def _parse_llm_json(self, raw_text: str, target_language: str) -> Tuple[str, str, str, str]:
        """Parses answer_translated, short_answer_translated, answer_canonical, short_answer_canonical."""
        try:
            data = json.loads(raw_text)
            ans_tr = data.get("answer_translated") or data.get("full_answer") or data.get("answer") or raw_text
            short_tr = data.get("short_answer_translated") or data.get("short_answer") or split_sentence_boundary(ans_tr)
            ans_en = data.get("answer_canonical") or (ans_tr if target_language == "en" else data.get("full_answer") or ans_tr)
            short_en = data.get("short_answer_canonical") or split_sentence_boundary(ans_en)
            return ans_tr.strip(), short_tr.strip(), ans_en.strip(), short_en.strip()
        except Exception:
            short_ans = split_sentence_boundary(raw_text)
            return raw_text.strip(), short_ans, raw_text.strip(), short_ans

    def _synthesize_grounded_answer(
        self,
        query: str,
        retrieved_chunks: List[RetrievedChunk],
        target_language: str
    ) -> Tuple[str, str, str, str]:
        """
        Deterministic, genuinely localized fallback synthesizer from knowledge chunks (Task 4).
        Never returns English text with a Hindi label.
        """
        top_content = retrieved_chunks[0].content if retrieved_chunks else "Consult local KVK for verified package of practices."
        top_source = retrieved_chunks[0].source if retrieved_chunks else "ICAR Package of Practices"

        # English canonical answer (always English)
        full_en = (
            f"Advisory Source: {top_source}\n\n"
            f"{top_content}\n\n"
            f"{PESTICIDE_SAFETY_LINE}"
        )
        short_en = split_sentence_boundary(top_content)

        if target_language == "hi":
            full_tr = (
                f"कृषि परामर्श (स्रोत: {top_source}):\n\n"
                f"{top_content}\n\n"
                f"सुरक्षा सूचना: उत्पाद लेबल का पालन करें, केवल पंजीकृत दवाओं का उपयोग करें, सुरक्षा उपकरण पहनें और निकटतम केवीके (KVK) से सलाह लें।"
            )
            short_tr = "फसल सलाह: अनुशंसित कृषि पैकेज का पालन करें और दवा छिड़काव से पहले लेबल अवश्य पढ़ें।"
            return full_tr, short_tr, full_en, short_en

        elif target_language == "kn":
            full_tr = (
                f"ಕೃಷಿ ಸಲಹೆ (ಮೂಲ: {top_source}):\n\n"
                f"{top_content}\n\n"
                f"ಸುರಕ್ಷತಾ ಸೂಚನೆ: ಉತ್ಪನ್ನದ ಲೇಬಲ್ ಸೂಚನೆ ಪಾಲಿಸಿ, ಕಾಯುವ ಅವಧಿ ಗೌರವಿಸಿ ಮತ್ತು ಸ್ಥಳೀಯ ಕೆವಿಕೆ (KVK) ಸಂಪರ್ಕಿಸಿ."
            )
            short_tr = "ಬೆಳೆ ಸಲಹೆ: ಶಿಫಾರಸು ಮಾಡಿದ ಕೃಷಿ ಪದ್ಧತಿಯನ್ನು ಅನುಸರಿಸಿ ಮತ್ತು ಔಷಧ ಬಳಸುವ ಮುನ್ನ ಲೇಬಲ್ ಓದಿ."
            return full_tr, short_tr, full_en, short_en

        return full_en, short_en, full_en, short_en

    async def translate_text(self, text: str, source_language: str, target_language: str) -> Tuple[Optional[str], str]:
        """Translates text between Indic languages and English using free LLM chain."""
        if source_language == target_language or not text.strip():
            return text, "passthrough"

        prompt = (
            f"Translate the following Indian agricultural text accurately from {source_language} to {target_language}. "
            f"Preserve technical agricultural terms, crop names, and chemical names accurately. "
            f"Output ONLY the translated text without commentary or quotes:\n\n{text}"
        )

        # 1. Try Gemini
        if settings.GOOGLE_API_KEY and not settings.GOOGLE_API_KEY.startswith("your_"):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={settings.GOOGLE_API_KEY}"
                payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        parts = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])
                        trans = parts[0].get("text", "").strip()
                        if trans:
                            return trans, f"gemini_{self.gemini_model}_translation"
            except Exception as e:
                logger.debug(f"Gemini translation failed: {e}")

        # 2. Try Groq
        if settings.GROQ_API_KEY and not settings.GROQ_API_KEY.startswith("your_"):
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
                payload = {
                    "model": self.groq_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 512
                }
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        trans = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                        if trans:
                            return trans, f"groq_{self.groq_model}_translation"
            except Exception as e:
                logger.debug(f"Groq translation failed: {e}")

        # Return None on failure (Task 4: no fake [en] tags)
        return None, "translation_failed"

rag_engine = RAGEngine()
