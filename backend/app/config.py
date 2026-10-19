import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Server settings
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Milestone 1: Speech & Translation (Sarvam AI + Groq Whisper Fallback)
    SARVAM_ENABLED: bool = Field(default=True, description="Enable Sarvam AI API for Indic STT/TTS; set false to save credits")
    SARVAM_API_KEY: str = Field(default="", description="Sarvam AI API key for Indic STT/TTS/Translation")
    SARVAM_API_URL: str = "https://api.sarvam.ai"
    OPENAI_API_KEY: str = Field(default="", description="Optional OpenAI key (deprecated in favor of free Groq Whisper)")

    # Milestone 1: Hugging Face Models
    ENABLE_HF_LOCAL: bool = Field(default=False, description="Set True for heavy local HF models; False fits in 512MB RAM using rule+LLM fallback")
    HF_TOKEN: str = Field(default="", description="Hugging Face API token (optional)")
    HF_INTENT_MODEL: str = "facebook/bart-large-mnli"
    HF_NER_MODEL: str = "dslim/bert-base-NER"

    # Milestone 2: Vector DB (Default to local store for 100% free operation)
    VECTOR_DB_TYPE: str = Field(default="local", description="'local', 'chromadb', or 'pinecone'")
    PINECONE_API_KEY: str = Field(default="", description="Optional Pinecone API Key")
    PINECONE_INDEX_NAME: str = "agri-assistant"
    PINECONE_CLOUD: str = "aws"
    PINECONE_REGION: str = "us-east-1"
    CHROMA_PERSIST_DIRECTORY: str = "./data/chroma_db"
    CHROMA_COLLECTION_NAME: str = "agri_knowledge_base"

    # Milestone 2: Embeddings & LLM
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    LLM_PROVIDER: str = Field(default="chain", description="'chain' (Gemini->Groq->Mock), 'gemini', 'groq', or 'mock'")
    GOOGLE_API_KEY: str = Field(default="", description="Google Gemini API key for free-tier RAG (from Google AI Studio)")
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GROQ_API_KEY: str = Field(default="", description="Groq API key for free-tier RAG & Whisper (from Groq Console)")
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_WHISPER_MODEL: str = "whisper-large-v3-turbo"

    # Milestone 2: Live Data APIs
    DATA_GOV_IN_API_KEY: str = Field(default="", description="data.gov.in API Key for AGMARKNET")
    AGMARKNET_RESOURCE_ID: str = "9ef84268-d588-465a-a308-a864a43d0070"
    WEATHER_PROVIDER: str = Field(default="open-meteo", description="'open-meteo' or 'mock'")
    SCHEME_CHECKER_MODE: str = Field(default="rules", description="'rules' or 'mock'")

    # Quality & Storage
    QUALITY_CONFIDENCE_THRESHOLD: float = 0.70
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/sessions.db"

    # Security & Admin
    ADMIN_API_KEY: str = Field(default="dev-admin-token", description="Admin secret token for privileged endpoints")

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]

settings = Settings()
