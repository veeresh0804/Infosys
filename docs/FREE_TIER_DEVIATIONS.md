# Free Tier Architectural Deviations & Mentor Justification

This document details all technical deviations made from the original internship project specification to enable the platform to run **100% on free tiers with zero cost, zero credit cards, and fit within 512 MB RAM hosting limits**.

---

## 1. Embeddings & Vector Store
* **Original Project Document**:
  Specified Pinecone or ChromaDB with `sentence-transformers` for embedding 384-dimensional dense vectors.
* **What Changed**:
  - The default vector store was changed from `pinecone` to `local` (a prebuilt, file-backed cosine-similarity vector store in `data/local_vector_index.json`).
  - PyTorch-based `sentence-transformers` was replaced in the default deployment with **`fastembed` (ONNX Runtime)** using the exact same `sentence-transformers/all-MiniLM-L6-v2` 384-dimensional architecture.
  - Pinecone and ChromaDB remain fully supported as configurable options in `.env`.
* **Mentor Justification / Why**:
  - The smallest free cloud hosts (e.g. Render free web service) enforce a strict **512 MB RAM limit**.
  - Importing PyTorch (`torch`) immediately consumes 350–450 MB RAM, causing immediate Out-Of-Memory (`OOMKilled`) crashes upon container boot.
  - `fastembed` utilizes a lightweight C++ ONNX Runtime that consumes less than 50 MB RAM and computes 384-dimensional vectors with high fidelity.
  - Free cloud hosts feature ephemeral container disks; committing the prebuilt 50-chunk index (`data/local_vector_index.json`) ensures zero startup cold-start delays.

---

## 2. LLM Synthesis & Ordered Provider Chain
* **Original Project Document**:
  Specified a single configurable large language model API call for RAG synthesis and back-translation.
* **What Changed**:
  - Implemented an **ordered resilient provider chain**:
    1. **Primary**: Google Gemini Free Tier (`gemini-2.5-flash`) via Google AI Studio.
    2. **Secondary Fallback**: Groq Free Tier (`llama-3.3-70b-versatile`).
    3. **Final Fallback**: Domain-grounded deterministic agricultural synthesis mock.
  - Added **24-hour SQLite response caching** for repeated queries.
  - Added **Direct Native Generation**: The LLM is instructed to synthesize answers directly in the farmer's requested language (Hindi, Kannada, English) from English retrieved chunks.
* **Mentor Justification / Why**:
  - Free tiers enforce rate limits (Google AI Studio allows 15 RPM / 1500 Requests Per Day).
  - Without an ordered chain, when a free daily quota is reached, student demo evaluations would crash. With the chain, it fails over to Groq and then to verified domain mocks.
  - Caching repeated questions ensures evaluation benchmarks cost zero API calls.
  - Direct generation in the target language halves external API calls by eliminating separate back-translation requests.

---

## 3. Speech-to-Text (STT) Fallback
* **Original Project Document**:
  Specified Sarvam AI Saaras as primary STT, with OpenAI Whisper as the secondary fallback.
* **What Changed**:
  - Replaced paid OpenAI Whisper API with **Groq-hosted Whisper (`whisper-large-v3-turbo`)** and browser Web Speech API.
  - OpenAI Whisper is preserved as a configurable option if an `OPENAI_API_KEY` is supplied.
* **Mentor Justification / Why**:
  - OpenAI Whisper has no free tier and requires paid per-minute billing and a credit card.
  - Groq provides free-tier Whisper transcription at ultra-low latencies with no credit card required.

---

## 4. Sarvam AI Credit Preservation & Circuit Breaker
* **Original Project Document**:
  Assumed uninterrupted live calls to Sarvam AI STT, TTS, and Translation.
* **What Changed**:
  - Added a process-lifetime **Circuit Breaker**: Upon detecting HTTP 402/403/429 (credit exhaustion or rate limits), the backend logs once and permanently switches to free fallbacks (Groq Whisper, free LLM translation, and browser `speechSynthesis`).
  - Added `SARVAM_ENABLED=false` environment toggle for zero-credit local testing.
  - Added SQLite caching for synthesized TTS audio by hash of text, language, and speaker.
  - Capped synthesized voice text to concise summaries (~250 characters).
* **Mentor Justification / Why**:
  - Sarvam AI issues one-time trial credits upon signup that do not renew automatically.
  - If credits run out during a mentor presentation, the circuit breaker guarantees the application continues working without throwing uncaught exceptions.

---

## 5. Hugging Face Models on 512 MB Hosts
* **Original Project Document**:
  Specified Hugging Face transformer models for zero-shot intent classification (`facebook/bart-large-mnli`) and agricultural Named Entity Recognition (`dslim/bert-base-NER`).
* **What Changed**:
  - In default cloud deployment, intent classification utilizes the high-precision domain keyword/regex classifier with free LLM fallback.
  - Agricultural NER utilizes the curated Agricultural Domain Gazetteers.
  - PyTorch transformer pipelines are guarded behind `ENABLE_HF_LOCAL=true` and isolated in `backend/requirements-local.txt`.
* **Mentor Justification / Why**:
  - `facebook/bart-large-mnli` weighs 1.63 GB on disk and consumes >2 GB RAM during model initialization.
  - Attempting to load BART or BERT on a 512 MB RAM instance crashes the web server immediately. The gazetteer and rule engine provide microsecond response times and 0 MB additional memory overhead.

---

## 6. Live Weather & Mandi APIs
* **Terms & Commercial Status**:
  - **Open-Meteo**: Confirmed 100% free for non-commercial educational use (up to 10,000 daily API calls, requires no API key).
  - **data.gov.in AGMARKNET**: Free government open data portal key; includes sample APMC fallback with clear UI badges when API keys are pending approval.

---

## 7. RAG Orchestration Framework (LangChain vs. Direct Async Orchestration)
* **Original Project Document**:
  Specified using LangChain for vector database querying and prompt assembly chains.
* **What Changed**:
  - Implemented direct, high-performance async RAG synthesis using native HTTPX clients and structured JSON prompting (`gemini-2.5-flash` / `llama-3.3-70b-versatile`).
  - FastEmbed ONNX was used directly with cosine similarity vector indexing.
* **Mentor Justification / Why**:
  - Standard `langchain` and `langchain-community` packages install dozens of transitively heavy dependencies (pydantic-v1 shims, dataclass wrappers, tenacity, langchain-core) that increase cold-start import time by >3.5 seconds and consume an additional 70–110 MB RAM, threatening the 512 MB memory boundary.
  - Direct async synthesis gives 100% control over JSON output schemas, structured multi-field generation (`answer_canonical`, `answer_translated`, `short_answer`), and transparent error failover.

---

## 8. Sarvam AI API Specs Hardening
* **Original Project Document**:
  Specified generic parameters for Sarvam STT, TTS, and Translation without error handling details.
* **What Changed**:
  - Replaced legacy `bulbul:v2` parameters: Removed `pitch` and `loudness` per official Sarvam `bulbul:v3` API documentation.
  - Implemented honest circuit breaker: Permanent trip for HTTP 401/402/403 (credit exhaustion) and temporary 60-second cooldown for HTTP 429 rate limits.
  - Sentence-boundary TTS summarization: Synthesizes clean sentence completions splitting on both Latin `.` and Indic `।` (preventing mid-sentence or mid-word cutoffs).
  - Translation input chunking for texts exceeding Sarvam API character limits.
* **Mentor Justification / Why**:
  - Sending unsupported parameters (`pitch`, `loudness`) to `bulbul:v3` causes HTTP 422 Unprocessable Entity errors from Sarvam.
  - Handling 429 with cool-down prevents permanent failure when momentary concurrency occurs during farmer interactions.

