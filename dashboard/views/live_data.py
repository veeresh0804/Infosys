"""Live-data views: APMC prices, agricultural weather and scheme eligibility.

These views reuse the same public endpoints as the farmer chat pipeline. Results
are cached briefly to protect upstream providers, with explicit refresh actions.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import streamlit as st

try:  # ``streamlit run dashboard/app.py`` puts the dashboard folder on sys.path
    from api_client import AgriApiClient, BackendError
    from ui import empty_state, esc, fmt_pct, section_title
except ImportError:  # imported as a package (``dashboard.views.live_data``)
    from dashboard.api_client import AgriApiClient, BackendError
    from dashboard.ui import empty_state, esc, fmt_pct, section_title


MANDI_COLUMNS = [
    "commodity", "market", "district", "state", "modal_price",
    "min_price", "max_price", "arrival_date", "source",
]


# --------------------------------------------------------------------------- cache
@st.cache_data(ttl=60, show_spinner=False)
def _fetch_mandi_prices(base_url: str, commodity: str, state: str, limit: int) -> list[dict[str, Any]]:
    """Fetch AGMARKNET mandi prices through the backend."""
    return AgriApiClient(base_url).mandi_prices(
        commodity=commodity or None, state=state or None, limit=limit
    )


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_weather(
    base_url: str, district: str, latitude: Optional[float], longitude: Optional[float]
) -> dict[str, Any]:
    """Fetch current weather and an agro-meteorological advisory."""
    return AgriApiClient(base_url).weather(
        district=district or None, latitude=latitude, longitude=longitude
    )


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_scheme_eligibility(
    base_url: str, landholding_acres: float, crops: str, state: str
) -> list[dict[str, Any]]:
    """Evaluate the farmer profile against government schemes."""
    return AgriApiClient(base_url).scheme_eligibility(landholding_acres, crops, state)


# ------------------------------------------------------------------------- helpers
def _show_backend_error(exc: BackendError, base_url: str) -> None:
    """Render a consistent, actionable backend failure message."""
    message = str(exc)
    if "uvicorn" not in message.lower():
        message += (
            f"\n\nMake sure the FastAPI backend is running at {base_url}. Start it from "
            "the project root with `python -m uvicorn backend.app.main:app --port 8000`."
        )
    st.error(message)


def _refresh_cached(cache_fn: Any, kwargs: dict[str, Any], session_key: str, spinner: str) -> None:
    """Bypass the short-lived cache, fetch fresh data and rerun the view."""
    cache_fn.clear()
    try:
        with st.spinner(spinner):
            fresh = cache_fn(**kwargs)
    except BackendError as exc:
        _show_backend_error(exc, str(kwargs.get("base_url", "")))
        return
    except Exception as exc:  # defensive: a malformed response must not crash the tab
        st.error(f"Unexpected error while refreshing data: {exc}")
        return
    st.session_state[session_key] = fresh
    st.rerun()


def _fetch_and_store(
    fetch_fn: Any,
    base_url: str,
    params: dict[str, Any],
    session_key: str,
    query_key: str,
    spinner: str,
    action: str,
) -> None:
    """Fetch through the cached client and persist the latest result and query."""
    try:
        with st.spinner(spinner):
            result = fetch_fn(base_url, **params)
    except BackendError as exc:
        _show_backend_error(exc, base_url)
    except Exception as exc:  # defensive: a malformed response must not crash the tab
        st.error(f"Unexpected error while {action}: {exc}")
    else:
        st.session_state[session_key] = result
        st.session_state[query_key] = params
        st.rerun()


def _section_header(
    title: str,
    caption: str,
    base_url: str,
    query_key: str,
    cache_fn: Any,
    session_key: str,
    spinner: str,
) -> None:
    """Render a sub-tab heading plus its cache-busting refresh button."""
    heading, action = st.columns([4, 1], vertical_alignment="center")
    with heading:
        st.markdown(f"#### {title}")
        st.caption(caption)
    query = st.session_state.get(query_key)
    with action:
        if st.button(
            "🔄 Refresh",
            key=f"{session_key}_refresh",
            width="stretch",
            disabled=not query,
            help="Clear the 60-second cache and fetch fresh data.",
        ):
            _refresh_cached(cache_fn, {"base_url": base_url, **(query or {})}, session_key, spinner)


def _is_mock(source: Any) -> bool:
    return "mock" in str(source or "").lower()


def _fmt_measure(value: Any, suffix: str, decimals: int = 1) -> str:
    try:
        return f"{float(value):.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def _safe_url(value: Any) -> str:
    """Allow only ordinary web links from backend-supplied portal URLs."""
    url = str(value or "").strip()
    return esc(url) if url.lower().startswith(("http://", "https://")) else ""


# ---------------------------------------------------------------------- 1) mandi
def _render_mandi(base_url: str) -> None:
    _section_header(
        "💰 Mandi prices",
        "Wholesale APMC prices from AGMARKNET (mock fallback when no data.gov.in key is set).",
        base_url,
        "mandi_query",
        _fetch_mandi_prices,
        "mandi_result",
        "Refreshing mandi prices...",
    )

    with st.form("mandi_form", border=True):
        commodity_col, state_col, limit_col = st.columns([2, 2, 1])
        commodity = commodity_col.text_input("Commodity", value="Tomato", key="mandi_commodity_input")
        state = state_col.text_input("State", value="Karnataka", key="mandi_state_input")
        limit = limit_col.number_input(
            "Rows", min_value=1, max_value=20, value=5, step=1, key="mandi_limit_input"
        )
        submitted = st.form_submit_button("Fetch prices", type="primary", width="stretch")

    if submitted:
        params = {"commodity": commodity.strip(), "state": state.strip(), "limit": int(limit)}
        _fetch_and_store(
            _fetch_mandi_prices, base_url, params, "mandi_result", "mandi_query",
            "Fetching APMC mandi prices...", "fetching mandi prices",
        )

    stored = st.session_state.get("mandi_result")
    if stored is None:
        empty_state("No prices loaded yet — choose a commodity and state, then press “Fetch prices”.")
        return

    items = [item for item in stored if isinstance(item, dict)] if isinstance(stored, list) else []
    if not items:
        empty_state("No mandi records matched this query. Try a broader state or commodity.")
        return
    if any(_is_mock(item.get("source")) for item in items):
        st.warning(
            "Using clearly-labelled mock AGMARKNET data — set DATA_GOV_IN_API_KEY for live prices."
        )

    frame = pd.DataFrame(items)
    for column in MANDI_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    display = frame[MANDI_COLUMNS].copy()
    for column in ("modal_price", "min_price", "max_price"):
        display[column] = pd.to_numeric(display[column], errors="coerce")

    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config={
            "commodity": "Commodity",
            "market": "Market",
            "district": "District",
            "state": "State",
            "modal_price": st.column_config.NumberColumn("Modal ₹/qtl", format="₹%.0f"),
            "min_price": st.column_config.NumberColumn("Min ₹/qtl", format="₹%.0f"),
            "max_price": st.column_config.NumberColumn("Max ₹/qtl", format="₹%.0f"),
            "arrival_date": "Arrival date",
            "source": "Source",
        },
    )

    chart = display.dropna(subset=["modal_price"]).set_index("market")["modal_price"]
    if len(chart) >= 2:
        st.bar_chart(chart, width="stretch")
        st.caption("Modal wholesale price by market (₹ per quintal).")


# -------------------------------------------------------------------- 2) weather
def _render_weather(base_url: str) -> None:
    _section_header(
        "🌦️ Weather",
        "Current conditions and a spray/irrigation advisory from Open-Meteo.",
        base_url,
        "weather_query",
        _fetch_weather,
        "weather_result",
        "Refreshing weather...",
    )
    use_coordinates = st.toggle(
        "Use coordinates",
        key="weather_use_coordinates",
        help="Use an exact latitude/longitude instead of the district lookup table.",
    )

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    with st.form("weather_form", border=True):
        cols = st.columns(
            [2, 1, 1] if use_coordinates else [1], vertical_alignment="bottom"
        )
        district = cols[0].text_input("District", value="Bengaluru Rural", key="weather_district_input")
        if use_coordinates:
            latitude = cols[1].number_input(
                "Latitude", min_value=-90.0, max_value=90.0, value=12.9716,
                step=0.0001, format="%.4f", key="weather_latitude_input",
            )
            longitude = cols[2].number_input(
                "Longitude", min_value=-180.0, max_value=180.0, value=77.5946,
                step=0.0001, format="%.4f", key="weather_longitude_input",
            )
        submitted = st.form_submit_button("Fetch weather", type="primary", width="stretch")

    if submitted:
        params = {"district": district.strip(), "latitude": latitude, "longitude": longitude}
        _fetch_and_store(
            _fetch_weather, base_url, params, "weather_result", "weather_query",
            "Fetching live weather...", "fetching weather",
        )

    weather = st.session_state.get("weather_result")
    if not isinstance(weather, dict):
        empty_state("No weather loaded yet — enter a district (or coordinates) and press “Fetch weather”.")
        return
    if _is_mock(weather.get("source")):
        st.warning(
            "Using labelled mock weather data — the live Open-Meteo call failed, so these values "
            "are a safe fallback."
        )

    metric_cols = st.columns(4)
    metric_cols[0].metric("Temperature", _fmt_measure(weather.get("temperature"), " °C"), border=True)
    metric_cols[1].metric("Humidity", _fmt_measure(weather.get("humidity"), "%", 0), border=True)
    metric_cols[2].metric(
        "Rain probability", _fmt_measure(weather.get("precipitation_prob"), "%", 0), border=True
    )
    metric_cols[3].metric("Wind speed", _fmt_measure(weather.get("wind_speed"), " km/h"), border=True)

    st.markdown(
        f"""
        <div class="ks-card">
          <div class="ks-eyebrow">📍 {esc(weather.get("location", "Unknown location"))}</div>
          <div style="font-size:.9rem;line-height:1.6;color:#374151;">
            {esc(weather.get("advisory", "No advisory available."))}
          </div>
          <div class="ks-muted" style="margin-top:8px;">
            {esc(weather.get("forecast_summary", "No forecast summary available."))}
          </div>
          <div class="ks-muted" style="margin-top:4px;">
            Source: {esc(weather.get("source", "—"))}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -------------------------------------------------------------------- 3) schemes
def _render_schemes(base_url: str) -> None:
    _section_header(
        "📜 Scheme eligibility",
        "Rule-based screening against PM-KISAN, PMFBY, KCC and Soil Health Card criteria.",
        base_url,
        "scheme_query",
        _fetch_scheme_eligibility,
        "scheme_result",
        "Re-evaluating scheme eligibility...",
    )

    with st.form("scheme_form", border=True):
        acres_col, crops_col, state_col = st.columns([1, 2, 2])
        acres = acres_col.number_input(
            "Landholding (acres)", min_value=0.0, max_value=1000.0, value=2.5,
            step=0.1, key="scheme_acres_input",
        )
        crops = crops_col.text_input(
            "Crops (comma-separated)", value="Tomato,Paddy", key="scheme_crops_input"
        )
        state = state_col.text_input("State", value="Karnataka", key="scheme_state_input")
        submitted = st.form_submit_button(
            "Check eligibility", type="primary", width="stretch"
        )

    if submitted:
        params = {"landholding_acres": float(acres), "crops": crops.strip(), "state": state.strip()}
        _fetch_and_store(
            _fetch_scheme_eligibility, base_url, params, "scheme_result", "scheme_query",
            "Evaluating scheme eligibility...", "checking scheme eligibility",
        )

    stored = st.session_state.get("scheme_result")
    if stored is None:
        empty_state(
            "No eligibility report yet — enter a landholding and crops, then press “Check eligibility”."
        )
        return

    schemes = [item for item in stored if isinstance(item, dict)] if isinstance(stored, list) else []
    if not schemes:
        empty_state("The backend returned no scheme results for this profile.")
        return

    eligible = sum(1 for scheme in schemes if bool(scheme.get("is_eligible")))
    eligible_col, rate_col = st.columns(2)
    eligible_col.metric("Eligible schemes", f"{eligible} / {len(schemes)}", border=True)
    rate_col.metric("Eligibility rate", fmt_pct(eligible / len(schemes)), border=True)

    query = st.session_state.get("scheme_query") or {}
    if query:
        st.caption(
            f"Evaluated for {query.get('landholding_acres', '—')} acres · "
            f"crops: {query.get('crops') or '—'} · state: {query.get('state') or '—'}"
        )

    for scheme in schemes:
        is_eligible = bool(scheme.get("is_eligible"))
        css_class = "eligible" if is_eligible else "ineligible"
        icon = "✅" if is_eligible else "❌"
        portal = _safe_url(scheme.get("portal_url"))
        portal_html = (
            f'<p><a href="{portal}" target="_blank" rel="noreferrer">Official portal ↗</a></p>'
            if portal else ""
        )
        st.markdown(
            f"""
            <div class="ks-scheme {css_class}">
              <h4>{icon} {esc(scheme.get("scheme_name", "Unnamed scheme"))}</h4>
              <p><strong>Eligibility:</strong> {esc(scheme.get("reason", "No reason provided."))}</p>
              <p><strong>Benefits:</strong> {esc(scheme.get("benefits", "Not specified."))}</p>
              {portal_html}
            </div>
            """,
            unsafe_allow_html=True,
        )


# ------------------------------------------------------------------ public entry
def render_live_data_tab(base_url: str) -> None:
    """Render the three live-data sub-tabs inside the main dashboard."""
    section_title(
        "Real-time data",
        "APMC prices, weather and scheme eligibility",
        "Calls the same live-data endpoints used by the farmer chat pipeline.",
    )
    with st.container():
        mandi_tab, weather_tab, schemes_tab = st.tabs(
            ["💰 Mandi prices", "🌦️ Weather", "📜 Scheme eligibility"]
        )
        with mandi_tab:
            _render_mandi(base_url)
        with weather_tab:
            _render_weather(base_url)
        with schemes_tab:
            _render_schemes(base_url)
