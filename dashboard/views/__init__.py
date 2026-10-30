"""Streamlit view modules for the KisanSahayak extension-worker dashboard."""

from .knowledge_base import render_knowledge_base_tab
from .live_data import render_live_data_tab

__all__ = ["render_live_data_tab", "render_knowledge_base_tab"]
