# Code Deletion Log

## [2026-10-30] Refactor Session (subagent: refactor-cleaner)

Scope: dead code and duplicate elimination across `backend/`, `data/ingestion/`, `scripts/`, and `dashboard/`.
Detection: full manual reference trace of every module (repo is Python FastAPI + Next.js; knip/ts-prune/depcheck not applicable — frontend has zero unused deps, verified against `src/` imports).

### Unused Imports Removed
- `backend/app/routers/speech.py` — `STTUnavailableError` (imported, never raised in this module)
- `backend/app/routers/rag.py` — `typing.List`, `typing.Optional`, `FlaggedReviewModel`, `RetrievedChunk` (not referenced in body)
- `backend/app/routers/ingestion.py` — `fastapi.Security` (unused)
- `backend/app/main.py` — duplicate `import os` inside `health_check()` (module already imports `os`)
- `backend/app/services/session/session_service.py` — `SessionResponse`
- `backend/app/services/live_data/weather_service.py` — `config.settings` (never read)
- `backend/app/services/nlp/intent_classifier.py` — `json`, `typing.Any`, `typing.Optional`, `config.settings`
- `backend/app/services/nlp/ner_service.py` — `typing.Dict`, `typing.Any`
- `backend/app/services/nlp/sarvam_service.py` — `typing.Dict`, `typing.Any`, `typing.List`
- `backend/app/services/nlp/translation_service.py` — `re` (no `re.` usage in module)
- `backend/app/services/rag/quality_scorer.py` — `sqlalchemy.ext.asyncio.AsyncSession` (module uses `AsyncSessionLocal` directly)
- `backend/tests/test_endpoints.py` — `pytest`, `unittest.mock.MagicMock` (no references in file)
- `scripts/run_all_acceptance_checks.py` — `time`, `json` (no references in file)
- `data/ingestion/ingest.py` — `get_vector_store` (imported, never called; module uses `LocalFallbackVectorStore` directly)
- `backend/app/services/agents/{market_price,weather,scheme_lookup}_agent.py` — `import logging` + unused `logger`

### Unused Code Removed
- `backend/app/services/nlp/intent_classifier.py` — `IntentClassifierService.__init__` and `_load_hf_pipeline()`.
  Reason: private methods with zero call sites anywhere in the repo; the HF zero-shot pipeline was never wired
  into `classify_intent()` (contrast: `ner_service._load_hf_pipeline()` IS called and was kept).
  Fields `model_name`, `_pipeline`, `_hf_available` were only consumed by the dead loader. Stale docstring updated.
- `backend/app/exceptions.py` — `TranslationUnavailableError` (defined but never imported or raised repo-wide;
  translation failure is honestly flagged via the `translation_failed` engine tag instead).
- `dashboard/ui.py` — `fmt_rupees()` (exported helper with no callers in dashboard views).

### Duplicate Code Consolidated
- `backend/app/services/agents/crop_advisory_agent.py` + `pest_control_agent.py` were byte-identical
  (same `vector_store.similarity_search(top_k=3)` → `rag_engine.generate_response()` → `extra_data` assembly;
  only the `"sub_agent"` key differed).
  → Consolidated into new `backend/app/services/agents/base_rag_agent.py::BaseRAGAdvisoryAgent`;
  both agents are now 12-line subclasses declaring only `sub_agent_name` and their docstring.
  Public singletons (`crop_advisory_agent`, `pest_control_agent`), class names, and method signatures unchanged.

### Bug Fixed (found during analysis)
- `data/ingestion/ingest.py` — `run_ingestion()` imported `ChromaVectorStore`, but the class in
  `vector_store.py` is named `ChromaDBVectorStore`; any `VECTOR_DB_TYPE=chromadb` run raised `ImportError`.
  Import corrected. (Latent — default config uses the `local` store.)

### Impact
- Files modified: 19, files added: 1 (`base_rag_agent.py`), files deleted: 0
- Lines of code removed: ~135; added: ~55 → net ≈ −80 LOC
- No frontend changes (frontend deps and exports verified fully used: `next`, `react`, `react-dom`, `@types/*`,
  `api.ts` exports all imported by components; all 9 `Icons.tsx` exports used by `page.tsx`)

### Verification
- `pytest backend/tests/test_endpoints.py` — **10/10 passed** (same as pre-change baseline)
- `python scripts/run_all_acceptance_checks.py` — **10/10 checks passed**
- `python -m compileall` over `backend/app`, `data/ingestion`, `backend/tests`, `scripts`, `dashboard` — OK
- Grep sweep: no lingering references to any removed symbol
- Note: running the acceptance checks regenerates `backend/data/local_vector_index.json`; that side effect was
  reverted (`git checkout`) so the working tree only contains intentional changes.

### Remaining (manual review needed — NOT removed)
- `dashboard/api_client.py` — `health()`, `translate()`, `intent_entities()`: no callers, but thin REST-mirror
  methods of the client class; kept for API parity. Remove if the dashboard will never surface them.
- `backend/app/config.py` — `HF_INTENT_MODEL` is now unread (HF intent loading was dead); kept because it is a
  documented env surface in `backend/.env.example` and `config/.env.example`.
- `backend/app/config.py` — `OPENAI_API_KEY` is a deprecated optional STT key still honored by
  `whisper_fallback.py`; kept deliberately.
- `dashboard/api_client.py` — `LocalFallbackVectorStore` persistence writes to both candidate paths; intentional.
- Not committed: working tree contains unrelated in-flight changes (`README.md`, `frontend/src/app/page.tsx`
  test-ids, `e2e/`, `dashboard/` from other sessions). Commit only the files listed above, separately.
