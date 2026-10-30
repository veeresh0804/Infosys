"""KisanSahayak extension-worker dashboard.

Run from the repository root: ``streamlit run dashboard/app.py``

A thin presentation layer over the same FastAPI REST API used by the
farmer-facing app; it never touches SQLite or the vector store directly.
"""

from __future__ import annotations

import base64
import binascii
import re
from collections import Counter
from datetime import datetime
from typing import Any, Optional

import pandas as pd
import streamlit as st

from api_client import AgriApiClient, BackendError, DEFAULT_BASE_URL
from ui import (
    LANG_LABELS, LANGUAGES, SAMPLE_QUERIES, confidence_kind, empty_state, esc,
    fmt_pct, inject_css, pill, render_live_data_panel, section_title, status_html,
)
from views.knowledge_base import render_knowledge_base_tab
from views.live_data import render_live_data_tab
from views.session_view import render_session_tab

# This must be the first Streamlit call after imports.
st.set_page_config(
    page_title="KisanSahayak | Extension Dashboard",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

SAMPLE_PLACEHOLDER = "— choose a sample —"
DEFAULT_SESSION_ID = "dashboard-session-1"
MAX_REVIEW_CARDS = 10


# ---------------------------------------------------------------------------
# Cached fetchers. Exceptions propagate to the UI-level handlers below.
# ---------------------------------------------------------------------------
@st.cache_data(ttl=20, show_spinner=False)
def cached_status(base_url: str) -> dict[str, Any]:
    return AgriApiClient(base_url).status()


@st.cache_data(ttl=30, show_spinner=False)
def cached_flagged_reviews(base_url: str) -> list[dict[str, Any]]:
    return AgriApiClient(base_url).flagged_reviews(limit=50)


@st.cache_data(ttl=45, show_spinner=False)
def cached_session(base_url: str, session_id: str) -> dict[str, Any]:
    return AgriApiClient(base_url).get_session(session_id)


# ---------------------------------------------------------------------------
# Parsing and formatting helpers
# ---------------------------------------------------------------------------
def _active_config(status: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(status, dict):
        return {}
    config = status.get("active_configuration") or status.get("active_engines")
    return config if isinstance(config, dict) else {}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_percent(value: Any) -> float:
    return round(max(0.0, min(1.0, _as_float(value))) * 100, 1)


def _shorten(value: Any, limit: int = 42) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


_GEMINI_LABEL = re.compile(
    r"gemini[-_ ]?(\d+(?:\.\d+)?)[-_ ]?(flash|pro|ultra|thinking)?", re.IGNORECASE
)


def _pretty_vector(value: Any) -> str:
    """Turn raw vector-store identifiers into a short human label."""
    text = " ".join(str(value or "").split())
    lowered = text.lower()
    if not text:
        return "-"
    if lowered.startswith("local"):
        chunks = re.search(r"(\d+)\s+chunks?", lowered)
        return f"Local · {chunks.group(1)} chunks" if chunks else "Local index"
    if "pinecone" in lowered:
        return "Pinecone"
    if "chroma" in lowered:
        return "ChromaDB"
    return text.split(" (", 1)[0]


def _pretty_model(value: Any) -> str:
    """Turn raw provider/model slugs into a readable engine name."""
    text = " ".join(str(value or "").split())
    if not text:
        return "-"
    match = _GEMINI_LABEL.search(text)
    if match:
        tier = f" {match.group(2).title()}" if match.group(2) else ""
        return f"Gemini {match.group(1)}{tier}"
    if "mock" in text.lower() or "fallback" in text.lower():
        return "Mock fallback"
    cleaned = " ".join(text.replace("_", " ").replace("-", " ").split())
    return cleaned[:1].upper() + cleaned[1:] if cleaned else "-"


def _engine_labels(config: dict[str, Any]) -> tuple[str, str]:
    """Return (vector store, LLM provider) for the status caption and KPI."""
    # The API calls these ``vector_store`` and ``llm_primary``.
    vector = _pretty_vector(config.get("vector_db") or config.get("vector_store"))
    llm = config.get("llm_provider") or config.get("llm_primary")
    if not llm or str(llm).lower().startswith("unconfigured"):
        llm = config.get("llm_fallback") or config.get("llm_secondary") or "-"
    return vector, _shorten(_pretty_model(llm), 38)


def _fmt_timestamp(value: Any) -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime(
            "%d %b %Y · %H:%M"
        )
    except ValueError:
        return str(value).replace("T", " ")[:16]


def _normalise_review(raw: dict[str, Any]) -> dict[str, Any]:
    chunks = raw.get("retrieved_chunks")
    return {
        "session_id": str(raw.get("session_id") or "—"),
        "time": _fmt_timestamp(raw.get("created_at")),
        "language": str(raw.get("detected_language") or "en"),
        "intent": str(raw.get("detected_intent") or "unknown"),
        "sub_agent": str(raw.get("sub_agent") or "—"),
        "confidence": max(0.0, min(1.0, _as_float(raw.get("confidence_score")))),
        "original_query": str(raw.get("original_query") or ""),
        "canonical_query": str(raw.get("canonical_query") or ""),
        "response_text": str(raw.get("response_text") or ""),
        "flag_reason": str(raw.get("flag_reason") or ""),
        "chunks": chunks if isinstance(chunks, list) else [],
    }


def _review_rows(reviews: Any) -> list[dict[str, Any]]:
    if not isinstance(reviews, list):
        return []
    return [_normalise_review(review) for review in reviews if isinstance(review, dict)]


def _top_sub_agent(reviews: list[dict[str, Any]]) -> str:
    counts = Counter(
        review["sub_agent"] for review in reviews if review["sub_agent"] not in {"", "—"}
    )
    return counts.most_common(1)[0][0] if counts else "—"


def _backend_hint(base_url: str) -> str:
    return (
        f"Start the FastAPI backend at {base_url} "
        "(python -m uvicorn backend.app.main:app --port 8000), then re-check."
    )


def _render_view(renderer: Any, *args: Any) -> None:
    """Guard extension tabs so an unreachable backend never crashes the app."""
    try:
        renderer(*args)
    except BackendError as exc:
        st.error(f"Could not load this section: {exc}")
    except Exception as exc:  # a view bug should never take down the whole page
        st.error(f"This section failed unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def render_sidebar() -> tuple[str, Optional[dict[str, Any]], Optional[str]]:
    """Render controls and return (base_url, status payload, status error)."""
    with st.sidebar:
        st.markdown("### 🌾 KisanSahayak")
        st.caption("AI Smart Farming Assistant · Extension Dashboard")
        raw_base_url = st.text_input(
            "Backend API URL", value=DEFAULT_BASE_URL, key="api_base_url",
            help="The dashboard reads the public FastAPI endpoints only.",
        )
        base_url = str(raw_base_url or "").strip().rstrip("/") or DEFAULT_BASE_URL

        try:
            status_data: Optional[dict[str, Any]] = cached_status(base_url)
            status_error: Optional[str] = None
        except BackendError as exc:
            status_data, status_error = None, str(exc)
        except Exception as exc:  # a malformed response must not crash the app
            status_data, status_error = None, f"Unexpected backend error: {exc}"

        if isinstance(status_data, dict):
            vector_label, llm_label = _engine_labels(_active_config(status_data))
            st.markdown(status_html(True, "Backend online"), unsafe_allow_html=True)
            st.caption(f"Vector DB: {vector_label}")
            st.caption(f"LLM provider: {llm_label}")
        else:
            st.markdown(status_html(False, "Backend offline"), unsafe_allow_html=True)
            st.caption("Could not reach the REST API. Start the backend, then re-check.")

        if st.button("🔄 Re-check connection", key="recheck_connection", width="stretch"):
            cached_status.clear()
            st.rerun()

        st.divider()
        st.selectbox(
            "Answer language", options=list(LANGUAGES.keys()),
            format_func=lambda code: LANGUAGES[code], key="query_lang",
        )
        st.text_input("Session ID", value=DEFAULT_SESSION_ID, key="session_id")
        st.link_button("🌱 Farmer voice UI", "http://localhost:3000", width="stretch")
        st.link_button("📘 API docs", f"{base_url}/docs", width="stretch")
        st.caption(
            "Works with mock providers when API keys are absent — every answer "
            "remains traceable through the same pipeline."
        )

    return base_url, status_data, status_error


# ---------------------------------------------------------------------------
# Header and KPI row
# ---------------------------------------------------------------------------
def render_header(online: bool) -> None:
    now_text = datetime.now().astimezone().strftime("%A, %d %b %Y · %I:%M %p %Z")
    st.markdown(
        f'<div class="ks-hero"><div class="ks-hero-row">'
        f'<div style="flex:1 1 520px;"><h1>🌾 KisanSahayak Extension Dashboard</h1>'
        f'<p>Multilingual farmer queries · RAG telemetry · human review queue</p></div>'
        f'<div style="text-align:right;">'
        f'{status_html(online, "Backend online" if online else "Backend offline")}'
        f'<div style="color:#bbf7d0;font-size:.76rem;margin-top:7px;">{esc(now_text)}</div>'
        f"</div></div></div>",
        unsafe_allow_html=True,
    )


def render_kpis(
    online: bool, status_data: Optional[dict[str, Any]], status_error: Optional[str],
    reviews: list[dict[str, Any]], flagged_error: Optional[str],
) -> None:
    """Summary row; status and flagged reviews are fetched once by the caller."""
    normalised = _review_rows(reviews)
    if flagged_error:
        flagged_value = avg_value = "—"
    else:
        flagged_value = str(len(normalised))
        avg_value = (
            fmt_pct(sum(review["confidence"] for review in normalised) / len(normalised))
            if normalised else "—"
        )
    vector_label, llm_label = (
        _engine_labels(_active_config(status_data))
        if isinstance(status_data, dict) else ("—", "—")
    )
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Backend", "Online" if online else "Offline", border=True,
                help=status_error or "Fetched from GET / on the configured backend.")
    col2.metric("Flagged reviews", flagged_value, border=True,
                help=flagged_error or "Low-confidence answers waiting for a human.")
    col3.metric("Avg flagged confidence", avg_value, border=True,
                help="Mean quality score of the current review queue.")
    col4.metric("Vector DB / LLM", vector_label, delta=llm_label, delta_color="off",
                border=True, help="Active retrieval backend and language-model provider.")


# ---------------------------------------------------------------------------
# Ask-a-question tab
# ---------------------------------------------------------------------------
def render_query_log() -> None:
    """Compact, session-local history of questions asked from this browser."""
    entries = st.session_state.get("query_log") or []
    if not isinstance(entries, list):
        entries = []
    entries = [entry for entry in entries[-10:] if isinstance(entry, dict)]
    with st.expander("🧾 Query log · last 10", expanded=False):
        if not entries:
            st.caption("No questions asked in this dashboard session yet.")
        else:
            frame = pd.DataFrame([{
                "Time": e.get("time", ""),
                "Question": e.get("question", ""),
                "Intent": e.get("intent", ""),
                "Confidence %": round(_as_float(e.get("confidence")) * 100),
            } for e in entries])
            st.dataframe(
                frame, width="stretch", hide_index=True,
                column_config={"Confidence %": st.column_config.NumberColumn(
                    "Confidence %", format="%.0f%%"
                )},
            )
        if st.button("Clear log", key="clear_query_log"):
            st.session_state["query_log"] = []
            st.rerun()


def _render_tts(res: dict[str, Any], base_url: str) -> None:
    """Synthesize and cache a voice version of the latest answer."""
    language = str(res.get("detected_language") or "en").lower().split("-")[0]
    if language not in LANGUAGES:
        language = "en"
    speech_text = (
        res.get("short_answer_translated") or res.get("answer_translated") or ""
    ).strip()
    if st.button("🔊 Synthesize voice answer", key="tts_synthesize"):
        if not speech_text:
            st.warning("There is no answer text to synthesize.")
        else:
            st.session_state.pop("tts_audio", None)
            st.session_state.pop("tts_engine", None)
            try:
                with st.spinner("Generating voice answer…"):
                    payload = AgriApiClient(base_url).synthesize_speech(
                        speech_text, language
                    )
                if not isinstance(payload, dict):
                    raise BackendError("The speech endpoint returned an unexpected payload.")
                encoded = str(payload.get("audio_base64") or "")
                if not encoded:
                    raise BackendError("The speech endpoint returned no audio data.")
                audio_bytes = base64.b64decode(encoded)
                if not audio_bytes:
                    raise BackendError("The speech endpoint returned empty audio data.")
                st.session_state["tts_audio"] = audio_bytes
                st.session_state["tts_engine"] = str(
                    payload.get("engine_used") or "unknown"
                )
                st.session_state["tts_format"] = str(payload.get("format") or "wav")
            except (BackendError, ValueError, TypeError, binascii.Error) as exc:
                st.error(f"Voice synthesis failed: {exc}")

    audio = st.session_state.get("tts_audio")
    if isinstance(audio, (bytes, bytearray)) and audio:
        audio_format = str(st.session_state.get("tts_format") or "wav").lower()
        if audio_format not in {"wav", "mp3", "ogg"}:
            audio_format = "wav"
        st.audio(bytes(audio), format=f"audio/{audio_format}")
        st.caption(
            f"Voice engine: {st.session_state.get('tts_engine', 'unknown')} · "
            f"{len(audio):,} bytes"
        )


def render_query_result(res: dict[str, Any], base_url: str) -> None:
    """Render the persisted response of the last successful query."""
    intent = str(res.get("intent") or "unknown")
    language_code = str(res.get("detected_language") or "en")
    language_label = LANG_LABELS.get(language_code, language_code)
    confidence = max(0.0, min(1.0, _as_float(res.get("confidence_score"))))
    is_low = bool(res.get("is_low_confidence"))
    metric_cols = st.columns(4)
    metric_cols[0].metric(
        "Intent", f"{intent} · {_as_float(res.get('intent_confidence')):.0%}", border=True
    )
    metric_cols[1].metric("Sub-agent", str(res.get("sub_agent") or "—"), border=True)
    metric_cols[2].metric("Detected language", language_label, border=True)
    metric_cols[3].metric(
        "Confidence", fmt_pct(confidence),
        delta="Flagged for review" if is_low else "Above threshold",
        delta_color="inverse" if is_low else "normal", border=True,
    )
    if is_low:
        st.warning(
            f"Flagged for review — {res.get('flag_reason') or 'below confidence threshold'}"
        )
    if res.get("is_fallback"):
        st.info("Answer used a fallback / mock data source.")

    st.markdown(
        f'<div class="ks-answer"><div class="ks-eyebrow">Answer · '
        f'{esc(language_label)}</div><div class="ks-answer-text">'
        f"{esc(res.get('answer_translated') or '')}</div></div>",
        unsafe_allow_html=True,
    )
    short_answer = str(res.get("short_answer_translated") or "")
    st.caption(f"Short answer: {short_answer or '—'}")
    with st.expander("Show canonical English answer", expanded=False):
        st.write(res.get("answer_canonical") or "No canonical answer returned.")

    entities = res.get("entities") or []
    if isinstance(entities, list) and entities:
        entity_html = "".join(
            pill(f"{e.get('label', 'entity')}: {e.get('text', '')}", "blue")
            for e in entities if isinstance(e, dict)
        )
        st.markdown('<div class="ks-eyebrow">Detected entities</div>' + entity_html,
                    unsafe_allow_html=True)
    else:
        st.caption("No agricultural entities were extracted from this query.")

    _render_tts(res, base_url)
    live_data = res.get("live_data")
    render_live_data_panel(live_data if isinstance(live_data, dict) else None)
    st.markdown("##### Retrieved knowledge-base chunks")
    chunks = res.get("retrieved_chunks") or []
    if not isinstance(chunks, list):
        chunks = []
    if chunks:
        for chunk in chunks[:5]:
            if not isinstance(chunk, dict):
                continue
            source = str(chunk.get("source") or "Unknown source")
            score = max(0.0, min(1.0, _as_float(chunk.get("similarity_score"))))
            with st.expander(f"{source} · similarity {score:.0%}", expanded=False):
                st.progress(score)
                st.write(chunk.get("content") or "No content returned for this chunk.")
    else:
        st.caption("No vector chunks — query was handled by a live-data sub-agent.")
    render_query_log()


def render_session_context(base_url: str, session_id: str) -> None:
    """Right-hand farmer profile card inside the Ask tab."""
    st.markdown("### Session context")
    try:
        session = cached_session(base_url, session_id)
    except BackendError as exc:
        st.info(f"Session context unavailable — {_backend_hint(base_url)}")
        with st.expander("Connection details", expanded=False):
            st.code(str(exc), language=None)
        return
    except Exception as exc:
        st.info("Session context could not be loaded. Check the backend URL.")
        with st.expander("Error details", expanded=False):
            st.code(str(exc), language=None)
        return
    if not isinstance(session, dict):
        st.caption("The backend returned an unexpected session payload.")
        return

    language_code = str(session.get("preferred_language") or "en")
    st.metric("Preferred language", LANG_LABELS.get(language_code, language_code),
              border=True)
    location = " · ".join(
        part for part in [session.get("state"), session.get("district")] if part
    )
    st.caption(f"📍 {location or 'State / district not recorded'}")
    acres = session.get("landholding_acres")
    st.metric("Landholding", f"{_as_float(acres):g} acres" if acres is not None else "—",
              border=True)
    crops = session.get("crops_grown") or []
    if crops:
        st.markdown('<div class="ks-eyebrow">Crops grown</div>'
                    + "".join(pill(str(crop), "green") for crop in crops),
                    unsafe_allow_html=True)
    else:
        st.caption("No crops recorded for this farmer yet.")


def render_pipeline_card() -> None:
    """Explain the seven-stage pipeline for extension workers."""
    st.markdown(
        '<div class="ks-card"><div class="ks-eyebrow">Under the hood · 7 stages</div>'
        '<ol style="margin:8px 0 0 18px;padding:0;color:#374151;font-size:.83rem;'
        'line-height:1.8;">'
        "<li><strong>STT</strong> — speech-to-text via Sarvam / Whisper</li>"
        "<li><strong>Translate</strong> — Indic query to canonical English</li>"
        "<li><strong>Intent / NER</strong> — route the query and extract entities</li>"
        "<li><strong>Agent</strong> — RAG chunks or verified live data</li>"
        "<li><strong>Quality score</strong> — similarity, intent and entity coverage</li>"
        "<li><strong>Review flag</strong> — low confidence lands in this dashboard</li>"
        "<li><strong>Back-translate</strong> — final answer in the farmer's language</li>"
        "</ol></div>",
        unsafe_allow_html=True,
    )


def render_ask_tab(base_url: str, session_id: str) -> None:
    """Farmer question entry, pipeline result and session context."""
    section_title("Farmer Q&A", "Ask the assistant",
                  "The same multilingual RAG pipeline used by the farmer voice UI.")
    left, right = st.columns([2.2, 1])
    with left:
        # Apply a sample before the text area exists so the widget picks up the
        # new draft on the rerun. Never mutate a widget key after creation.
        chosen_sample = st.selectbox(
            "Quick sample question",
            [SAMPLE_PLACEHOLDER] + [sample["label"] for sample in SAMPLE_QUERIES],
            key="sample_pick",
        )
        if chosen_sample == SAMPLE_PLACEHOLDER:
            st.session_state["_sample_applied"] = None
        elif chosen_sample != st.session_state.get("_sample_applied"):
            sample = next(
                (item for item in SAMPLE_QUERIES if item["label"] == chosen_sample), None
            )
            if sample:
                st.session_state["draft_query"] = sample["text"]
                st.session_state["_sample_applied"] = chosen_sample
                st.rerun()

        with st.form("ask_form"):
            question = st.text_area(
                "Farmer question (Hindi, Kannada or English)",
                key="draft_query", height=110,
                placeholder=(
                    "e.g. टमाटर के पत्तों पर पीले धब्बे हैं — क्या छिड़काव करूँ? "
                    "/ ಭತ್ತದಲ್ಲಿ ಕಾಂಡ ಕೊರೆಯುವ ಹುಳು ಬಂದಿದೆ, ಏನು ಮಾಡಬೇಕು?"
                ),
            )
            submitted = st.form_submit_button(
                "🚀 Ask the assistant", type="primary", width="stretch"
            )

        if submitted:
            text = (question or "").strip()
            if not text:
                st.warning("Enter a farmer question before asking the assistant.")
            elif not session_id:
                st.warning("Enter a session ID in the sidebar before asking.")
            else:
                try:
                    with st.spinner("Routing through translation, RAG and quality scoring…"):
                        response = AgriApiClient(base_url).query(
                            text, st.session_state.get("query_lang", "hi"), session_id
                        )
                    if not isinstance(response, dict):
                        raise BackendError("The backend returned an unexpected response.")
                    st.session_state["last_response"] = response
                    st.session_state.pop("tts_audio", None)
                    st.session_state.pop("tts_engine", None)
                    log = st.session_state.setdefault("query_log", [])
                    if not isinstance(log, list):
                        log = []
                    log.append({
                        "time": datetime.now().strftime("%H:%M:%S"),
                        "question": text,
                        "intent": str(response.get("intent") or "unknown"),
                        "confidence": _as_float(response.get("confidence_score")),
                    })
                    st.session_state["query_log"] = log[-50:]
                except BackendError as exc:
                    st.error(f"Could not reach the assistant: {exc}")
                    st.caption("Check the backend URL in the sidebar, then try again.")
                except Exception as exc:
                    st.error(f"The query failed unexpectedly: {exc}")

        last_response = st.session_state.get("last_response")
        if isinstance(last_response, dict):
            st.divider()
            render_query_result(last_response, base_url)
        else:
            empty_state("Ask a question above to see the answer, confidence score, "
                        "retrieved chunks and voice playback.")
    with right:
        render_session_context(base_url, session_id)
        render_pipeline_card()


# ---------------------------------------------------------------------------
# Review queue tab
# ---------------------------------------------------------------------------
def render_review_queue(reviews: list[dict[str, Any]], base_url: str) -> None:
    """Human-in-the-loop queue of low-confidence answers."""
    heading, refresh_col = st.columns([4, 1])
    with heading:
        section_title("Human in the loop", "Flagged review queue",
                      f"Low-confidence answers from {base_url}.")
    with refresh_col:
        if st.button("🔄 Refresh", key="refresh_queue", width="stretch"):
            cached_flagged_reviews.clear()
            st.rerun()

    normalised = _review_rows(reviews)
    if not normalised:
        st.success("Queue clear — no low-confidence answers need review.")
        empty_state("When an answer falls below the confidence threshold it will "
                    "appear here with its retrieved sources and flag reason.")
        return

    avg_confidence = sum(r["confidence"] for r in normalised) / len(normalised)
    below_half = sum(1 for r in normalised if r["confidence"] < 0.5)
    metric_cols = st.columns(4)
    metric_cols[0].metric("Total flagged", str(len(normalised)), border=True)
    metric_cols[1].metric("Avg confidence", fmt_pct(avg_confidence), border=True)
    metric_cols[2].metric("Below 50%", str(below_half), border=True)
    metric_cols[3].metric("Top sub-agent", _top_sub_agent(normalised), border=True)

    # Filters
    filter_cols = st.columns([1, 1, 1.4, 1.4])
    agent_options = sorted(
        {r["sub_agent"] for r in normalised if r["sub_agent"] != "—"}
    )
    language_options = sorted({r["language"] for r in normalised})
    selected_agents = filter_cols[0].multiselect(
        "Sub-agent", agent_options, key="review_agents"
    )
    selected_languages = filter_cols[1].multiselect(
        "Detected language", language_options,
        format_func=lambda code: LANG_LABELS.get(code, code), key="review_languages",
    )
    confidence_range = filter_cols[2].slider(
        "Confidence range", 0.0, 1.0, (0.0, 1.0), 0.01
    )
    search_text = filter_cols[3].text_input(
        "Search", key="review_search", placeholder="Question, answer or flag reason…"
    )
    search_text = (search_text or "").strip().casefold()

    filtered: list[dict[str, Any]] = []
    for review in normalised:
        if selected_agents and review["sub_agent"] not in selected_agents:
            continue
        if selected_languages and review["language"] not in selected_languages:
            continue
        if not (confidence_range[0] <= review["confidence"] <= confidence_range[1]):
            continue
        if search_text:
            haystack = " ".join([
                review["original_query"], review["canonical_query"],
                review["response_text"], review["flag_reason"],
            ]).casefold()
            if search_text not in haystack:
                continue
        filtered.append(review)

    if not filtered:
        st.info("No flagged reviews match the current filters.")
        return

    # Table + CSV
    table = pd.DataFrame([{
        "Time": r["time"],
        "Language": LANG_LABELS.get(r["language"], r["language"]),
        "Intent": r["intent"],
        "Sub-agent": r["sub_agent"],
        "Confidence %": _as_percent(r["confidence"]),
        "Original query": r["original_query"],
        "Flag reason": r["flag_reason"] or "—",
    } for r in filtered])
    st.dataframe(
        table, width="stretch", hide_index=True,
        column_config={"Confidence %": st.column_config.NumberColumn(
            "Confidence %", format="%.1f%%"
        )},
    )
    st.download_button(
        "⬇️ Download queue as CSV",
        data=table.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"kisansahayak_flagged_reviews_{datetime.now():%Y%m%d}.csv",
        mime="text/csv", width="stretch",
    )

    # Detail cards
    st.markdown("#### Review details")
    for review in filtered[:MAX_REVIEW_CARDS]:
        score = review["confidence"]
        with st.expander(
            f"{score:.0%} · {review['sub_agent']} · "
            f"{_shorten(review['original_query'], 60)}",
            expanded=False,
        ):
            detail_cols = st.columns(4)
            detail_cols[0].metric("Confidence", fmt_pct(score))
            detail_cols[1].metric("Intent", review["intent"])
            detail_cols[2].metric(
                "Language", LANG_LABELS.get(review["language"], review["language"])
            )
            detail_cols[3].metric("Flagged at", review["time"])
            st.markdown(
                pill(f"Confidence {fmt_pct(score)}",
                     confidence_kind(score, score < 0.5)),
                unsafe_allow_html=True,
            )
            st.markdown("**Original query**")
            st.write(review["original_query"] or "—")
            if (review["canonical_query"]
                    and review["canonical_query"] != review["original_query"]):
                st.markdown("**Canonical English query**")
                st.write(review["canonical_query"])
            st.markdown(
                f'<div class="ks-answer"><div class="ks-eyebrow">'
                f'Assistant response</div><div class="ks-answer-text">'
                f"{esc(review['response_text'] or '—')}</div></div>",
                unsafe_allow_html=True,
            )
            st.markdown("**Flag reason**")
            st.write(review["flag_reason"] or "Not supplied by the backend.")
            sources = []
            for chunk in review["chunks"]:
                if isinstance(chunk, dict):
                    source = str(chunk.get("source") or "").strip()
                    if source and source not in sources:
                        sources.append(source)
            if sources:
                st.markdown('<div class="ks-eyebrow">Chunk sources</div>'
                            + "".join(pill(source, "gray") for source in sources),
                            unsafe_allow_html=True)
            else:
                st.caption("No retrieved chunks recorded for this review.")
            st.caption(f"Session: {review['session_id']}")

    if len(filtered) > MAX_REVIEW_CARDS:
        st.caption(f"Showing the first {MAX_REVIEW_CARDS} of {len(filtered)} matching "
                   "reviews. Download the CSV for the full queue.")


# ---------------------------------------------------------------------------
# Page composition
# ---------------------------------------------------------------------------
def main() -> None:
    base_url, status_data, status_error = render_sidebar()
    online = isinstance(status_data, dict)

    # Fetch the review queue once and share it with the KPI row and tab 2.
    try:
        raw_reviews = cached_flagged_reviews(base_url) or []
        if not isinstance(raw_reviews, list):
            raise BackendError("The flagged-reviews endpoint returned an unexpected payload.")
        flagged_reviews = [r for r in raw_reviews if isinstance(r, dict)]
        flagged_error: Optional[str] = None
    except BackendError as exc:
        flagged_reviews, flagged_error = [], str(exc)
    except Exception as exc:
        flagged_reviews, flagged_error = [], f"Unexpected review-queue error: {exc}"

    session_id = (
        str(st.session_state.get("session_id") or "").strip() or DEFAULT_SESSION_ID
    )
    render_header(online)
    render_kpis(online, status_data, status_error, flagged_reviews, flagged_error)

    tabs = st.tabs([
        "💬 Ask a question", "🚩 Review queue", "📡 Live data",
        "📚 Knowledge base", "🧑‍🌾 Farmer session",
    ])
    with tabs[0]:
        render_ask_tab(base_url, session_id)
    with tabs[1]:
        if flagged_error:
            st.error(f"Could not load the review queue: {flagged_error}")
            st.caption(_backend_hint(base_url))
            if st.button("🔄 Refresh queue", key="refresh_queue_error"):
                cached_flagged_reviews.clear()
                st.rerun()
        else:
            render_review_queue(flagged_reviews, base_url)
    with tabs[2]:
        _render_view(render_live_data_tab, base_url)
    with tabs[3]:
        _render_view(render_knowledge_base_tab, base_url)
    with tabs[4]:
        _render_view(render_session_tab, base_url, session_id)

    st.divider()
    st.caption(
        f"Dashboard → {base_url} · Reads the same REST API as the farmer voice UI."
    )


main()
