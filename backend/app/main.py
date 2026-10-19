import sys, os
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.config import settings
from backend.app.database import init_db
from backend.app.routers import speech, nlp, rag, live_data, sessions, ingestion

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("agri-assistant")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Smart Farming Assistant backend...")
    await init_db()
    logger.info("Database initialized successfully.")
    yield
    logger.info("Shutting down backend...")

app = FastAPI(
    title="AI-Driven Smart Farming Assistant API",
    description="Multilingual Agricultural Guidance Platform implementing Milestone 1 & Milestone 2 (Speech, Translation, Intent/NER, LangChain RAG, Live Mandi/Weather/Schemes, Session State)",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(speech.router)
app.include_router(nlp.router)
app.include_router(rag.router)
app.include_router(live_data.router)
app.include_router(sessions.router)
app.include_router(ingestion.router)

@app.get("/health")
@app.get("/api/health")
async def health_check():
    import os
    from backend.app.services.rag.embeddings import embedding_service
    from backend.app.services.rag.vector_store import get_vector_store
    from backend.app.services.nlp.sarvam_service import sarvam_service

    mem_mb = 0.0
    try:
        import psutil
        mem_mb = round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 2)
    except Exception:
        pass

    vstore = get_vector_store()
    chunk_count = vstore.count()

    active_engines = {
        "llm_primary": f"google_gemini_{settings.GEMINI_MODEL}" if (settings.GOOGLE_API_KEY and not settings.GOOGLE_API_KEY.startswith("your_")) else "unconfigured",
        "llm_secondary": f"groq_{settings.GROQ_MODEL}" if (settings.GROQ_API_KEY and not settings.GROQ_API_KEY.startswith("your_")) else "unconfigured",
        "llm_fallback": "domain_grounded_mock_engine",
        "stt_primary": "sarvam_saaras" if (settings.SARVAM_ENABLED and sarvam_service.is_configured) else ("circuit_broken" if sarvam_service.circuit_broken else "disabled"),
        "stt_secondary": f"groq_whisper_{settings.GROQ_WHISPER_MODEL}" if (settings.GROQ_API_KEY and not settings.GROQ_API_KEY.startswith("your_")) else "mock_whisper_fallback",
        "tts_primary": "sarvam_bulbul" if (settings.SARVAM_ENABLED and sarvam_service.is_configured) else "fallback_browser_speech",
        "translation": "sarvam_mayura" if (settings.SARVAM_ENABLED and sarvam_service.is_configured) else "free_llm_chain",
        "embeddings": embedding_service.engine_used,
        "vector_store": f"{settings.VECTOR_DB_TYPE} ({chunk_count} chunks indexed)",
        "weather": settings.WEATHER_PROVIDER,
        "mandi": "data.gov.in AGMARKNET" if settings.DATA_GOV_IN_API_KEY else "sample_apmc_mock",
        "schemes": "rule_based_engine"
    }

    return {
        "status": "healthy",
        "free_tier_mode": True,
        "memory_rss_mb": mem_mb,
        "memory_fit_512mb": mem_mb < 512.0,
        "active_engines": active_engines
    }

@app.get("/")
async def root_status():
    health = await health_check()
    return {
        "status": "online",
        "service": "AI-Driven Smart Farming Assistant Backend (Free Tiers Edition)",
        "milestones": [
            "Milestone 1: NLP & Multilingual Processing (Free Tier & Client Voice)",
            "Milestone 2: Agricultural Knowledge Base & RAG Integration (FastEmbed ONNX & Gemini/Groq)"
        ],
        "active_configuration": health["active_engines"],
        "memory_rss_mb": health["memory_rss_mb"],
        "docs_url": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.BACKEND_HOST, port=settings.BACKEND_PORT, reload=True)
