import os
import io
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.config import settings
from backend.app.services.rag.rag_engine import PESTICIDE_SAFETY_LINE
from backend.app.services.nlp.intent_classifier import intent_classifier
from backend.app.services.nlp.ner_service import ner_service

client = TestClient(app)

def test_health_and_root():
    """Verify /api/health and root return honest status and memory metrics."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["free_tier_mode"] is True
    assert "memory_rss_mb" in data
    assert "active_engines" in data
    assert "embeddings" in data["active_engines"]

    res_root = client.get("/")
    assert res_root.status_code == 200
    assert res_root.json()["status"] == "online"

def test_language_detection_kannada_with_ui_set_to_hindi():
    """Task 3: Kannada query with UI set to Hindi is treated as Kannada, not Hindi."""
    payload = {
        "session_id": "test-lang-kn-1",
        "text": "ಭತ್ತದಲ್ಲಿ ಕಾಂಡ ಕೊರೆಯುವ ಹುಳುವಿನ ಹಾನಿಯನ್ನು ಹೇಗೆ ನಿಯಂತ್ರಿಸುವುದು?",
        "language": "hi"
    }
    res = client.post("/api/rag/query", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "kn"
    # Canonical answer must be English
    assert data["answer_canonical"] is not None
    assert len(data["answer_canonical"]) > 0

def test_language_detection_english_with_no_language_field():
    """Task 3: English query with no language field is detected as English and answered in English."""
    payload = {
        "session_id": "test-lang-en-1",
        "text": "What is the recommended fertilizer dosage for tomato?"
    }
    res = client.post("/api/rag/query", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "en"
    assert data["answer_translated"] == data["answer_canonical"] or "fertilizer" in data["answer_translated"].lower() or "tomato" in data["answer_translated"].lower()

def test_intent_classification_tie_breaking_and_honest_confidence():
    """Task 5: Intent classification specificity tie-breaking and honest confidence."""
    # 1. Drip irrigation subsidy -> scheme_lookup
    intent, score = intent_classifier.classify("Tell me about subsidy for drip irrigation")
    assert intent == "scheme_lookup"
    assert score > 0.65

    # 2. Market price of tomato in Kolar -> market_prices
    intent, score = intent_classifier.classify("price of tomato in Kolar")
    assert intent == "market_prices"
    assert score > 0.65

    # 3. Weather check -> weather
    intent, score = intent_classifier.classify("will it rain tomorrow")
    assert intent == "weather"
    assert score > 0.65

    # 4. Ambiguous / vague -> low confidence, NOT 0.77
    intent, score = intent_classifier.classify("my crop is dying")
    assert score < 0.60, f"Confidence was {score}, expected honest low score < 0.60"

def test_session_isolation_and_no_invented_profile():
    """Task 6: Two sessions never see each other's history; new session starts empty."""
    sid_a = "session-iso-a"
    sid_b = "session-iso-b"

    # Query session A
    res_a = client.post("/api/rag/query", json={
        "session_id": sid_a,
        "text": "Tell me about drip irrigation subsidy",
        "language": "en"
    })
    assert res_a.status_code == 200

    # Inspect Session A
    state_a = client.get(f"/api/sessions/{sid_a}").json()
    assert len(state_a["history"]) >= 2

    # Inspect Session B - must have 0 history and no invented profile facts
    state_b = client.get(f"/api/sessions/{sid_b}").json()
    assert len(state_b["history"]) == 0
    assert state_b["state"] is None
    assert state_b["district"] is None
    assert state_b["landholding_acres"] is None
    assert state_b["crops_grown"] == []

def test_stt_unavailable_error_handling():
    """Task 1: When no STT is available or fails, return 503/422 stt_unavailable without pipeline continuation."""
    with patch("backend.app.routers.speech.sarvam_service.speech_to_text", side_effect=Exception("Sarvam failed")), \
         patch("backend.app.routers.speech.whisper_service.transcribe", side_effect=Exception("Whisper failed")), \
         patch("backend.app.routers.rag.sarvam_service.speech_to_text", side_effect=Exception("Sarvam failed")), \
         patch("backend.app.routers.rag.whisper_service.transcribe", side_effect=Exception("Whisper failed")):
        # Direct speech transcription endpoint
        files = {"file": ("test.wav", b"fake audio content", "audio/wav")}
        res = client.post("/api/speech/transcribe", files=files, data={"language_code": "hi-IN"})
        assert res.status_code in [422, 503]
        data = res.json()
        assert data.get("error") == "stt_unavailable" or "stt_unavailable" in str(data)

        # Voice branch in /api/rag/query
        res_voice = client.post("/api/rag/query", json={
            "session_id": "stt-fail-session",
            "audio_base64": "ZmFrZSBhdWRpbyBkYXRh",
            "language": "hi"
        })
        assert res_voice.status_code in [422, 503]
        data_voice = res_voice.json()
        assert data_voice.get("error") == "stt_unavailable" or "stt_unavailable" in str(data_voice)

def test_honest_translation_unavailable_handling():
    """Task 4: When translation fails, return localized service busy without running RAG."""
    with patch("backend.app.services.nlp.translation_service.translation_service.to_canonical", return_value=(None, "hi", "translation_failed")):
        res = client.post("/api/rag/query", json={
            "session_id": "trans-fail-session",
            "text": "अज्ञात कृषि प्रश्न",
            "language": "hi"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["is_fallback"] is True
        assert "व्यस्त" in data["answer_translated"] or "busy" in data["answer_canonical"].lower()

def test_standing_pesticide_safety_line_present():
    """Task 9: Standing pesticide advisory line must be present in code and prompt."""
    assert "follow the product label" in PESTICIDE_SAFETY_LINE.lower()
    assert "protective gear" in PESTICIDE_SAFETY_LINE.lower()
    assert "waiting period" in PESTICIDE_SAFETY_LINE.lower()
    assert "kisan call centre" in PESTICIDE_SAFETY_LINE.lower()

def test_audio_fixture_wav_file():
    """Task 2: Real WAV audio fixture can be sent to STT endpoint."""
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "test_audio.wav")
    assert os.path.exists(fixture_path), "test_audio.wav fixture missing"

    with open(fixture_path, "rb") as f:
        audio_bytes = f.read()

    assert len(audio_bytes) > 1000, "WAV fixture should have real PCM audio bytes"
    files = {"file": ("test_audio.wav", io.BytesIO(audio_bytes), "audio/wav")}

    # Without live Sarvam/Groq keys, the endpoint should return a clean 503 stt_unavailable or transcribe if keys are present
    res = client.post("/api/speech/transcribe", files=files, data={"language_code": "hi-IN"})
    assert res.status_code in [200, 422, 503]

def test_reindex_protected_behind_admin_token():
    """Task 11: /api/ingestion/reindex requires X-Admin-Token and returns real doc count."""
    # 1. Calling without token must be 403 Forbidden
    res_unauth = client.post("/api/ingestion/reindex")
    assert res_unauth.status_code == 403

    # 2. Calling with correct admin token
    res_auth = client.post(
        "/api/ingestion/reindex",
        headers={"X-Admin-Token": settings.ADMIN_API_KEY}
    )
    assert res_auth.status_code == 200
    data = res_auth.json()
    assert data["status"] == "success"
    assert data["documents_ingested"] == 26
    assert data["chunks_created"] == 50

def test_telemetry_pipeline_records_and_summarizes():
    """docs README: 'Agent Router & telemetry pipeline' - every routed query is recorded
    and exposed via the /api/telemetry observability endpoints."""
    res = client.post("/api/rag/query", json={"text": "Will it rain tomorrow in Kolar district?", "language": "en"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "weather"
    assert data["sub_agent"] == "weather"

    summary = client.get("/api/telemetry/summary").json()
    assert summary["total_queries"] >= 1, f"Telemetry row was not recorded: {summary}"
    assert summary["by_intent"].get("weather", 0) >= 1
    assert summary["by_sub_agent"].get("weather", 0) >= 1
    assert isinstance(summary["avg_latency_ms"], int)
    assert summary["avg_latency_ms"] >= 0
    assert summary["max_latency_ms"] is not None
    assert isinstance(summary["recent"], list)

    health = client.get("/api/telemetry/health").json()
    assert health["status"] == "healthy"

def test_intent_classification_chain_short_circuit_and_llm_fallback():
    """docs/FREE_TIER_DEVIATIONS.md SS5: confident rule decisions short-circuit;
    ambiguous ones honor ENABLE_HF_LOCAL and the free LLM chain when available."""
    import asyncio

    # 1. Confident rule match never spends an LLM call
    intent, conf, model = intent_classifier.classify_intent(
        "How to control yellow stem borer in paddy rice with chlorantraniliprole?"
    )
    assert intent == "pest_control" and conf >= 0.79 and model == "agri_domain_rule_classifier"

    # 2. Ambiguous query falls through to the LLM chain when it is available
    assert settings.ENABLE_HF_LOCAL is False

    async def fake_llm(text):
        return "scheme_lookup", 0.72, "gemini_test_intent_router"

    with patch("backend.app.services.rag.rag_engine.rag_engine.classify_intent_llm", side_effect=fake_llm):
        intent2, conf2, model2 = asyncio.run(intent_classifier.classify_intent_async("my crop issue"))
    assert intent2 == "scheme_lookup" and abs(conf2 - 0.72) < 1e-9 and model2 == "gemini_test_intent_router"

    # 3. With no LLM available, the honest low-confidence rule decision stays (no fabricated confidence)
    with patch("backend.app.services.rag.rag_engine.rag_engine.classify_intent_llm", side_effect=lambda t: None):
        intent3, conf3, model3 = asyncio.run(intent_classifier.classify_intent_async("my crop issue"))
    assert model3 == "agri_domain_rule_classifier" and conf3 < 0.60

def test_intent_hf_path_is_gated_and_graceful():
    """ENABLE_HF_LOCAL=true must use the HF zero-shot intent path and degrade
    gracefully when the model is unavailable - all without downloading real models."""
    import asyncio

    class FakeHFPipeline:
        """Stands in for the facebook/bart-large-mnli zero-shot pipeline."""
        def __call__(self, text, candidate_labels, hypothesis_template=None):
            assert hypothesis_template == "This farmer query is about {}."
            return {"labels": ["crop_advisory", "pest_control"], "scores": [0.81, 0.10]}

    async def must_not_be_called(text):
        raise AssertionError("LLM chain must not be consulted when the HF model resolves")

    async def fake_llm(text):
        return "weather", 0.68, "gemini_test_intent_router"

    # 1. HF path honors the flag and maps the zero-shot result/prepares an honest confidence
    with patch.object(settings, "ENABLE_HF_LOCAL", True):
        with patch.object(intent_classifier, "_hf_pipeline", FakeHFPipeline()):
            with patch("backend.app.services.rag.rag_engine.rag_engine.classify_intent_llm", side_effect=must_not_be_called):
                intent, conf, model = asyncio.run(intent_classifier.classify_intent_async("my crop issue"))
    assert intent == "crop_advisory" and abs(conf - 0.81) < 1e-9 and model == "facebook_bart_large_mnli"

    # 2. HF unavailable (no real transformers model) -> chain degrades to the LLM link, never crashes
    with patch.object(settings, "ENABLE_HF_LOCAL", True):
        with patch.dict("sys.modules", {"transformers": None}):
            with patch.object(intent_classifier, "_hf_pipeline", None):
                with patch("backend.app.services.rag.rag_engine.rag_engine.classify_intent_llm", side_effect=fake_llm):
                    intent2, conf2, model2 = asyncio.run(intent_classifier.classify_intent_async("my crop issue"))
    assert intent2 == "weather" and model2 == "gemini_test_intent_router"
