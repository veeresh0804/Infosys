import os
import io
import pytest
from unittest.mock import patch, MagicMock
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
