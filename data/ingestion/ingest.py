import os
import sys
import json
import asyncio
import logging
from typing import List, Dict, Any, Tuple

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

def build_knowledge_chunks() -> Tuple[List[Dict[str, Any]], int]:
    """
    Assembles knowledge base chunks with provenance metadata.
    Returns: (chunks_list, total_source_documents_count)
    """
    kb_dir = os.path.join(BASE_DIR, "data", "knowledge_base")
    chunks = []

    # 1. Ingest ICAR Crop Guidance
    icar_file = os.path.join(kb_dir, "icar_crop_guidance.json")
    icar_items = load_json_file(icar_file)
    for crop in icar_items:
        crop_name = crop.get("crop", "Unknown Crop")
        season = crop.get("season", "All Season")
        source = crop.get("source", "ICAR Bulletin")
        provenance = {
            "source_title": crop.get("source_title", source),
            "source_url": crop.get("source_url", "https://icar.org.in"),
            "retrieved_on": crop.get("retrieved_on", "2026-10-19"),
            "verified": crop.get("verified", False),
            "reviewer_note": crop.get("reviewer_note", "")
        }

        # Chunk 1: Agronomy, Soil & Sowing
        chunks.append({
            "id": f"{crop['id']}-soil-sowing",
            "content": f"Crop: {crop_name} ({season})\nSoil & Climate: {crop.get('soil_and_climate')}\nSowing & Spacing: {crop.get('sowing_and_spacing')}",
            "source": source,
            "metadata": {
                "category": "crop_advisory",
                "crop": crop_name,
                "season": season,
                "topic": "soil_sowing",
                **provenance
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
                "topic": "fertilizer_irrigation",
                **provenance
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
                "topic": "weed_harvest",
                **provenance
            }
        })

    # 2. Ingest Kisan Call Centre (KCC) Pest & Disease FAQs
    kcc_file = os.path.join(kb_dir, "kcc_faqs.json")
    kcc_items = load_json_file(kcc_file)
    for faq in kcc_items:
        crop_name = faq.get("crop", "Crop")
        source = faq.get("source", "Kisan Call Centre Advisory")
        provenance = {
            "source_title": faq.get("source_title", source),
            "source_url": faq.get("source_url", "https://agricoop.gov.in"),
            "retrieved_on": faq.get("retrieved_on", "2026-10-19"),
            "verified": faq.get("verified", False),
            "reviewer_note": faq.get("reviewer_note", "")
        }

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
                "topic": "pest_disease_control",
                **provenance
            }
        })

    # 3. Ingest Government Schemes
    scheme_file = os.path.join(kb_dir, "government_schemes.json")
    scheme_items = load_json_file(scheme_file)
    for s in scheme_items:
        source = f"{s.get('scheme_name')} (Official Portal: {s.get('portal_url')})"
        elig = s.get("eligibility", {})
        provenance = {
            "source_title": s.get("source_title", s.get("scheme_name")),
            "source_url": s.get("source_url", s.get("portal_url", "https://agricoop.gov.in")),
            "retrieved_on": s.get("retrieved_on", "2026-10-19"),
            "verified": s.get("verified", True),
            "reviewer_note": s.get("reviewer_note", "")
        }

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
                "topic": "government_schemes",
                **provenance
            }
        })

    total_docs = len(icar_items) + len(kcc_items) + len(scheme_items)
    logger.info(f"Assembled {len(chunks)} chunks from {total_docs} primary documents.")
    return chunks, total_docs

async def run_ingestion() -> Tuple[int, int]:
    """
    Executes full ingestion and indexing.
    Returns: (total_source_documents_count, total_chunks_count)
    """
    logger.info(f"Starting Knowledge Base Ingestion (Vector DB: {settings.VECTOR_DB_TYPE})...")
    chunks, total_docs = build_knowledge_chunks()

    # Always build and persist the local file-backed vector index
    from backend.app.services.rag.vector_store import LocalFallbackVectorStore
    local_store = LocalFallbackVectorStore()
    local_count = await local_store.add_documents(chunks)
    logger.info(f"Successfully saved {local_count} prebuilt chunks from {total_docs} documents.")

    # Also sync into ChromaDB or Pinecone if configured
    if settings.VECTOR_DB_TYPE.lower() == "chromadb":
        from backend.app.services.rag.vector_store import ChromaVectorStore
        chroma = ChromaVectorStore()
        await chroma.add_documents(chunks)
    elif settings.VECTOR_DB_TYPE.lower() == "pinecone" and settings.PINECONE_API_KEY:
        from backend.app.services.rag.vector_store import PineconeVectorStore
        pine = PineconeVectorStore()
        if pine.is_configured:
            await pine.add_documents(chunks)

    return total_docs, local_count

if __name__ == "__main__":
    docs, count = asyncio.run(run_ingestion())
    print(f"Ingestion Complete: {docs} documents, {count} chunks indexed.")
