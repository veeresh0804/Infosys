
import io
import json
import os
import re
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

try:
    from sarvamai import SarvamAI
except ModuleNotFoundError:  # pragma: no cover - optional backend dependency
    SarvamAI = None

try:
    from huggingface_hub import InferenceClient
except ModuleNotFoundError:  # pragma: no cover - optional backend dependency
    InferenceClient = None


# --------------------------------------------------
# 1. Application setup
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

API_KEY = os.getenv("SARVAM_API_KEY")
HF_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN")
HF_INTENT_MODEL = os.getenv("HF_INTENT_MODEL", "")
HF_NER_MODEL = os.getenv("HF_NER_MODEL", "")

hf_client = (
    InferenceClient(api_key=HF_TOKEN, timeout=20)
    if HF_TOKEN and InferenceClient is not None
    else None
)

print("Hugging Face token configured:", bool(HF_TOKEN))

app = FastAPI(
    title="Multilingual Agricultural Chatbot API",
    description="Backend for the agricultural chatbot project",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# 2. Load agricultural knowledge base
# --------------------------------------------------

KNOWLEDGE_BASE_PATH = BASE_DIR / "knowledge_base.json"

try:
    with open(KNOWLEDGE_BASE_PATH, "r", encoding="utf-8") as file:
        KNOWLEDGE_BASE = json.load(file)

    if not isinstance(KNOWLEDGE_BASE, list):
        raise ValueError("The knowledge base must contain a JSON list.")

    print(f"Loaded {len(KNOWLEDGE_BASE)} agricultural records.")

except (OSError, json.JSONDecodeError, ValueError) as error:
    raise RuntimeError(
        f"Could not load knowledge_base.json: {error}"
    ) from error


# --------------------------------------------------
# 3. Request format
# --------------------------------------------------

class QuestionRequest(BaseModel):
    question: str
    language: str = "unknown"


# --------------------------------------------------
# 4. Intent classification
# --------------------------------------------------


# --------------------------------------------------
# 4. Intent classification
# --------------------------------------------------

INTENT_LABELS = [
    "crop_management",
    "pest_control",
    "soil_health",
    "government_schemes",
    "market_prices",
    "general_agriculture",
]


def classify_intent_fallback(question: str) -> str:
    text = question.lower()

    if any(word in text for word in [
        "pest", "insect", "worm", "bug", "कीट"
    ]):
        return "pest_control"

    if any(word in text for word in [
        "soil", "fertilizer", "fertiliser",
        "nutrient", "soil test", "मिट्टी"
    ]):
        return "soil_health"

    if any(word in text for word in [
        "price", "market", "mandi", "selling",
        "कीमत", "भाव"
    ]):
        return "market_prices"

    if any(word in text for word in [
        "scheme", "subsidy", "government",
        "farmer benefit", "योजना"
    ]):
        return "government_schemes"

    if any(word in text for word in [
        "tomato", "tomatoes", "rice", "paddy",
        "wheat", "cotton", "crop", "farming",
        "cultivation", "irrigation", "water",
        "grow", "plant", "seedling", "पानी"
    ]):
        return "crop_management"

    return "general_agriculture"


def classify_intent(question: str) -> dict:
    """Classify the original transcript using Hugging Face when available."""

    if hf_client and HF_INTENT_MODEL:
        try:
            result = hf_client.zero_shot_classification(
                text=question[:1000],
                candidate_labels=INTENT_LABELS,
                model=HF_INTENT_MODEL,
            )

            return {
                "intent": result.labels[0],
                "confidence": float(result.scores[0]),
                "method": "huggingface",
            }

        except Exception as error:
            print(f"Hugging Face classification unavailable: {error}")

    return {
        "intent": classify_intent_fallback(question),
        "confidence": None,
        "method": "keyword_fallback",
    }


# --------------------------------------------------
# 5. Entity extraction
# --------------------------------------------------

def extract_entities(question: str) -> list:
    text = question.lower()
    entities = []

    crops = {
        "rice": ["rice", "paddy"],
        "wheat": ["wheat"],
        "cotton": ["cotton"],
        "tomato": ["tomato", "tomatoes"],
    }

    for crop_name, words in crops.items():
        if any(re.search(
            r"(?<!\w)" + re.escape(word) + r"(?!\w)", text
        ) for word in words):
            entities.append({
                "type": "crop",
                "value": crop_name,
            })

    if any(word in text for word in [
        "pest", "insect", "worm", "bug", "कीट"
    ]):
        entities.append({
            "type": "problem",
            "value": "pest",
        })

    return entities


# --------------------------------------------------
# 6. Knowledge-base search
# --------------------------------------------------

def search_knowledge_base(question: str, intent: str) -> list:
    text = re.sub(r"[^\w\s-]", " ", question.lower())
    text = re.sub(r"\s+", " ", text).strip()

    matches = []

    for record in KNOWLEDGE_BASE:
        score = 0
        keywords = record.get("keywords", [])

        for keyword in keywords:
            keyword = keyword.lower().strip()

            if not keyword:
                continue

            pattern = (
                r"(?<!\w)" + re.escape(keyword) + r"(?!\w)"
            )

            if re.search(pattern, text):
                score += 2

        # Also match the record's question and crop field.
        record_question = record.get("question", "").lower()
        crop = record.get("crop", "").lower()

        if crop and crop != "general":
            if re.search(
                r"(?<!\w)" + re.escape(crop) + r"(?!\w)", text
            ):
                score += 2

        if record_question:
            question_words = set(re.findall(r"\w+", record_question))
            input_words = set(re.findall(r"\w+", text))
            score += len(question_words & input_words) * 0.25

        if record.get("category", "") == intent:
            score += 3

        if score > 0:
            matches.append({
                "record": record,
                "score": score,
            })

    matches.sort(key=lambda item: item["score"], reverse=True)
    return matches[:3]


# --------------------------------------------------
# 7. Language detection and translation
# --------------------------------------------------

SUPPORTED_LANGUAGES = {
    "en-IN",
    "hi-IN",
    "kn-IN",
    "te-IN",
    "ta-IN",
}


def translate_text(
    text: str,
    source_language: str,
    target_language: str,
) -> dict:
    if source_language == target_language:
        return {
            "translated_text": text,
            "source_language_code": source_language,
        }

    if not API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Sarvam API key is not configured.",
        )

    if SarvamAI is None:
        raise HTTPException(
            status_code=500,
            detail="Sarvam AI SDK is not installed in this environment.",
        )

    try:
        client = SarvamAI(api_subscription_key=API_KEY)

        result = client.text.translate(
            input=text[:1000],
            source_language_code=source_language,
            target_language_code=target_language,
            model="mayura:v1",
        )

        return {
            "translated_text": result.translated_text,
            "source_language_code": getattr(
                result, "source_language_code", source_language
            ),
        }

    except Exception as error:
        print(f"Translation error: {error}")

        raise HTTPException(
            status_code=502,
            detail="Translation failed. Check the backend terminal.",
        ) from error


# --------------------------------------------------
# 8. Basic endpoints
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "message": "Agricultural Chatbot API is running!"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "sarvam_api_key_configured": bool(API_KEY),
        "knowledge_base_records": len(KNOWLEDGE_BASE),
    }


# --------------------------------------------------
# 9. Process an agricultural question
# --------------------------------------------------

@app.post("/api/process-question")
def process_question(request: QuestionRequest):
    session_id = str(uuid4())
    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Please enter an agricultural question.",
        )

    pipeline_steps = [{
        "step": "question_received",
        "status": "completed",
        "details": "The question was received successfully.",
    }]

    # Detect language and normalize the question to English.
    translation = translate_text(question, "auto", "en-IN")
    detected_language = translation.get(
        "source_language_code", request.language
    )
    normalized_question = translation["translated_text"]

    # Avoid unsupported language codes in later translation calls.
    if detected_language not in SUPPORTED_LANGUAGES:
        detected_language = request.language

    pipeline_steps.append({
        "step": "language_detection_translation",
        "status": "completed",
        "details": (
            f"Detected language: {detected_language}. "
            "Question translated into English."
        ),
    })


    classification = classify_intent(question)
    intent = classification["intent"]
    intent_confidence = classification["confidence"]
    classification_method = classification["method"]
    entities = extract_entities(normalized_question)

    pipeline_steps.append({
        "step": "intent_classification",
        "status": "completed",
        "details": f"Detected intent: {intent}",
    })

    pipeline_steps.append({
        "step": "entity_extraction",
        "status": "completed",
        "details": f"Extracted {len(entities)} entity/entities.",
    })

    matches = search_knowledge_base(normalized_question, intent)

    retrieved_records = []

    for item in matches:
        record = item["record"]

        retrieved_records.append({
            "id": record.get("id", ""),
            "category": record.get("category", ""),
            "question": record.get("question", ""),
            "answer": record.get("answer", ""),
            "source": record.get("source", ""),
            "source_url": record.get("source_url", ""),
            "score": item["score"],
        })

    # Translate answers back to the detected/requested language.
    if detected_language and detected_language != "en-IN":
        for record in retrieved_records:
            answer_translation = translate_text(
                record["answer"],
                "en-IN",
                detected_language,
            )
            record["answer"] = answer_translation["translated_text"]

    if retrieved_records:
        pipeline_steps.append({
            "step": "knowledge_retrieval",
            "status": "completed",
            "details": (
                f"Found {len(retrieved_records)} relevant "
                "knowledge record(s)."
            ),
        })
        processing_status = "retrieved"
        message = "Relevant agricultural information was found."
    else:
        pipeline_steps.append({
            "step": "knowledge_retrieval",
            "status": "no_match",
            "details": "No matching records were found.",
        })
        processing_status = "no_match"
        message = "No matching knowledge-base records were found."

    return {
        "session_id": session_id,
        "original_question": question,
        "detected_language": detected_language,
        "normalized_question": normalized_question,
        "intent": intent,
        "intent_confidence": intent_confidence,
        "classification_method": classification_method,
        "entities": entities,
        "retrieved_records": retrieved_records,
        "pipeline_steps": pipeline_steps,
        "processing_status": processing_status,
        "message": message,
    }


# --------------------------------------------------
# 10. Speech-to-text
# --------------------------------------------------

@app.post("/api/speech-to-text")
def speech_to_text(audio: UploadFile = File(...)):
    if not API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Sarvam API key is not configured in backend/.env.",
        )

    if SarvamAI is None:
        raise HTTPException(
            status_code=500,
            detail="Sarvam AI SDK is not installed in this environment.",
        )

    try:
        client = SarvamAI(api_subscription_key=API_KEY)

        result = client.speech_to_text.transcribe(
            file=audio.file,
            model="saaras:v3",
            language_code="unknown",
        )

        return {
            "transcript": result.transcript,
            "language_code": getattr(result, "language_code", None),
            "request_id": getattr(result, "request_id", None),
        }

    except Exception as error:
        print(f"Speech transcription error: {error}")

        raise HTTPException(
            status_code=502,
            detail="Speech transcription failed. Check the backend terminal.",
        ) from error

    finally:
        audio.file.close()


# --------------------------------------------------
# 11. Text-to-speech
# --------------------------------------------------

TTS_SPEAKERS = {
    "en-IN": "simran",
    "hi-IN": "simran",
    "kn-IN": "simran",
    "te-IN": "simran",
    "ta-IN": "simran",
}


@app.post("/api/text-to-speech")
def text_to_speech(request: QuestionRequest):
    if not API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Sarvam API key is not configured.",
        )

    if SarvamAI is None:
        raise HTTPException(
            status_code=500,
            detail="Sarvam AI SDK is not installed in this environment.",
        )

    text = request.question.strip()
    language = request.language

    if not text:
        raise HTTPException(
            status_code=400,
            detail="No text was provided for speech generation.",
        )

    if language not in SUPPORTED_LANGUAGES:
        language = "en-IN"

    try:
        client = SarvamAI(api_subscription_key=API_KEY)

        audio_chunks = client.text_to_speech.convert_stream(
            text=text[:3500],
            language_code=language,
            model="bulbul:v3",
            speaker=TTS_SPEAKERS.get(language, "simran"),
            output_audio_codec="mp3",
        )

        audio_bytes = b"".join(audio_chunks)

        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=answer.mp3"
            },
        )

    except Exception as error:
        print(f"Text-to-speech error: {error}")

        raise HTTPException(
            status_code=502,
            detail="Speech generation failed. Check the backend terminal.",
        ) from error
