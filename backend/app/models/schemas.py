import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON
from backend.app.database import Base

# ==============================================================================
# SQLAlchemy ORM Models
# ==============================================================================

class SessionModel(Base):
    __tablename__ = "sessions"

    session_id = Column(String(64), primary_key=True, index=True)
    user_id = Column(String(64), nullable=True, default="default_farmer")
    preferred_language = Column(String(10), default="hi")  # "hi", "kn", "en"
    state = Column(String(64), nullable=True, default="Karnataka")
    district = Column(String(64), nullable=True, default="Bengaluru Rural")
    landholding_acres = Column(Float, nullable=True, default=2.5)
    crops_grown = Column(JSON, nullable=True, default=lambda: ["Tomato", "Paddy"])
    history = Column(JSON, nullable=True, default=list)  # list of {role, text, canonical_text, timestamp}
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class FlaggedReviewModel(Base):
    __tablename__ = "flagged_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), index=True)
    original_query = Column(Text, nullable=False)
    canonical_query = Column(Text, nullable=False)
    detected_language = Column(String(10), default="en")
    detected_intent = Column(String(64), nullable=False)
    response_text = Column(Text, nullable=False)
    confidence_score = Column(Float, nullable=False)
    sub_agent = Column(String(64), nullable=False)
    flag_reason = Column(String(255), nullable=False)
    retrieved_chunks = Column(JSON, nullable=True, default=list)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class LLMCacheModel(Base):
    __tablename__ = "llm_cache"

    cache_key = Column(String(128), primary_key=True, index=True)
    query = Column(Text, nullable=False)
    language = Column(String(10), default="en")
    full_answer = Column(Text, nullable=False)
    short_answer = Column(Text, nullable=True)
    provider = Column(String(32), default="cached")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class TTSCacheModel(Base):
    __tablename__ = "tts_cache"

    audio_hash = Column(String(128), primary_key=True, index=True)
    text = Column(Text, nullable=False)
    language = Column(String(10), default="hi")
    speaker = Column(String(32), default="kavya")
    audio_base64 = Column(Text, nullable=False)
    engine = Column(String(32), default="cached")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# ==============================================================================
# Pydantic Schemas
# ==============================================================================

# Session & User Profile Schemas
class SessionUpdate(BaseModel):
    user_id: Optional[str] = None
    preferred_language: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    landholding_acres: Optional[float] = None
    crops_grown: Optional[List[str]] = None

class SessionResponse(BaseModel):
    session_id: str
    user_id: Optional[str]
    preferred_language: str
    state: Optional[str]
    district: Optional[str]
    landholding_acres: Optional[float]
    crops_grown: List[str]
    history: List[Dict[str, Any]]
    created_at: Optional[datetime.datetime]
    updated_at: Optional[datetime.datetime]

# Speech-to-Text & Text-to-Speech
class STTResponse(BaseModel):
    transcript: str
    language_code: str
    engine_used: str  # "sarvam", "whisper_fallback", or "mock"
    confidence: Optional[float] = None

class TTSRequest(BaseModel):
    text: str
    target_language: str = "hi"  # "hi", "kn", "en"
    speaker: Optional[str] = "meera"

class TTSResponse(BaseModel):
    audio_base64: str
    format: str = "wav"
    engine_used: str  # "sarvam" or "mock"

# NLP & Translation
class TranslationRequest(BaseModel):
    text: str
    source_language: Optional[str] = None
    target_language: str = "en"  # canonical default

class TranslationResponse(BaseModel):
    original_text: str
    detected_language: str
    translated_text: str
    engine_used: str

class IntentEntityRequest(BaseModel):
    text: str  # canonical English text

class EntityItem(BaseModel):
    text: str
    label: str
    confidence: float

class IntentEntityResponse(BaseModel):
    intent: str
    intent_confidence: float
    entities: List[EntityItem]
    model_used: str

# RAG & Sub-agent Orchestration
class RetrievedChunk(BaseModel):
    id: str
    content: str
    source: str
    similarity_score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)

class QueryPipelineRequest(BaseModel):
    session_id: Optional[str] = "default-session"
    text: Optional[str] = None
    language: Optional[str] = None  # user specified or auto-detect
    audio_base64: Optional[str] = None  # if voice input is sent

class QueryPipelineResponse(BaseModel):
    session_id: str
    original_query: str
    detected_language: str
    canonical_query: str
    intent: str
    intent_confidence: float
    entities: List[EntityItem]
    sub_agent: str
    answer_canonical: str
    answer_translated: str
    short_answer_canonical: Optional[str] = None
    short_answer_translated: Optional[str] = None
    confidence_score: float
    is_low_confidence: bool
    is_fallback: bool = False
    flag_reason: Optional[str] = None
    retrieved_chunks: List[RetrievedChunk] = Field(default_factory=list)
    live_data: Optional[Dict[str, Any]] = None
    audio_base64: Optional[str] = None  # optional TTS response

# Live Data Schemas
class MandiPriceItem(BaseModel):
    commodity: str
    state: str
    district: str
    market: str
    min_price: float
    max_price: float
    modal_price: float
    arrival_date: str
    source: str

class WeatherData(BaseModel):
    location: str
    latitude: float
    longitude: float
    temperature: float
    humidity: float
    precipitation_prob: float
    wind_speed: float
    forecast_summary: str
    advisory: str
    source: str

class SchemeEligibilityItem(BaseModel):
    scheme_id: str
    scheme_name: str
    is_eligible: bool
    reason: str
    benefits: str
    portal_url: str

class IngestionResult(BaseModel):
    documents_ingested: int
    chunks_created: int
    vector_db_type: str
    status: str
    message: str
