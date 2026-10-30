"""Shared presentation helpers for the KisanSahayak Streamlit dashboard.

Every view imports its styling and small render helpers from here so the
dashboard keeps one visual language. Keep this module free of backend calls.
"""

from __future__ import annotations

import html
from typing import Any, Optional

import pandas as pd
import streamlit as st

LANGUAGES: dict[str, str] = {
    "hi": "हिन्दी (Hindi)",
    "kn": "ಕನ್ನಡ (Kannada)",
    "en": "English",
}

LANG_LABELS: dict[str, str] = {"hi": "Hindi", "kn": "Kannada", "en": "English"}

SAMPLE_QUERIES: list[dict[str, str]] = [
    {
        "label": "🍅 Tomato leaf curl (Hindi)",
        "text": "टमाटर की फसल में पत्ता मरोड़ रोग का क्या उपाय है?",
        "lang": "hi",
    },
    {
        "label": "🌾 Paddy stem borer (Kannada)",
        "text": "ಭತ್ತದಲ್ಲಿ ಕಾಂಡ ಕೊರೆಯುವ ಹುಳುವಿನ ಹಾನಿಯನ್ನು ಹೇಗೆ ನಿಯಂತ್ರಿಸುವುದು?",
        "lang": "kn",
    },
    {
        "label": "💰 Tomato mandi price (English)",
        "text": "What is today's mandi price for Tomato in Karnataka?",
        "lang": "en",
    },
    {
        "label": "🌦️ Spray or not today? (Hindi)",
        "text": "क्या आज बारिश होगी? छिड़काव कर सकते हैं क्या?",
        "lang": "hi",
    },
    {
        "label": "📜 PM-KISAN eligibility (English)",
        "text": "Am I eligible for PM-KISAN subsidy with 2 acres land?",
        "lang": "en",
    },
]

CSS = """
<style>
:root {
  --ks-green-900: #14532d;
  --ks-green-700: #15803d;
  --ks-green-500: #22c55e;
  --ks-green-50:  #f0fdf4;
  --ks-amber:     #b45309;
  --ks-red:       #b91c1c;
  --ks-ink:       #1f2937;
  --ks-muted:     #6b7280;
  --ks-line:      #e5e7eb;
  --ks-card:      rgba(255, 255, 255, 0.86);
}

/* Hero */
.ks-hero {
  background: linear-gradient(120deg, #14532d 0%, #166534 45%, #15803d 100%);
  color: #f0fdf4;
  border-radius: 18px;
  padding: 22px 26px;
  margin-bottom: 10px;
  box-shadow: 0 10px 26px rgba(20, 83, 45, 0.22);
}
.ks-hero h1 { color: #ffffff; font-size: 1.65rem; margin: 0 0 4px 0; letter-spacing: -0.02em; }
.ks-hero p  { color: #dcfce7; margin: 0; font-size: 0.92rem; }
.ks-hero .ks-hero-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.ks-hero .ks-hero-spacer { flex: 1 1 auto; }

/* Status */
.ks-status {
  display: inline-flex; align-items: center; gap: 7px;
  border-radius: 999px; padding: 5px 12px;
  font-size: 0.78rem; font-weight: 600; letter-spacing: 0.01em;
  border: 1px solid transparent; white-space: nowrap;
}
.ks-status .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.ks-status.online  { background: #dcfce7; color: #14532d; border-color: #86efac; }
.ks-status.online .dot { background: #16a34a; box-shadow: 0 0 0 3px rgba(22,163,74,.18); }
.ks-status.offline { background: #fee2e2; color: #7f1d1d; border-color: #fca5a5; }
.ks-status.offline .dot { background: #dc2626; box-shadow: 0 0 0 3px rgba(220,38,38,.18); }

/* Pills */
.ks-pill {
  display: inline-block; border-radius: 999px; padding: 3px 10px;
  margin: 2px 4px 2px 0; font-size: 0.74rem; font-weight: 600;
  border: 1px solid #e5e7eb; background: #f9fafb; color: #374151;
  white-space: nowrap;
}
.ks-pill.green { background: #dcfce7; color: #14532d; border-color: #86efac; }
.ks-pill.amber { background: #fef3c7; color: #78350f; border-color: #fcd34d; }
.ks-pill.red   { background: #fee2e2; color: #7f1d1d; border-color: #fca5a5; }
.ks-pill.blue  { background: #dbeafe; color: #1e3a8a; border-color: #93c5fd; }
.ks-pill.gray  { background: #f3f4f6; color: #374151; border-color: #d1d5db; }

/* Cards */
.ks-card {
  background: var(--ks-card);
  border: 1px solid var(--ks-line);
  border-radius: 14px;
  padding: 16px 18px;
  margin-bottom: 12px;
  box-shadow: 0 2px 8px rgba(17, 24, 39, 0.05);
}
.ks-eyebrow {
  text-transform: uppercase; letter-spacing: 0.09em;
  font-size: 0.68rem; font-weight: 700; color: var(--ks-muted);
  margin-bottom: 6px;
}

/* Answer */
.ks-answer {
  background: linear-gradient(180deg, #ffffff 0%, #f7fdf9 100%);
  border: 1px solid #bbf7d0;
  border-left: 6px solid var(--ks-green-700);
  border-radius: 14px;
  padding: 18px 20px;
  margin: 6px 0 10px 0;
}
.ks-answer .ks-answer-text {
  font-size: 1.02rem; line-height: 1.65; color: #111827;
  white-space: normal;
}
.ks-answer .ks-answer-text br { content: ""; display: block; margin: 3px 0; }
.ks-answer .ks-source { color: var(--ks-muted); font-size: 0.76rem; margin-top: 10px; }

/* Weather + mandi mini widgets */
.ks-weather-strip {
  display: flex; gap: 10px; flex-wrap: wrap; margin: 4px 0 8px 0;
}
.ks-weather-cell {
  flex: 1 1 120px; min-width: 120px;
  background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 12px;
  padding: 10px 12px;
}
.ks-weather-cell .k { font-size: 0.68rem; text-transform: uppercase; letter-spacing: .08em; color: #0369a1; font-weight: 700; }
.ks-weather-cell .v { font-size: 1.15rem; font-weight: 700; color: #0c4a6e; margin-top: 2px; }

.ks-price {
  font-size: 1.5rem; font-weight: 800; color: var(--ks-green-900);
  letter-spacing: -0.02em;
}
.ks-price small { font-size: 0.72rem; font-weight: 600; color: var(--ks-muted); }

/* Schemes */
.ks-scheme {
  border-radius: 12px; padding: 13px 15px; margin-bottom: 10px;
  border: 1px solid var(--ks-line); background: #ffffff;
}
.ks-scheme.eligible { border-left: 5px solid #16a34a; background: #f7fef9; }
.ks-scheme.ineligible { border-left: 5px solid #dc2626; background: #fff7f7; }
.ks-scheme h4 { margin: 0 0 6px 0; font-size: 0.95rem; color: #111827; }
.ks-scheme p { margin: 3px 0; font-size: 0.82rem; color: #374151; line-height: 1.5; }
.ks-scheme a { color: var(--ks-green-700); font-weight: 600; text-decoration: none; }

/* Chat history */
.ks-chat-row { display: flex; margin: 8px 0; }
.ks-chat-row.farmer { justify-content: flex-end; }
.ks-chat-row.assistant { justify-content: flex-start; }
.ks-bubble {
  max-width: 82%; border-radius: 14px; padding: 10px 14px;
  font-size: 0.88rem; line-height: 1.55; border: 1px solid var(--ks-line);
}
.ks-chat-row.farmer .ks-bubble { background: #dcfce7; border-color: #bbf7d0; color: #14532d; }
.ks-chat-row.assistant .ks-bubble { background: #ffffff; color: #1f2937; }
.ks-bubble .meta { display: block; margin-top: 5px; font-size: 0.68rem; color: #6b7280; }

/* Misc */
.ks-muted { color: var(--ks-muted); font-size: 0.8rem; }
.ks-empty {
  border: 1px dashed #d1d5db; border-radius: 12px; padding: 22px;
  text-align: center; color: var(--ks-muted); background: #fcfcfc;
  font-size: 0.88rem;
}
.ks-divider { height: 1px; background: var(--ks-line); margin: 14px 0; }

/* Metric cards (theme handles page padding/sidebar colours via config.toml) */
div[data-testid="stMetric"] {
  background: #ffffff; border: 1px solid var(--ks-line); border-radius: 12px;
  padding: 10px 14px; box-shadow: 0 1px 4px rgba(17,24,39,.04);
}

/* Responsive KPI rows: 4-up on wide screens, 2-up when the window is narrow.
   Only rows whose columns contain metrics directly are affected, so content
   layouts such as the Ask tab keep their proportions. */
@media (max-width: 1200px) {
  [data-testid="stHorizontalBlock"]:has(
    > [data-testid="stColumn"] > [data-testid="stVerticalBlock"]
    > [data-testid="stElementContainer"] > [data-testid="stMetric"]
  ) {
    flex-wrap: wrap;
    row-gap: 0.75rem;
  }
  [data-testid="stHorizontalBlock"]:has(
    > [data-testid="stColumn"] > [data-testid="stVerticalBlock"]
    > [data-testid="stElementContainer"] > [data-testid="stMetric"]
  ) > [data-testid="stColumn"] {
    flex: 1 1 calc(50% - 0.5rem);
    min-width: calc(50% - 0.5rem);
    max-width: calc(50% - 0.5rem);
  }
  div[data-testid="stMetricValue"] { font-size: 1.65rem; }
  [data-testid="stMainBlockContainer"] { padding-left: 2rem; padding-right: 2rem; }
}
@media (max-width: 900px) {
  [data-testid="stMainBlockContainer"] { padding-left: 1rem; padding-right: 1rem; }
}
</style>
"""


def inject_css() -> None:
    """Inject the shared stylesheet once per rerun."""
    st.markdown(CSS, unsafe_allow_html=True)


def esc(text: Any) -> str:
    """HTML-escape user/backend text and preserve line breaks."""
    if text is None:
        return ""
    return html.escape(str(text)).replace("\n", "<br>")


def pill(text: str, kind: str = "gray") -> str:
    """Return an inline HTML pill. Use inside st.markdown(..., unsafe_allow_html=True)."""
    return f'<span class="ks-pill {kind}">{esc(text)}</span>'


def status_html(online: bool, label: Optional[str] = None) -> str:
    if online:
        return (
            '<span class="ks-status online"><span class="dot"></span>'
            f"{esc(label or 'Backend online')}</span>"
        )
    return (
        '<span class="ks-status offline"><span class="dot"></span>'
        f"{esc(label or 'Backend offline')}</span>"
    )


def confidence_kind(score: float, is_low: bool) -> str:
    if is_low:
        return "red"
    if score >= 0.85:
        return "green"
    return "amber"


def fmt_pct(value: Optional[float]) -> str:
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return "—"


def empty_state(message: str) -> None:
    st.markdown(f'<div class="ks-empty">{esc(message)}</div>', unsafe_allow_html=True)


def section_title(eyebrow: str, title: str, help_text: Optional[str] = None) -> None:
    st.markdown(
        f'<div class="ks-eyebrow">{esc(eyebrow)}</div>'
        f'<div style="font-size:1.12rem;font-weight:700;color:#111827;margin-bottom:2px;">{esc(title)}</div>',
        unsafe_allow_html=True,
    )
    if help_text:
        st.caption(help_text)


def render_live_data_panel(live_data: Optional[dict[str, Any]]) -> None:
    """Compact rendering of the ``live_data`` block returned by /api/rag/query."""
    if not live_data:
        return

    weather = live_data.get("weather")
    prices = live_data.get("mandi_prices") or []
    schemes = live_data.get("schemes_evaluated") or []

    if weather:
        st.markdown(
            f"""
            <div class="ks-card">
              <div class="ks-eyebrow">Live weather · {esc(weather.get('location', '—'))}</div>
              <div class="ks-weather-strip">
                <div class="ks-weather-cell"><div class="k">Temperature</div><div class="v">{esc(weather.get('temperature', '—'))}°C</div></div>
                <div class="ks-weather-cell"><div class="k">Humidity</div><div class="v">{esc(weather.get('humidity', '—'))}%</div></div>
                <div class="ks-weather-cell"><div class="k">Rain chance</div><div class="v">{esc(weather.get('precipitation_prob', '—'))}%</div></div>
                <div class="ks-weather-cell"><div class="k">Wind</div><div class="v">{esc(weather.get('wind_speed', '—'))} km/h</div></div>
              </div>
              <div style="font-size:.84rem;color:#374151;line-height:1.5;">🌾 {esc(weather.get('advisory', ''))}</div>
              <div class="ks-muted" style="margin-top:6px;">Source: {esc(weather.get('source', '—'))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if prices:
        st.markdown('<div class="ks-eyebrow">APMC mandi prices</div>', unsafe_allow_html=True)
        frame = pd.DataFrame(prices)
        keep = [c for c in ["commodity", "market", "state", "modal_price", "min_price", "max_price", "source"] if c in frame.columns]
        if keep:
            display = frame[keep].copy()
            for column in ["modal_price", "min_price", "max_price"]:
                if column in display.columns:
                    display[column] = pd.to_numeric(display[column], errors="coerce")
            st.dataframe(
                display,
                width="stretch",
                hide_index=True,
                column_config={
                    "commodity": "Commodity",
                    "market": "Market",
                    "state": "State",
                    "modal_price": st.column_config.NumberColumn("Modal ₹/qtl", format="₹%.0f"),
                    "min_price": st.column_config.NumberColumn("Min ₹/qtl", format="₹%.0f"),
                    "max_price": st.column_config.NumberColumn("Max ₹/qtl", format="₹%.0f"),
                    "source": "Source",
                },
            )

    if schemes:
        st.markdown('<div class="ks-eyebrow">Scheme eligibility</div>', unsafe_allow_html=True)
        for scheme in schemes:
            eligible = bool(scheme.get("is_eligible"))
            css_class = "eligible" if eligible else "ineligible"
            icon = "✅" if eligible else "❌"
            st.markdown(
                f"""
                <div class="ks-scheme {css_class}">
                  <h4>{icon} {esc(scheme.get('scheme_name', 'Scheme'))}</h4>
                  <p><strong>Eligibility:</strong> {esc(scheme.get('reason', ''))}</p>
                  <p><strong>Benefit:</strong> {esc(scheme.get('benefits', ''))}</p>
                  <p><a href="{esc(scheme.get('portal_url', '#'))}" target="_blank" rel="noreferrer">Official portal ↗</a></p>
                </div>
                """,
                unsafe_allow_html=True,
            )
