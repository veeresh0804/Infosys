# AI-Driven Smart Farming Assistant (Milestones 1 & 2)

**A full-stack multilingual AI agricultural guidance platform** providing rural Indian farmers with expert advisory on crop management, soil health, pest control, government subsidies, and APMC mandi market prices in **Hindi (हिन्दी)**, **Kannada (ಕನ್ನಡ)**, and **English**, via voice and text.

---

## 🏗️ Architecture & Monorepo Structure

```
Infosys/
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI application entrypoint with CORS & routers
│   │   ├── config.py                   # Pydantic BaseSettings configuration loader
│   │   ├── database.py                 # SQLAlchemy async engine & SQLite setup
│   │   ├── models/
│   │   │   └── schemas.py              # Pydantic & SQLAlchemy models (Sessions, Flagged Reviews)
│   │   ├── services/
│   │   │   ├── nlp/
│   │   │   │   ├── sarvam_service.py   # Sarvam AI Indic STT (Saaras), TTS (Bulbul), Translation (Mayura)
│   │   │   │   ├── whisper_fallback.py # OpenAI Whisper STT fallback
│   │   │   │   ├── translation_service.py # Canonical language & back-translation orchestration
│   │   │   │   ├── intent_classifier.py# Intent classification (HF BART-MNLI & domain rule classifier)
│   │   │   │   └── ner_service.py      # Agricultural NER (HF bert-base-NER & Agri Gazetteer)
│   │   │   ├── rag/
│   │   │   │   ├── vector_store.py     # Pinecone & ChromaDB configurable vector store
│   │   │   │   ├── embeddings.py       # SentenceTransformers (all-MiniLM-L6-v2, 384 dim)
│   │   │   │   ├── rag_engine.py       # LangChain RAG synthesis with configurable LLM (Gemini, Groq, OpenAI)
│   │   │   │   └── quality_scorer.py   # Response quality scoring & human review flagging (< 0.70)
│   │   │   ├── live_data/
│   │   │   │   ├── mandi_service.py    # AGMARKNET APMC mandi price API & clearly-labelled mock
│   │   │   │   ├── weather_service.py  # Open-Meteo live weather & agro-meteorological advisory
│   │   │   │   └── scheme_checker.py   # Rule-based eligibility engine (PM-KISAN, PMFBY, KCC, Soil Health Card)
│   │   │   ├── agents/
│   │   │   │   ├── router.py           # Central Agent Router & telemetry pipeline
│   │   │   │   ├── crop_advisory_agent.py
│   │   │   │   ├── pest_control_agent.py
│   │   │   │   ├── market_price_agent.py
│   │   │   │   ├── weather_agent.py
│   │   │   │   └── scheme_lookup_agent.py
│   │   │   └── session/
│   │   │       └── session_service.py  # SQLite conversation state & user preferences
│   │   └── routers/
│   │       ├── speech.py               # /api/speech/transcribe, /api/speech/synthesize
│   │       ├── nlp.py                  # /api/nlp/translate, /api/nlp/intent-entities
│   │       ├── rag.py                  # /api/rag/query, /api/rag/flagged-reviews
│   │       ├── live_data.py            # /api/live-data/mandi-prices, /weather, /scheme-eligibility
│   │       ├── sessions.py             # /api/sessions/{session_id}
│   │       └── ingestion.py            # /api/ingestion/reindex
│   ├── tests/
│   │   └── test_endpoints.py           # Automated end-to-end integration test suite
│   ├── requirements.txt                # Python backend dependencies
│   ├── .env                            # Active environment configuration
│   └── .env.example                    # Backend environment template
├── data/
│   ├── knowledge_base/
│   │   ├── icar_crop_guidance.json     # Curated ICAR package of practices (Paddy, Wheat, Tomato, Cotton, Maize)
│   │   ├── kcc_faqs.json               # Curated Kisan Call Centre farmer pest/disease resolutions
│   │   └── government_schemes.json     # Curated central/state agricultural scheme dossiers
│   └── ingestion/
│       └── ingest.py                   # Script to chunk, embed and index documents into vector store
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx              # Root HTML & metadata
│   │   │   ├── page.tsx                # Main verification dashboard
│   │   │   └── globals.css             # Vanilla CSS design system
│   │   ├── components/
│   │   │   ├── AudioRecorder.tsx       # In-browser microphone recorder
│   │   │   ├── ChatInterface.tsx       # Multilingual chat with telemetry & TTS playback
│   │   │   ├── KnowledgeInspector.tsx  # Retrieved chunks & re-indexing control
│   │   │   ├── LiveDataInspector.tsx   # Live Mandi, Weather & Scheme evaluators
│   │   │   └── SessionStateInspector.tsx# Profile context, preferences & review queue
│   │   └── lib/
│   │       └── api.ts                  # Typed frontend API client
│   ├── package.json
│   └── tsconfig.json
├── config/
│   └── .env.example                    # Root master configuration reference
└── README.md
```

---

## 🚀 Setup & Execution Guide

### Prerequisites
- **Python**: 3.12 (with `py` launcher or `python`)
- **Node.js**: v18+ (tested on Node v24)
- **pip** and **npm**

### 1. Backend Setup
```bash
# In project root:
cd backend

# Create virtual environment with Python 3.12:
py -3.12 -m venv venv

# Activate virtual environment (Windows PowerShell):
.\venv\Scripts\Activate.ps1

# Install dependencies:
pip install -r requirements.txt

# Configure environment:
cp .env.example .env

# Run database & knowledge base ingestion:
python -m data.ingestion.ingest

# Start FastAPI server on port 8000:
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend Setup
```bash
# Open a second terminal and navigate to frontend:
cd frontend

# Install Node dependencies:
npm install

# Start Next.js development server on port 3000:
npm run dev
```

### 3. Open in Browser
- **Farmer Test UI**: [http://localhost:3000](http://localhost:3000)
- **FastAPI Auto-Generated Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **FastAPI ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 🧪 Automated Testing
Run the comprehensive test suite verifying all Milestone 1 & 2 components:
```bash
c:\Users\manoh\Desktop\Infosys\backend\venv\Scripts\python.exe -u backend/tests/test_endpoints.py
```
This suite automatically exercises:
1. Root health & provider configuration
2. Language detection and translation (Hindi/Kannada -> Canonical English)
3. Intent classification and Agricultural Named Entity Recognition
4. Live Open-Meteo weather advisory
5. AGMARKNET Mandi price retrieval
6. Government scheme eligibility evaluation (PM-KISAN, PMFBY, KCC, Soil Health Card)
7. End-to-end Hindi query pipeline with knowledge-base chunk retrieval & answer synthesis
8. End-to-end Kannada query pipeline
9. Session state persistence and low-confidence human review queuing in SQLite.

---

## 📡 REST API Reference

### 1. Speech Processing
- **`POST /api/speech/transcribe`**
  - **Payload**: `multipart/form-data` with `file: <audio_file>`, `language_code: <optional>`
  - **Response**: `{"transcript": "...", "language_code": "hi-IN", "engine_used": "sarvam_saaras", "confidence": 0.92}`
- **`POST /api/speech/synthesize`**
  - **Payload**: `{"text": "...", "target_language": "hi", "speaker": "meera"}`
  - **Response**: `{"audio_base64": "...", "format": "wav", "engine_used": "sarvam_bulbul"}`

### 2. NLP & Translation
- **`POST /api/nlp/translate`**
  - **Payload**: `{"text": "...", "source_language": "hi", "target_language": "en"}`
  - **Response**: `{"original_text": "...", "detected_language": "hi", "translated_text": "...", "engine_used": "..."}`
- **`POST /api/nlp/intent-entities`**
  - **Payload**: `{"text": "How to control yellow stem borer in paddy rice with chlorantraniliprole?"}`
  - **Response**: `{"intent": "pest_control", "intent_confidence": 0.83, "entities": [{"text": "paddy", "label": "CROP"}, ...], "model_used": "..."}`
- **`GET /api/nlp/detect-language?text=...`**
  - **Response**: `{"text": "...", "detected_language": "hi"}`

### 3. RAG & Agent Orchestration
- **`POST /api/rag/query`**
  - **Payload**: `{"session_id": "...", "text": "...", "language": "hi", "audio_base64": null}`
  - **Response**: `{"session_id": "...", "original_query": "...", "detected_language": "...", "canonical_query": "...", "intent": "...", "intent_confidence": 0.85, "entities": [...], "sub_agent": "...", "answer_canonical": "...", "answer_translated": "...", "confidence_score": 0.82, "is_low_confidence": false, "retrieved_chunks": [...], "live_data": {...}}`
- **`GET /api/rag/flagged-reviews?limit=20`**
  - **Response**: List of flagged low-confidence queries (< 0.70 threshold) for extension workers.

### 4. Real-Time Data APIs
- **`GET /api/live-data/mandi-prices?commodity=Tomato&state=Karnataka`**
  - **Response**: `[{"commodity": "Tomato", "market": "Kolar APMC", "modal_price": 1850.0, "min_price": 1400.0, "max_price": 2200.0, ...}]`
- **`GET /api/live-data/weather?district=Bengaluru+Rural`**
  - **Response**: `{"location": "Bengaluru Rural", "temperature": 27.5, "humidity": 68.0, "precipitation_prob": 25.0, "advisory": "...", "source": "Open-Meteo"}`
- **`GET /api/live-data/scheme-eligibility?landholding_acres=2.5&crops=Tomato,Paddy`**
  - **Response**: `[{"scheme_name": "PM-KISAN", "is_eligible": true, "reason": "...", "benefits": "...", "portal_url": "..."}]`

### 5. Session State & Ingestion
- **`GET /api/sessions/{session_id}`**: Retrieves farmer profile, preferences, and chat history.
- **`PATCH /api/sessions/{session_id}`**: Updates farmer preferences (preferred language, acres, crops).
- **`POST /api/ingestion/reindex`**: Re-chunks and re-embeds knowledge base documents into vector store.

---

## 🔒 Configuration & Environment Variables

| Variable | Description | Default / Recommended |
|---|---|---|
| `SARVAM_API_KEY` | Sarvam AI Indic STT, TTS, and Translation Key | `your_sarvam_api_key_here` (Uses clearly-labelled mock if empty) |
| `OPENAI_API_KEY` | OpenAI Whisper STT fallback & optional LLM | `your_openai_api_key_here` (Uses clearly-labelled mock if empty) |
| `GOOGLE_API_KEY` | Google Gemini API key for free tier RAG | Free tier from Google AI Studio |
| `GEMINI_MODEL` | Gemini Model identifier | `gemini-1.5-flash` |
| `GROQ_API_KEY` | Groq API key for free tier open-source LLMs | `your_groq_api_key_here` |
| `PINECONE_API_KEY`| Pinecone cloud vector DB key | `your_pinecone_api_key_here` (Uses persistent local vector store if empty) |
| `VECTOR_DB_TYPE` | Selected vector database | `pinecone` (configurable to `chromadb`) |
| `EMBEDDING_MODEL_NAME` | Embedding model for semantic search | `sentence-transformers/all-MiniLM-L6-v2` |
| `DATA_GOV_IN_API_KEY` | data.gov.in AGMARKNET mandi key | Clearly-labelled APMC market mock if empty |
| `WEATHER_PROVIDER` | Weather forecast provider | `open-meteo` (Free, no key required) |
| `QUALITY_CONFIDENCE_THRESHOLD` | Threshold below which queries are flagged | `0.70` |
| `DATABASE_URL` | SQLite database URI | `sqlite+aiosqlite:///./data/sessions.db` |
