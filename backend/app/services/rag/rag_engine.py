import logging
from typing import List, Dict, Any, Tuple
from backend.app.config import settings
from backend.app.models.schemas import RetrievedChunk

logger = logging.getLogger(__name__)

RAG_PROMPT_TEMPLATE = """You are an expert Indian Agricultural Extension Specialist advising smallholder farmers.
Ground your response strictly in the verified agricultural knowledge base chunks provided below.
Provide clear, actionable, and practical guidance. Mention specific chemical/organic names and recommended dosages if given in the context.

Context from Verified Knowledge Base:
{context}

Farmer Context:
State: {state} | District: {district} | Landholding: {landholding} acres | Crops: {crops}

Farmer Question:
{question}

Advisory Response (concise, clear, farmer-friendly):"""

class RAGEngine:
    """
    Retrieval-Augmented Generation (RAG) synthesis engine using LangChain.
    Configurable to use Google Gemini (free tier), Groq (free tier), OpenAI, or domain mock.
    """

    def __init__(self):
        self.provider = settings.LLM_PROVIDER.lower()
        self._llm = None
        self._init_llm()

    def _init_llm(self):
        try:
            if self.provider == "gemini" and settings.GOOGLE_API_KEY:
                from langchain_google_genai import ChatGoogleGenerativeAI
                self._llm = ChatGoogleGenerativeAI(
                    model=settings.GEMINI_MODEL,
                    google_api_key=settings.GOOGLE_API_KEY,
                    temperature=0.2
                )
                logger.info(f"Initialized Gemini LLM ({settings.GEMINI_MODEL})")
            elif self.provider == "groq" and settings.GROQ_API_KEY:
                from langchain_groq import ChatGroq
                self._llm = ChatGroq(
                    model=settings.GROQ_MODEL,
                    groq_api_key=settings.GROQ_API_KEY,
                    temperature=0.2
                )
                logger.info(f"Initialized Groq LLM ({settings.GROQ_MODEL})")
            elif self.provider == "openai" and settings.OPENAI_API_KEY:
                from langchain_openai import ChatOpenAI
                self._llm = ChatOpenAI(
                    model="gpt-4o-mini",
                    api_key=settings.OPENAI_API_KEY,
                    temperature=0.2
                )
                logger.info("Initialized OpenAI LLM (gpt-4o-mini)")
            else:
                logger.info(f"[MOCK/LOCAL] No paid LLM API key configured for '{self.provider}'. Using grounded domain synthesis engine.")
                self._llm = None
        except Exception as e:
            logger.warning(f"Error initializing LLM provider '{self.provider}': {e}. Using domain mock generator.")
            self._llm = None

    async def generate_response(
        self,
        query: str,
        retrieved_chunks: List[RetrievedChunk],
        farmer_profile: Dict[str, Any]
    ) -> Tuple[str, str]:
        """
        Synthesizes grounded agricultural answer from retrieved chunks.
        Returns: (answer_canonical, llm_engine_used)
        """
        # Format context
        if retrieved_chunks:
            context_text = "\n\n".join([
                f"[Source: {c.source} | Similarity: {c.similarity_score}]\n{c.content}"
                for c in retrieved_chunks
            ])
        else:
            context_text = "No direct knowledge base chunk retrieved."

        state = farmer_profile.get("state", "Karnataka")
        district = farmer_profile.get("district", "Bengaluru Rural")
        landholding = farmer_profile.get("landholding_acres", 2.0)
        crops = ", ".join(farmer_profile.get("crops_grown", ["Tomato", "Paddy"]))

        formatted_prompt = RAG_PROMPT_TEMPLATE.format(
            context=context_text,
            state=state,
            district=district,
            landholding=landholding,
            crops=crops,
            question=query
        )

        # 1. If LLM is initialized, invoke via LangChain
        if self._llm is not None:
            try:
                from langchain_core.messages import HumanMessage
                response = await self._llm.ainvoke([HumanMessage(content=formatted_prompt)])
                return response.content.strip(), f"langchain_{self.provider}"
            except Exception as e:
                logger.error(f"Error generating answer with LangChain LLM ({self.provider}): {e}")

        # 2. Domain-grounded expert synthesis fallback
        logger.info("[MOCK] Synthesizing grounded response using verified agricultural knowledge chunks.")
        return self._synthesize_grounded_answer(query, retrieved_chunks), "domain_grounded_synthesis_engine"

    def _synthesize_grounded_answer(self, query: str, retrieved_chunks: List[RetrievedChunk]) -> str:
        """
        Synthesizes a high quality, coherent advisory response directly from retrieved chunks.
        """
        if not retrieved_chunks:
            return (
                "Based on available agricultural advisories, please consult your nearest Krishi Vigyan Kendra (KVK) "
                "or Kisan Call Centre (Toll-Free 1800-180-1551) for immediate specialized guidance."
            )

        top_chunk = retrieved_chunks[0]
        summary_lines = [
            f"According to verified guidance ({top_chunk.source}):",
            top_chunk.content
        ]

        if len(retrieved_chunks) > 1:
            second = retrieved_chunks[1]
            summary_lines.append(f"Additional advisory ({second.source}): {second.content[:250]}...")

        return "\n\n".join(summary_lines)

rag_engine = RAGEngine()
