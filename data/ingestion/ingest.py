import os
import sys
import json
import asyncio
import logging
from typing import List, Dict, Any

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app.services.rag.vector_store import get_vector_store
from backend.app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest")

def load_json_file(file_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_knowledge_chunks() -> List[Dict[str, Any]]:
    kb_dir = os.path.join(BASE_DIR, "data", "knowledge_base")
    chunks = []

    # 1. Ingest ICAR Crop Guidance
    icar_file = os.path.join(kb_dir, "icar_crop_guidance.json")
    icar_items = load_json_file(icar_file)
    for crop in icar_items:
        crop_name = crop.get("crop", "Unknown Crop")
        season = crop.get("season", "All Season")
        source = crop.get("source", "ICAR Bulletin")

        # Chunk 1: Agronomy, Soil & Sowing
        chunks.append({
            "id": f"{crop['id']}-soil-sowing",
            "content": f"Crop: {crop_name} ({season})\nSoil & Climate: {crop.get('soil_and_climate')}\nSowing & Spacing: {crop.get('sowing_and_spacing')}",
            "source": source,
            "metadata": {
                "category": "crop_advisory",
                "crop": crop_name,
                "season": season,
                "topic": "soil_sowing"
            }
        })

        # Chunk 2: Nutrient, NPK & Fertilizer Management
        chunks.append({
            "id": f"{crop['id']}-nutrients",
            "content": f"Crop: {crop_name} Fertilizer & Nutrient Management:\n{crop.get('nutrient_management')}\nWater Management: {crop.get('water_management')}",
            "source": source,
            "metadata": {
                "category": "crop_advisory",
                "crop": crop_name,
                "season": season,
                "topic": "fertilizer_irrigation"
            }
        })

        # Chunk 3: Weed Control & Harvesting
        chunks.append({
            "id": f"{crop['id']}-weeds-harvest",
            "content": f"Crop: {crop_name} Weed Control:\n{crop.get('weed_control')}\nHarvesting & Maturity:\n{crop.get('harvesting')}",
            "source": source,
            "metadata": {
                "category": "crop_advisory",
                "crop": crop_name,
                "season": season,
                "topic": "weed_harvest"
            }
        })

    # 2. Ingest Kisan Call Centre (KCC) Pest & Disease FAQs
    kcc_file = os.path.join(kb_dir, "kcc_faqs.json")
    kcc_items = load_json_file(kcc_file)
    for faq in kcc_items:
        crop_name = faq.get("crop", "Crop")
        source = faq.get("source", "Kisan Call Centre Advisory")

        chunks.append({
            "id": faq["id"],
            "content": (
                f"Crop: {crop_name} | Problem: {faq.get('query')}\n"
                f"Hindi Query: {faq.get('query_hi')}\n"
                f"Kannada Query: {faq.get('query_kn')}\n"
                f"Symptoms: {faq.get('symptoms')}\n"
                f"Recommended Management & Control: {faq.get('management')}\n"
                f"Preventive Measures: {faq.get('preventive_measures')}"
            ),
            "source": source,
            "metadata": {
                "category": "pest_control",
                "crop": crop_name,
                "topic": "pest_disease_control"
            }
        })

    # 3. Ingest Government Schemes
    scheme_file = os.path.join(kb_dir, "government_schemes.json")
    scheme_items = load_json_file(scheme_file)
    for s in scheme_items:
        source = f"{s.get('scheme_name')} (Official Portal: {s.get('portal_url')})"
        elig = s.get("eligibility", {})

        chunks.append({
            "id": s["id"],
            "content": (
                f"Scheme Name: {s.get('scheme_name')}\n"
                f"Summary: {s.get('summary')}\n"
                f"Eligibility Target Group: {elig.get('target_group')}\n"
                f"Exclusions: {'; '.join(elig.get('exclusions', []))}\n"
                f"Documents Required: {', '.join(elig.get('documents_required', []))}\n"
                f"Benefits: {s.get('benefits')}\n"
                f"Application Process: {s.get('application_process')}"
            ),
            "source": source,
            "metadata": {
                "category": "scheme_lookup",
                "scheme": s.get("scheme_name"),
                "topic": "government_schemes"
            }
        })

    logger.info(f"Assembled {len(chunks)} chunks from ICAR, KCC, and Government Schemes.")
    return chunks

async def run_ingestion() -> int:
    logger.info(f"Starting Knowledge Base Ingestion (Vector DB: {settings.VECTOR_DB_TYPE})...")
    chunks = build_knowledge_chunks()

    # 1. Always build and persist the local file-backed vector index for zero-cost / offline deployment
    from backend.app.services.rag.vector_store import LocalFallbackVectorStore
    local_store = LocalFallbackVectorStore()
    local_count = await local_store.add_documents(chunks)
    logger.info(f"Successfully saved {local_count} prebuilt chunks to local vector store (local_vector_index.json).")

    # 2. Also index into the configured vector store (if not local)
    vector_store = get_vector_store()
    if not isinstance(vector_store, LocalFallbackVectorStore):
        remote_count = await vector_store.add_documents(chunks)
        logger.info(f"Successfully indexed {remote_count} document chunks into {settings.VECTOR_DB_TYPE}.")
        return remote_count

    return local_count

if __name__ == "__main__":
    asyncio.run(run_ingestion())
