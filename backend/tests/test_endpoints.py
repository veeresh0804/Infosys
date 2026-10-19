import requests
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"

def test_all():
    print("1. Root Status:")
    r = requests.get(f"{BASE}/")
    print(r.status_code, r.json())
    assert r.status_code == 200

    print("\n2. Translation Test (Hindi -> Canonical EN):")
    r = requests.post(f"{BASE}/api/nlp/translate", json={"text": "टमाटर में पत्ता मरोड़ रोग की रोकथाम कैसे करें?", "target_language": "en"})
    print(r.status_code, r.json())
    assert r.status_code == 200

    print("\n3. Intent & Entity Extraction:")
    r = requests.post(f"{BASE}/api/nlp/intent-entities", json={"text": "How to control yellow stem borer in paddy rice with chlorantraniliprole?"})
    print(r.status_code, r.json())
    assert r.status_code == 200

    print("\n4. Live Weather API (Open-Meteo):")
    r = requests.get(f"{BASE}/api/live-data/weather?district=Mandya")
    print(r.status_code, r.json()["location"], r.json()["temperature"], r.json()["advisory"][:60])
    assert r.status_code == 200

    print("\n5. Live Mandi Prices:")
    r = requests.get(f"{BASE}/api/live-data/mandi-prices?commodity=Tomato")
    print(r.status_code, len(r.json()), r.json()[0])
    assert r.status_code == 200

    print("\n6. Govt Schemes Evaluation:")
    r = requests.get(f"{BASE}/api/live-data/scheme-eligibility?landholding_acres=3.0&crops=Paddy,Tomato")
    print(r.status_code, len(r.json()), [s["scheme_name"] for s in r.json() if s["is_eligible"]])
    assert r.status_code == 200

    print("\n7. End-to-End Pipeline Query (Hindi Crop Pest Query):")
    r = requests.post(f"{BASE}/api/rag/query", json={
        "session_id": "test-session-1",
        "text": "टमाटर के पत्ते ऊपर मुड़ रहे हैं और पीले हो रहे हैं, उपाय बताएं",
        "language": "hi"
    })
    res = r.json()
    print("Status:", r.status_code)
    print("Intent:", res.get("intent"), "| Sub-Agent:", res.get("sub_agent"))
    print("Confidence:", res.get("confidence_score"), "| Low Confidence Flagged:", res.get("is_low_confidence"))
    print("Chunks Retrieved:", len(res.get("retrieved_chunks", [])))
    print("Answer (Translated):", res.get("answer_translated")[:140])
    assert r.status_code == 200

    print("\n8. End-to-End Pipeline Query (Kannada Query):")
    r = requests.post(f"{BASE}/api/rag/query", json={
        "session_id": "test-session-1",
        "text": "ಭತ್ತದಲ್ಲಿ ಕಾಂಡ ಕೊರೆಯುವ ಹುಳುವಿನ ಹಾನಿಯನ್ನು ಹೇಗೆ ನಿಯಂತ್ರಿಸುವುದು?",
        "language": "kn"
    })
    res = r.json()
    print("Status:", r.status_code)
    print("Intent:", res.get("intent"), "| Sub-Agent:", res.get("sub_agent"))
    print("Answer (Translated):", res.get("answer_translated")[:140])
    assert r.status_code == 200

    print("\n9. Verify SQLite Session State & Flagged Reviews:")
    r_session = requests.get(f"{BASE}/api/sessions/test-session-1")
    print("Session History Count:", len(r_session.json().get("history", [])))
    r_flagged = requests.get(f"{BASE}/api/rag/flagged-reviews")
    print("Flagged Reviews Count:", len(r_flagged.json()))

    print("\nALL ENDPOINT TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_all()
