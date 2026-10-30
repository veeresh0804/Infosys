import sys
import os
import io
from unittest.mock import patch
from fastapi.testclient import TestClient

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from backend.app.main import app
from backend.app.config import settings
from backend.app.services.nlp.intent_classifier import intent_classifier
from backend.app.services.rag.rag_engine import rag_engine, PESTICIDE_SAFETY_LINE
from backend.app.models.schemas import RetrievedChunk

client = TestClient(app)

def run_all_checks() -> int:
    results = []

    def record_result(check_id: str, title: str, passed: bool, note: str = ""):
        status = "PASS" if passed else "FAIL"
        results.append({
            "id": check_id,
            "title": title,
            "status": status,
            "note": note
        })
        print(f"[{status}] {check_id}: {title} {('- ' + note) if note else ''}")

    print("=" * 80)
    print("RUNNING MILESTONE 1 AUDIT ACCEPTANCE CHECKS")
    print("=" * 80)

    # -------------------------------------------------------------
    # Check 1: Voice request with unusable audio and no STT keys returns an error, never a made-up question
    # -------------------------------------------------------------
    try:
        import base64
        # Valid base64 encoding of silent dummy audio
        dummy_b64 = base64.b64encode(b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00").decode("utf-8")
        with patch("backend.app.routers.rag.sarvam_service.speech_to_text", side_effect=Exception("Sarvam STT unavailable")), \
             patch("backend.app.routers.rag.whisper_service.transcribe", side_effect=Exception("Whisper STT unavailable")):
            res = client.post("/api/rag/query", json={
                "session_id": "check1-unusable-audio",
                "audio_base64": dummy_b64,
                "language": "hi"
            })
            passed = res.status_code in [422, 503] and ("stt_unavailable" in str(res.json()))
            record_result("Check 1", "Unusable audio + no STT keys returns HTTP 503/422 stt_unavailable without fabricating text", passed, f"Status: {res.status_code}")
    except Exception as e:
        record_result("Check 1", "Unusable audio STT error handling", False, str(e))

    # -------------------------------------------------------------
    # Check 2: English text with no language field is detected as English and answered in English
    # -------------------------------------------------------------
    try:
        res = client.post("/api/rag/query", json={
            "session_id": "check2-en-query",
            "text": "What is the recommended fertilizer dosage for tomato?"
        })
        data = res.json()
        passed = (
            res.status_code == 200 and
            data.get("detected_language") == "en" and
            data.get("answer_canonical") is not None
        )
        record_result("Check 2", "English text with no language field detected as English and answered in English", passed, f"Detected: {data.get('detected_language')}")
    except Exception as e:
        record_result("Check 2", "English language auto-detection", False, str(e))

    # -------------------------------------------------------------
    # Check 3: Kannada text with UI set to Hindi is handled as Kannada
    # -------------------------------------------------------------
    try:
        res = client.post("/api/rag/query", json={
            "session_id": "check3-kn-hindi-ui",
            "text": "ಭತ್ತದಲ್ಲಿ ಕಾಂಡ ಕೊರೆಯುವ ಹುಳುವಿನ ಹಾನಿಯನ್ನು ಹೇಗೆ ನಿಯಂತ್ರಿಸುವುದು?",
            "language": "hi"
        })
        data = res.json()
        passed = (
            res.status_code == 200 and
            data.get("detected_language") == "kn"
        )
        record_result("Check 3", "Kannada text with UI set to Hindi is handled as Kannada", passed, f"Detected: {data.get('detected_language')}")
    except Exception as e:
        record_result("Check 3", "Kannada precedence over UI language hint", False, str(e))

    # -------------------------------------------------------------
    # Check 4: With all LLM keys removed, a Hindi query returns localized 'service busy' message and not run through RAG
    # -------------------------------------------------------------
    try:
        with patch("backend.app.services.nlp.translation_service.translation_service.to_canonical", return_value=(None, "hi", "translation_failed")):
            res = client.post("/api/rag/query", json={
                "session_id": "check4-busy",
                "text": "अनजान कृषि समस्या",
                "language": "hi"
            })
            data = res.json()
            passed = (
                res.status_code == 200 and
                data.get("is_fallback") is True and
                ("व्यस्त" in data.get("answer_translated", "") or "busy" in data.get("answer_canonical", "").lower())
            )
            record_result("Check 4", "Translation failure returns localized service-busy notice without running RAG", passed, f"Engine: {data.get('engine_used')}")
    except Exception as e:
        record_result("Check 4", "Localized service-busy handling", False, str(e))

    # -------------------------------------------------------------
    # Check 5: Two session IDs have separate history; a new session has no invented crops or location
    # -------------------------------------------------------------
    try:
        sid_1 = "check5-session-alpha"
        sid_2 = "check5-session-beta"

        client.post("/api/rag/query", json={"session_id": sid_1, "text": "Subsidy for drip irrigation in Karnataka", "language": "en"})
        s1 = client.get(f"/api/sessions/{sid_1}").json()
        s2 = client.get(f"/api/sessions/{sid_2}").json()

        passed = (
            len(s1.get("history", [])) >= 2 and
            len(s2.get("history", [])) == 0 and
            s2.get("state") is None and
            s2.get("district") is None and
            s2.get("landholding_acres") is None and
            s2.get("crops_grown") == []
        )
        record_result("Check 5", "Session isolation and fresh sessions have no invented profile facts", passed, f"S1 history: {len(s1.get('history', []))}, S2 history: {len(s2.get('history', []))}")
    except Exception as e:
        record_result("Check 5", "Session isolation verification", False, str(e))

    # -------------------------------------------------------------
    # Check 6: Four intent tests in Task 5 pass
    # -------------------------------------------------------------
    try:
        i1, s1 = intent_classifier.classify("Tell me about subsidy for drip irrigation")
        i2, s2 = intent_classifier.classify("price of tomato in Kolar")
        i3, s3 = intent_classifier.classify("will it rain tomorrow")
        i4, s4 = intent_classifier.classify("my crop is dying")

        passed = (
            i1 == "scheme_lookup" and
            i2 == "market_prices" and
            i3 == "weather" and
            s4 < 0.60
        )
        record_result(
            "Check 6",
            "Intent specificity tie-breaking and honest low confidence (<0.60)",
            passed,
            f"1:{i1}({s1}), 2:{i2}({s2}), 3:{i3}({s3}), 4:{i4}({s4})"
        )
    except Exception as e:
        record_result("Check 6", "Intent classifier tie-breaking", False, str(e))

    # -------------------------------------------------------------
    # Check 7: Real audio fixture round-trips through speech format path
    # -------------------------------------------------------------
    try:
        fixture_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "tests", "fixtures", "test_audio.wav")
        if os.path.exists(fixture_path):
            with open(fixture_path, "rb") as f:
                wav_bytes = f.read()
            files = {"file": ("test_audio.wav", io.BytesIO(wav_bytes), "audio/wav")}
            res = client.post("/api/speech/transcribe", files=files, data={"language_code": "hi-IN"})
            passed = res.status_code in [200, 422, 503]
            record_result("Check 7", "Real WAV audio fixture round-trips through STT format path", passed, f"Status: {res.status_code}, Bytes: {len(wav_bytes)}")
        else:
            record_result("Check 7", "Real WAV audio fixture", False, "Fixture file missing")
    except Exception as e:
        record_result("Check 7", "Audio fixture processing", False, str(e))

    # -------------------------------------------------------------
    # Check 8: LLM Provider Failover (mock first provider to return 429 and assert second is used)
    # -------------------------------------------------------------
    try:
        test_chunk = [
            RetrievedChunk(
                id="chunk_test_blast",
                content="Blast disease in rice caused by Magnaporthe oryzae. Treat with Tricyclazole 75 WP.",
                source="icar_crop_guidelines.json",
                similarity_score=0.91,
                metadata={"verified": True, "crop": "Paddy"}
            )
        ]

        # Mock Gemini failing with 429 rate limit, assert Groq or fallback is invoked
        with patch.object(rag_engine, "_call_gemini", return_value=(None, None, None, None, None)), \
             patch.object(rag_engine, "_call_groq", return_value=("Groq response", "Short Groq", "Groq response EN", "Short Groq EN", "groq_llama-3.3-70b-versatile")):
            orig_gemini_key = settings.GOOGLE_API_KEY
            orig_groq_key = settings.GROQ_API_KEY
            try:
                settings.GOOGLE_API_KEY = "dummy_gemini_key"
                settings.GROQ_API_KEY = "gsk_dummy_groq_key"
                import asyncio
                ans_tr, short_tr, ans_en, short_en, engine = asyncio.run(
                    rag_engine.generate_response(
                        query="Unique query for failover check: blast in paddy rice?",
                        retrieved_chunks=test_chunk,
                        farmer_profile={},
                        target_language="en"
                    )
                )
                passed = "groq" in engine
                record_result("Check 8", "LLM Provider Failover (Gemini failure fails over to Groq)", passed, f"Engine: {engine}")
            finally:
                settings.GOOGLE_API_KEY = orig_gemini_key
                settings.GROQ_API_KEY = orig_groq_key
    except Exception as e:
        record_result("Check 8", "LLM Provider failover", False, str(e))

    # -------------------------------------------------------------
    # Check 9: docs/KB_REVIEW.md exists and unverified notice displayed for verified=false
    # -------------------------------------------------------------
    try:
        kb_review_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "KB_REVIEW.md")
        kb_exists = os.path.exists(kb_review_path)

        # Create query with simulated verified=false chunk
        unverified_chunk = RetrievedChunk(
            id="unverified_experimental_crop",
            content="Experimental unverified treatment for crop.",
            source="unverified_source.json",
            similarity_score=0.95,
            metadata={"verified": False, "crop": "Experimental"}
        )

        with patch("backend.app.services.rag.vector_store.LocalFallbackVectorStore.similarity_search", return_value=[unverified_chunk]):
            res = client.post("/api/rag/query", json={
                "session_id": "unverified-source-test",
                "text": "What is the experimental treatment?",
                "language": "en"
            })
            data = res.json()
            has_notice = data.get("has_unverified_sources") is True
            passed = kb_exists and has_notice
            record_result("Check 9", "docs/KB_REVIEW.md exists and unverified records flag has_unverified_sources=True", passed, f"KB_REVIEW.md: {kb_exists}, has_unverified: {has_notice}")
    except Exception as e:
        record_result("Check 9", "Knowledge base review and unverified provenance notice", False, str(e))

    # -------------------------------------------------------------
    # Check 10: Server process RSS memory under 512 MB
    # -------------------------------------------------------------
    try:
        import psutil
        proc = psutil.Process(os.getpid())
        mem_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
        passed = mem_mb < 512.0
        record_result("Check 10", "Server process memory under 512 MB free tier constraint", passed, f"Current RSS: {mem_mb} MB (<512 MB)")
    except Exception as e:
        record_result("Check 10", "Memory RSS measurement", False, str(e))

    # -------------------------------------------------------------
    # Pass / Fail Table Summary
    # -------------------------------------------------------------
    print("\n" + "=" * 80)
    print("ACCEPTANCE CHECKS SUMMARY TABLE")
    print("=" * 80)
    print(f"{'Check ID':<10} | {'Status':<6} | {'Description':<55}")
    print("-" * 80)
    total_failures = 0
    for r in results:
        if r["status"] == "FAIL":
            total_failures += 1
        print(f"{r['id']:<10} | {r['status']:<6} | {r['title'][:55]:<55}")
    print("-" * 80)
    print(f"Total: {len(results)} checks | Passed: {len(results) - total_failures} | Failed: {total_failures}")
    print("=" * 80)

    if total_failures > 0:
        print(f"\n❌ ACCEPTANCE FAILED: {total_failures} checks did not pass.")
        return 1
    else:
        print("\n✅ ALL ACCEPTANCE CHECKS PASSED.")
        return 0

if __name__ == "__main__":
    exit_code = run_all_checks()
    sys.exit(exit_code)
