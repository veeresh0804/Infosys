"""Knowledge-base overview and vector re-indexing for extension workers.

The browser reads checked-in JSON sources directly (read-only); re-indexing is
the only write action and is delegated to ``POST /api/ingestion/reindex``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

try:  # ``streamlit run dashboard/app.py`` puts the dashboard folder on sys.path
    from api_client import AgriApiClient, BackendError
    from ui import empty_state, section_title
except ImportError:  # imported as a package (``dashboard.views.knowledge_base``)
    from dashboard.api_client import AgriApiClient, BackendError
    from dashboard.ui import empty_state, section_title


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = PROJECT_ROOT / "data" / "knowledge_base"
LOCAL_INDEX_PATH = PROJECT_ROOT / "backend" / "data" / "local_vector_index.json"
SOURCE_CONFIG: dict[str, tuple[str, list[str]]] = {
    "ICAR crop guidance": ("icar", ["crop", "season", "source"]),
    "KCC pest FAQs": ("kcc", ["crop", "category", "query", "source"]),
    "Government schemes": ("schemes", ["scheme_name", "category", "portal_url"]),
}


# --------------------------------------------------------------------------- cache
def _read_records(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    """Read a JSON list of objects, recording a friendly error on failure."""
    if not path.exists():
        errors.append(f"{path.name} is missing")
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        errors.append(f"{path.name} could not be read ({exc.__class__.__name__})")
        return []
    if not isinstance(payload, list):
        errors.append(f"{path.name} does not contain a JSON list")
        return []
    return [record for record in payload if isinstance(record, dict)]


def _count_local_chunks(path: Path, errors: list[str]) -> tuple[int, bool]:
    """Count chunks in the local fallback index without loading the vectors."""
    if not path.exists():
        return 0, False
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        errors.append(f"{path.name} could not be read ({exc.__class__.__name__})")
        return 0, True
    if isinstance(payload, list):
        return len(payload), True
    if isinstance(payload, dict):
        for key in ("chunks", "items", "records", "data"):
            if isinstance(payload.get(key), list):
                return len(payload[key]), True
    errors.append(f"{path.name} does not contain a chunk list")
    return 0, True


@st.cache_data(ttl=300, show_spinner=False)
def _load_corpus() -> dict[str, Any]:
    """Load the local corpus overview; cached for five minutes."""
    errors: list[str] = []
    icar = _read_records(CORPUS_DIR / "icar_crop_guidance.json", errors)
    kcc = _read_records(CORPUS_DIR / "kcc_faqs.json", errors)
    schemes = _read_records(CORPUS_DIR / "government_schemes.json", errors)
    index_count, index_exists = _count_local_chunks(LOCAL_INDEX_PATH, errors)
    return {
        "icar": icar, "kcc": kcc, "schemes": schemes,
        "index_count": index_count, "index_exists": index_exists, "errors": errors,
    }


# ------------------------------------------------------------------------- helpers
def _show_backend_error(exc: BackendError, base_url: str) -> None:
    message = str(exc)
    if "uvicorn" not in message.lower():
        message += (
            f"\n\nMake sure the FastAPI backend is running at {base_url}. Start it from "
            "the project root with `python -m uvicorn backend.app.main:app --port 8000`."
        )
    st.error(message)


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ------------------------------------------------------------------ corpus browser
def _render_corpus_browser(corpus: dict[str, Any]) -> None:
    source_label = st.selectbox("Corpus source", list(SOURCE_CONFIG), key="kb_source_select")
    snapshot_key, columns = SOURCE_CONFIG[source_label]
    records = [record for record in corpus.get(snapshot_key, []) if isinstance(record, dict)]
    if not records:
        empty_state(f"No records found in {source_label}. Check the files in data/knowledge_base.")
        return

    display = pd.DataFrame(records).reindex(columns=columns)
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config={
            "crop": "Crop",
            "season": "Season",
            "category": "Category",
            "source": st.column_config.TextColumn("Source", width="large"),
            "query": st.column_config.TextColumn("Farmer query", width="large"),
            "scheme_name": st.column_config.TextColumn("Scheme", width="large"),
            "portal_url": st.column_config.LinkColumn("Portal", display_text="Open ↗"),
        },
    )
    st.caption(f"{len(records)} records available in {source_label}.")

    record_ids = [
        str(record.get("id") or f"{snapshot_key}-record-{index + 1}")
        for index, record in enumerate(records)
    ]
    index_by_id = {record_id: index for index, record_id in enumerate(record_ids)}
    selected_id = st.selectbox("Record ID", record_ids, key=f"kb_record_{snapshot_key}")
    with st.expander("Full record JSON", expanded=False):
        st.json(records[index_by_id[selected_id]])


# ------------------------------------------------------------------------ re-index
def _render_reindex(base_url: str, total_records: int) -> None:
    st.markdown(
        f"""
        <div class="ks-card">
          <div class="ks-eyebrow">Embedding pipeline</div>
          <p style="margin:0;font-size:.88rem;line-height:1.6;color:#374151;">
            Re-chunks and re-embeds every source record in the checked-in corpus —
            <strong>{total_records}</strong> records in total — with the backend's
            configured embedding model.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(
        "Re-indexing needs the backend's embedding model and may take a while. Source JSON "
        "files are never modified; only the vector index is refreshed."
    )

    if st.button(
        "🔄 Re-index knowledge base", type="primary", key="kb_reindex_button", width="stretch"
    ):
        client = AgriApiClient(base_url)
        with st.status("Chunking and embedding corpus...", expanded=True) as status:
            st.write("Parsing ICAR crop guidance, KCC FAQs and government schemes...")
            st.write("Requesting POST /api/ingestion/reindex — this may take a while...")
            try:
                result = client.reindex()
                if not isinstance(result, dict):
                    raise ValueError("The backend returned an unexpected re-index response.")
            except BackendError as exc:
                status.update(label="Re-index failed", state="error")
                _show_backend_error(exc, base_url)
            except Exception as exc:  # defensive: never crash the dashboard
                status.update(label="Re-index failed", state="error")
                st.error(f"Unexpected error during re-indexing: {exc}")
            else:
                documents = _as_int(result.get("documents_ingested"))
                chunks = _as_int(result.get("chunks_created"))
                engine = str(result.get("vector_db_type") or "unknown")
                st.write(f"📚 Documents ingested: **{documents:,}**")
                st.write(f"🧩 Chunks created: **{chunks:,}**")
                st.write(f"🗄️ Vector engine: **{engine}**")
                status.update(label="Re-index complete", state="complete")
                st.session_state["kb_reindex_result"] = result
                _load_corpus.clear()

    stored = st.session_state.get("kb_reindex_result")
    if not isinstance(stored, dict):
        return
    st.markdown("##### Last re-index result")
    result_cols = st.columns(3)
    result_cols[0].metric("Documents ingested", f"{_as_int(stored.get('documents_ingested')):,}", border=True)
    result_cols[1].metric("Chunks created", f"{_as_int(stored.get('chunks_created')):,}", border=True)
    result_cols[2].metric("Vector engine", str(stored.get("vector_db_type") or "unknown"), border=True)
    st.success(str(stored.get("message") or "Knowledge base re-indexed successfully."))


# ------------------------------------------------------------------- public entry
def render_knowledge_base_tab(base_url: str) -> None:
    """Render the corpus overview, browser and re-index controls."""
    section_title(
        "Knowledge base",
        "Curated ICAR, KCC and government-scheme corpus",
        "Local corpus overview plus vector re-indexing through POST /api/ingestion/reindex.",
    )

    corpus = _load_corpus()
    icar, kcc, schemes = corpus["icar"], corpus["kcc"], corpus["schemes"]
    if corpus["errors"]:
        st.warning("Corpus files could not be fully loaded: " + "; ".join(corpus["errors"]))

    overview = st.columns(4)
    overview[0].metric("ICAR crop guides", f"{len(icar):,}", border=True)
    overview[1].metric("KCC FAQ resolutions", f"{len(kcc):,}", border=True)
    overview[2].metric("Government schemes", f"{len(schemes):,}", border=True)
    overview[3].metric(
        "Estimated chunks",
        f"{3 * len(icar) + len(kcc) + len(schemes):,}",
        border=True,
        help="3 chunks per ICAR guide, plus 1 chunk per KCC FAQ and per scheme.",
    )

    index_col, index_note = st.columns([1, 2], vertical_alignment="center")
    with index_col:
        st.metric("Chunks in local fallback index", f"{corpus['index_count']:,}", border=True)
    with index_note:
        if corpus["index_exists"]:
            st.caption(
                "Pinecone or ChromaDB may be the active vector store; this count only reflects "
                "backend/data/local_vector_index.json."
            )
        else:
            st.caption("No local fallback index found — Pinecone or ChromaDB may be active instead.")

    with st.container():
        browser_tab, reindex_tab = st.tabs(["📊 Corpus browser", "🔄 Re-index"])
        with browser_tab:
            _render_corpus_browser(corpus)
        with reindex_tab:
            _render_reindex(base_url, len(icar) + len(kcc) + len(schemes))
