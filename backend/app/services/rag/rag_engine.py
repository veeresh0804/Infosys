import os
import re
import json
import logging
import hashlib
import asyncio
import datetime
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
    """
    Strips personal identifiable information (phone numbers, full names) before
    sending prompts to public/free-tier LLM endpoints.
    """
    if not text:
        return text
    # Strip Indian phone numbers (10 digits with optional +91 or leading 0)
    text = re.sub(r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b", "[PHONE_REDACTED]", text)
    # Strip name introductions (e.g. "my name is Ramesh", "mera naam Suresh")
    text = re.sub(
        r"(?i)\b(my name is|i am|mera naam|nanna hesaru|naan)\s+([A-Z][a-z]+|[a-z]+)\b",
        r"\1 [FARMER]",
        text
    )
    return text

class RAGEngine:
    """
    Retrieval-Augmented Generation (RAG) synthesis engine using an ordered free-tier provider chain:
      1. Google Gemini free tier (AI Studio)
      2. Groq free tier (Llama-3.3-70b-versatile)
      3. Domain-grounded deterministic expert synthesis fallback

    Features:
      - 24-hour SQLite query caching (repeated demo questions cost 0 calls)
      - Direct fluent generation in farmer's language (Hindi / Kannada / English)
      - PII scrubbing
      - Automatic retry with exponential backoff on 429/quota/5xx errors
      - Daily quota tracking and alerting
    """

    def __init__(self):
        self.gemini_model = settings.GEMINI_MODEL
        self.groq_model = settings.GROQ_MODEL
        logger.info(f"RAG Engine initialized with chain: Gemini ({self.gemini_model}) -> Groq ({self.groq_model}) -> Domain Mock")

    def _cache_key(self, query: str, language: str) -> str:
        clean = f"{query.strip().lower()}:{language.strip().lower()}"
        return hashlib.sha256(clean.encode("utf-8")).hexdigest()

    async def get_cached_answer(self, query: str, language: str) -> Optional[Tuple[str, str, str]]:
        """
        Retrieves cached response from SQLite if less than 24 hours old.
        Returns: (full_answer, short_answer, provider) or None
        """
        try:
            key = self._cache_key(query, language)
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(LLMCacheModel).where(LLMCacheModel.cache_key == key))
                cached = result.scalars().first()
                if cached:
                    now = datetime.datetime.utcnow()
                    diff = now - (cached.created_at or now)
                    if diff.total_seconds() < 86400:  # 24 hours
                        logger.info(f"🎯 Cache hit (SQLite 24h) for query in '{language}'. Cost: 0 API calls.")
                        return cached.full_answer, cached.short_answer or cached.full_answer, f"{cached.provider}_cached"
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
        """
        Persists response to SQLite cache for 24 hours.
        """
        try:
            key = self._cache_key(query, language)
            async with AsyncSessionLocal() as db:
                # Remove any existing entry
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
    ) -> Tuple[str, str, str]:
        """
        Synthesizes grounded agricultural answer directly in target_language.
        Returns: (full_answer, short_answer, engine_used)
        """
        # 1. Check 24-hour cache first
        cached = await self.get_cached_answer(query, target_language)
        if cached:
            return cached

        # 2. Format context and scrub PII
        if retrieved_chunks:
            context_text = "\n\n".join([
                f"[Source: {c.source} | Score: {c.similarity_score}]\n{c.content}"
                for c in retrieved_chunks
            ])
        else:
            context_text = "No direct knowledge base chunk retrieved."

        safe_query = scrub_pii(query)
        state = farmer_profile.get("state", "Karnataka")
        district = farmer_profile.get("district", "Bengaluru Rural")
        landholding = farmer_profile.get("landholding_acres", 2.0)
        crops = ", ".join(farmer_profile.get("crops_grown", ["Tomato", "Paddy"]))
        lang_label = LANGUAGE_NAMES.get(target_language, "English")

        system_instruction = (
            f"You are an expert Indian Agricultural Extension Specialist advising smallholder farmers. "
            f"Ground your answer strictly in the provided verified agricultural context. "
            f"You MUST respond directly and fluently in {lang_label}. "
            f"Never tell the farmer to just 'read more'; give practical dosages, pesticide names, or fertilizer schedules if in context. "
            f"Output your final response strictly as valid JSON with two fields:\n"
            f'{{"short_answer": "1-2 short, crystal-clear sentences suitable for voice speech playback in {lang_label}",\n'
            f' "full_answer": "complete, detailed advisory in {lang_label}"}}'
        )

        user_content = (
            f"Verified Agricultural Context:\n{context_text}\n\n"
            f"Farmer Location: {district}, {state} | Land: {landholding} acres | Crops: {crops}\n\n"
            f"Farmer Question: {safe_query}"
        )

        # 3. Try Gemini Free Tier
        if settings.GOOGLE_API_KEY and settings.GOOGLE_API_KEY.strip() and not settings.GOOGLE_API_KEY.startswith("your_"):
            ans, short_ans, engine = await self._call_gemini(system_instruction, user_content)
            if ans:
                _check_and_increment_counter("gemini")
                await self.set_cached_answer(query, target_language, ans, short_ans, engine)
                return ans, short_ans, engine

        # 4. Try Groq Free Tier
        if settings.GROQ_API_KEY and settings.GROQ_API_KEY.strip() and not settings.GROQ_API_KEY.startswith("your_"):
            ans, short_ans, engine = await self._call_groq(system_instruction, user_content)
            if ans:
                _check_and_increment_counter("groq")
                await self.set_cached_answer(query, target_language, ans, short_ans, engine)
                return ans, short_ans, engine

        # 5. Domain Mock Fallback
        logger.info("[MOCK] LLM providers unavailable or unconfigured. Using domain-grounded synthesis fallback.")
        full_ans, short_ans = self._synthesize_grounded_answer(query, retrieved_chunks, target_language)
        return full_ans, short_ans, "domain_grounded_mock_engine"

    async def _call_gemini(self, system_instruction: str, user_content: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Invokes Google Gemini free tier via REST API with backoff retry."""
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
                            full_ans, short_ans = self._parse_llm_json(raw_text)
                            return full_ans, short_ans, f"google_gemini_{self.gemini_model}"
                    elif resp.status_code in [429, 500, 503]:
                        logger.warning(f"Gemini API returned status {resp.status_code}. Backing off {1 + attempt * 2}s...")
                        await asyncio.sleep(1 + attempt * 2)
                    else:
                        logger.error(f"Gemini error {resp.status_code}: {resp.text[:200]}")
                        break
            except Exception as e:
                logger.warning(f"Gemini call exception on attempt {attempt}: {e}")
                await asyncio.sleep(1)

        return None, None, None

    async def _call_groq(self, system_instruction: str, user_content: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Invokes Groq free tier (Llama-3.3-70b-versatile) via OpenAI-compatible endpoint."""
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
                            full_ans, short_ans = self._parse_llm_json(raw_text)
                            return full_ans, short_ans, f"groq_{self.groq_model}"
                    elif resp.status_code in [429, 500, 503]:
                        logger.warning(f"Groq API returned {resp.status_code}. Backoff {1 + attempt * 2}s...")
                        await asyncio.sleep(1 + attempt * 2)
                    else:
                        logger.error(f"Groq error {resp.status_code}: {resp.text[:200]}")
                        break
            except Exception as e:
                logger.warning(f"Groq call exception on attempt {attempt}: {e}")
                await asyncio.sleep(1)

        return None, None, None

    def _parse_llm_json(self, raw_text: str) -> Tuple[str, str]:
        """Parses {short_answer, full_answer} from LLM JSON output."""
        try:
            data = json.loads(raw_text)
            full_ans = data.get("full_answer") or data.get("answer") or raw_text
            short_ans = data.get("short_answer") or (full_ans.split(".")[0] + ".")
            return full_ans.strip(), short_ans.strip()
        except Exception:
            lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
            short_ans = lines[0] if lines else raw_text[:140]
            return raw_text.strip(), short_ans

    def _synthesize_grounded_answer(
        self,
        query: str,
        retrieved_chunks: List[RetrievedChunk],
        target_language: str
    ) -> Tuple[str, str]:
        """Deterministic fallback synthesizer from knowledge chunks."""
        if not retrieved_chunks:
            msg = (
                "Based on available agricultural advisories, please consult your nearest Krishi Vigyan Kendra (KVK) "
                "or Kisan Call Centre (Toll-Free 1800-180-1551) for immediate specialized guidance."
            )
            return msg, msg

        top = retrieved_chunks[0]
        full_lines = [
            f"Advisory Source: {top.source}",
            top.content
        ]
        if len(retrieved_chunks) > 1:
            full_lines.append(f"\nAdditional Advisory ({retrieved_chunks[1].source}):\n{retrieved_chunks[1].content[:250]}...")

        full_ans = "\n\n".join(full_lines)
        short_ans = top.content.split("\n")[0]
        if len(short_ans) > 180:
            short_ans = short_ans[:180] + "..."

        if target_language == "hi":
            full_ans = f"[हिन्दी परामर्श] {full_ans}"
            short_ans = f"[हिन्दी सारांश] {short_ans}"
        elif target_language == "kn":
            full_ans = f"[ಕನ್ನಡ ಸಲಹೆ] {full_ans}"
            short_ans = f"[ಕನ್ನಡ ಸಾರಾಂಶ] {short_ans}"

        return full_ans, short_ans

    async def translate_text(self, text: str, source_language: str, target_language: str) -> Tuple[str, str]:
        """
        Translates text between Indic languages and English using the free LLM chain.
        Invoked when Sarvam credits are exhausted or disabled.
        """
        if source_language == target_language or not text.strip():
            return text, "passthrough"

        prompt = (
            f"Translate the following Indian agricultural text accurately from {source_language} to {target_language}. "
            f"Preserve technical agricultural terms, crop names, and chemical names accurately. "
            f"Output ONLY the translated text without commentary or quotes:\n\n{text}"
        )

        # 1. Try Gemini
        if settings.GOOGLE_API_KEY:
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
        if settings.GROQ_API_KEY:
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

        return f"[{target_language}] {text}", "mock_llm_translation_fallback"

rag_engine = RAGEngine()
