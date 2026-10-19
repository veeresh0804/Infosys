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
async def health_check():
    return {"status": "healthy"}

@app.get("/")
async def root_status():
    return {
        "status": "online",
        "service": "AI-Driven Smart Farming Assistant Backend",
        "milestones": ["Milestone 1: NLP & Multilingual Processing", "Milestone 2: Agricultural Knowledge Base & RAG Integration"],
        "active_configuration": {
            "vector_db": settings.VECTOR_DB_TYPE,
            "llm_provider": settings.LLM_PROVIDER,
            "weather_provider": settings.WEATHER_PROVIDER,
            "sarvam_stt_tts": "Configured" if settings.SARVAM_API_KEY else "Mock Mode (Ready for key)",
            "openai_fallback": "Configured" if settings.OPENAI_API_KEY else "Mock Mode (Ready for key)",
            "gemini_api": "Configured" if settings.GOOGLE_API_KEY else "Mock Mode (Ready for key)"
        },
        "docs_url": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.BACKEND_HOST, port=settings.BACKEND_PORT, reload=True)
