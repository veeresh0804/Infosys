import os
import sys
import base64
import asyncio

# Ensure project root in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from backend.app.services.nlp.sarvam_service import sarvam_service

TILES = [
    {
        "id": "crop_care",
        "texts": {
            "en": "Crop Care",
            "hi": "फसल देखभाल",
            "kn": "ಬೆಳೆ ನಿರ್ವಹಣೆ"
        }
    },
    {
        "id": "pests",
        "texts": {
            "en": "Pests and Diseases",
            "hi": "कीट और रोग",
            "kn": "ಕೀಟ ಮತ್ತು ರೋಗ"
        }
    },
    {
        "id": "mandi",
        "texts": {
            "en": "Market Prices",
            "hi": "मंडी भाव",
            "kn": "ಮಾರುಕಟ್ಟೆ ದರ"
        }
    },
    {
        "id": "weather",
        "texts": {
            "en": "Weather Forecast",
            "hi": "मौसम",
            "kn": "ಹವಾಮಾನ"
        }
    },
    {
        "id": "schemes",
        "texts": {
            "en": "Government Schemes",
            "hi": "सरकारी योजनाएं",
            "kn": "ಸರ್ಕಾರಿ ಯೋಜನೆಗಳು"
        }
    }
]

async def generate():
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "public", "audio", "tiles")
    os.makedirs(out_dir, exist_ok=True)

    print(f"Target audio directory: {out_dir}")
    print(f"Sarvam AI is_configured: {sarvam_service.is_configured}")

    results = {}
    for tile in TILES:
        tid = tile["id"]
        results[tid] = {}
        for lang, text in tile["texts"].items():
            file_name = f"{tid}_{lang}.wav"
            file_path = os.path.join(out_dir, file_name)
            try:
                b64, engine = await sarvam_service.text_to_speech(
                    text=text,
                    target_language=lang,
                    speaker="meera"
                )
                if engine.startswith("sarvam"):
                    audio_bytes = base64.b64decode(b64)
                    with open(file_path, "wb") as f:
                        f.write(audio_bytes)
                    print(f"✓ Generated {file_name} with {engine} ({len(audio_bytes)} bytes)")
                    results[tid][lang] = {"status": "ok", "path": f"/audio/tiles/{file_name}", "engine": engine}
                else:
                    print(f"⚠️ Mock engine returned for {file_name} ({engine}). Not writing fake audio.")
                    results[tid][lang] = {"status": "missing_key", "path": None, "engine": engine}
            except Exception as e:
                print(f"❌ Failed for {file_name}: {e}")
                results[tid][lang] = {"status": "error", "error": str(e)}

    return results

if __name__ == "__main__":
    asyncio.run(generate())
