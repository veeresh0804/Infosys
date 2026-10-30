"""Farmer session inspector for the KisanSahayak extension dashboard.

Shows the SQLite-backed session profile and conversation history, lets an
extension worker correct farmer context, and exposes the raw session JSON.
All data comes through the backend REST API.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Optional

import streamlit as st

try:  # ``streamlit run dashboard/app.py`` (project root on sys.path)
    from dashboard.api_client import AgriApiClient, BackendError
    from dashboard.ui import (
        LANG_LABELS,
        LANGUAGES,
        confidence_kind,
        empty_state,
        esc,
        fmt_pct,
        pill,
        section_title,
    )
except ImportError:  # ``streamlit run app.py`` from inside the dashboard folder
    from api_client import AgriApiClient, BackendError
    from ui import (
        LANG_LABELS,
        LANGUAGES,
        confidence_kind,
        empty_state,
        esc,
        fmt_pct,
        pill,
        section_title,
    )


@st.cache_data(ttl=45, show_spinner=False)
def load_session(base_url: str, session_id: str) -> dict:
    """Fetch one farmer session; cached briefly so tab switches stay snappy."""
    return AgriApiClient(base_url).get_session(session_id)


def _short_id(value: Any, head: int = 12, tail: int = 4) -> str:
    text = str(value or "").strip()
    if not text:
        return "—"
    if len(text) <= head + tail + 1:
        return text
    return f"{text[:head]}…{text[-tail:]}"


def _fmt_number(value: Any) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return "—"


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_timestamp(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    try:
        stamp = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return stamp.strftime("%d %b %Y, %H:%M UTC")


def _render_metrics(session: dict, session_id: str) -> None:
    language_code = str(session.get("preferred_language") or "").strip()
    language = LANG_LABELS.get(language_code, language_code or "—")

    cols = st.columns(4)
    with cols[0]:
        st.metric(
            "Session",
            _short_id(session_id),
            help=f"Full session id: {session_id}",
            border=True,
        )
    with cols[1]:
        st.metric("Farmer / user", str(session.get("user_id") or "—"), border=True)
    with cols[2]:
        st.metric("Preferred language", language, border=True)
    with cols[3]:
        st.metric(
            "Landholding (acres)",
            _fmt_number(session.get("landholding_acres")),
            border=True,
        )

    crops = [
        str(crop).strip()
        for crop in (session.get("crops_grown") or [])
        if str(crop).strip()
    ]
    if crops:
        chips = " ".join(pill(crop, "green") for crop in crops)
        st.markdown(
            f'<div style="margin:2px 0 14px 0;">'
            f'<span class="ks-muted">Crops ({len(crops)})</span> {chips}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.caption("Crops (0): none recorded yet — add them in the profile form below.")


def _render_profile_form(base_url: str, session_id: str, session: dict) -> Optional[dict]:
    """Render the edit form and PATCH the session when submitted."""
    crops = [
        str(crop).strip()
        for crop in (session.get("crops_grown") or [])
        if str(crop).strip()
    ]
    languages = list(LANGUAGES.keys())
    current_language = str(session.get("preferred_language") or "en").strip()
    if current_language not in languages:
        current_language = "en"

    with st.form("session_form"):
        left, right = st.columns(2)
        with left:
            preferred_language = st.selectbox(
                "Preferred language",
                options=languages,
                index=languages.index(current_language),
                format_func=lambda code: LANGUAGES.get(code, code),
                help="The backend uses this for the answer language and voice.",
            )
            state = st.text_input(
                "State",
                value=str(session.get("state") or ""),
                placeholder="e.g. Karnataka",
            )
        with right:
            district = st.text_input(
                "District",
                value=str(session.get("district") or ""),
                placeholder="e.g. Bengaluru Rural",
            )
            landholding = st.number_input(
                "Landholding (acres)",
                min_value=0.0,
                step=0.5,
                value=_as_float(session.get("landholding_acres")),
                format="%.1f",
                help="Used by the backend for scheme eligibility. Leave blank if unknown.",
            )
        crops_text = st.text_input(
            "Crops grown",
            value=", ".join(crops),
            placeholder="Tomato, Paddy, Ragi",
            help="Comma-separated crop names.",
        )
        submitted = st.form_submit_button(
            "💾 Save farmer context",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return None

    updates = {
        "preferred_language": preferred_language,
        "state": state.strip(),
        "district": district.strip(),
        "landholding_acres": float(landholding) if landholding is not None else None,
        "crops_grown": [
            part.strip() for part in crops_text.split(",") if part.strip()
        ],
    }

    try:
        updated = AgriApiClient(base_url).update_session(session_id, updates)
    except BackendError as exc:
        st.error(f"Could not save the farmer context. {exc}")
        return None

    if not isinstance(updated, dict):
        st.warning(
            "The backend saved the profile but returned an unexpected payload. "
            "Reload the session to refresh."
        )
        load_session.clear()
        return None

    st.success("Farmer context saved.")
    st.toast("Farmer context saved.", icon="✅")
    load_session.clear()
    return updated


def _message_chips(metadata: dict, fallback_language: Any) -> str:
    chips: list[str] = []

    sub_agent = metadata.get("sub_agent")
    if sub_agent:
        chips.append(pill(str(sub_agent), "blue"))

    confidence = metadata.get("confidence_score")
    if confidence is not None:
        score = _as_float(confidence)
        if score is not None:
            chips.append(
                pill(
                    f"confidence {fmt_pct(score)}",
                    confidence_kind(score, bool(metadata.get("is_low_confidence"))),
                )
            )

    language = metadata.get("language") or fallback_language
    if language:
        language_text = str(language)
        chips.append(
            pill(LANG_LABELS.get(language_text, language_text), "gray")
        )

    return "".join(chips)


def _render_history(session: dict) -> None:
    history = session.get("history") or []
    fallback_language = session.get("preferred_language")

    with st.container(height=420, border=True):
        if not isinstance(history, list) or not history:
            empty_state("No conversation history for this session yet.")
            return

        for item in reversed(history):
            if not isinstance(item, dict):
                continue

            role = (
                "farmer"
                if str(item.get("role") or "").strip().lower() == "farmer"
                else "assistant"
            )
            metadata = item.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            else:
                metadata = dict(metadata)

            # Tolerate older rows that stored telemetry at the top level.
            for key in ("sub_agent", "confidence_score", "is_low_confidence", "language"):
                if key not in metadata and item.get(key) is not None:
                    metadata[key] = item.get(key)

            text = item.get("text") or item.get("canonical_text") or ""
            chips = _message_chips(metadata, fallback_language)
            timestamp = _fmt_timestamp(item.get("timestamp"))

            meta_html = chips
            if timestamp:
                meta_html += f'<span style="margin-left:6px;">· {esc(timestamp)}</span>'

            st.markdown(
                f'<div class="ks-chat-row {role}">'
                f'<div class="ks-bubble">'
                f'<span style="display:block;font-size:.66rem;font-weight:700;'
                f'letter-spacing:.08em;text-transform:uppercase;color:#6b7280;'
                f'margin-bottom:4px;">{role}</span>'
                f"<div>{esc(text)}</div>"
                f'<span class="meta">{meta_html}</span>'
                f"</div></div>",
                unsafe_allow_html=True,
            )


def render_session_tab(base_url: str, session_id: str) -> None:
    """Render the Farmer session tab."""
    section_title(
        "Farmer state",
        "Session profile and conversation history",
        "The backend stores this context in SQLite and uses it to personalise every answer.",
    )

    session_key = (session_id or "").strip()
    if not session_key:
        st.warning("Enter a session ID in the sidebar to inspect a farmer session.")
        return

    toolbar = st.columns([5, 1], vertical_alignment="center")
    with toolbar[1]:
        if st.button(
            "🔄 Reload",
            key="session_reload_button",
            width="stretch",
        ):
            load_session.clear()
            st.rerun()

    try:
        session = load_session(base_url, session_key)
    except BackendError as exc:
        st.error(
            "Could not load this farmer session. Start the backend from the project "
            "root with `backend\\venv\\Scripts\\python.exe -m uvicorn "
            "backend.app.main:app --port 8000`, then press **Reload session**. "
            f"({exc})"
        )
        return

    if not isinstance(session, dict):
        st.error(
            "The backend returned an unexpected session payload. "
            "Press **Reload session** to try again."
        )
        return

    active_id = str(session.get("session_id") or session_key)

    metrics_slot = st.empty()
    with metrics_slot.container():
        _render_metrics(session, active_id)

    st.subheader("Edit farmer context")
    updated = _render_profile_form(base_url, active_id, session)
    if updated is not None:
        session = updated
        active_id = str(session.get("session_id") or active_id)
        metrics_slot.empty()
        with metrics_slot.container():
            _render_metrics(session, active_id)

    section_title(
        "Conversation",
        "Session history",
        "Newest messages first — scroll inside the panel to read older turns.",
    )
    _render_history(session)

    with st.expander("View raw session JSON"):
        st.json(session)

    st.caption(
        "History is capped only by the backend and is shared with the farmer voice "
        "UI when the same session id is used."
    )
