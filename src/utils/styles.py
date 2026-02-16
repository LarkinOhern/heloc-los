"""Shared CSS and styled components for the HELOC LOS app.

Call inject_css() once per page render (idempotent via st.markdown key).
Use the helper functions for consistent styled elements.
"""

import streamlit as st
from src.config import STATUS_COLORS, STATUS_LABELS

# ── Global CSS ──────────────────────────────────────────────────────────────

_CSS = """
<style>
/* ── Status Badges ────────────────────────────────────────────── */
.status-badge {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 12px;
    font-weight: 600;
    font-size: 13px;
    color: white;
    letter-spacing: 0.3px;
}

/* ── Pipeline Cards ───────────────────────────────────────────── */
.pipeline-card {
    text-align: center;
    padding: 12px 8px;
    border-radius: 8px;
    border-left: 5px solid;
    background: linear-gradient(135deg, #fafafa 0%, #f5f5f5 100%);
    margin-bottom: 4px;
}
.pipeline-card .count {
    font-size: 28px;
    font-weight: 700;
    line-height: 1.2;
}
.pipeline-card .label {
    font-size: 11px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 2px;
}

/* ── Pipeline Row ─────────────────────────────────────────────── */
.pipeline-row {
    padding: 8px 0;
    border-bottom: 1px solid #f0f0f0;
}

/* ── Section Headers ──────────────────────────────────────────── */
.section-header {
    font-size: 14px;
    font-weight: 600;
    color: #1f77b4;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 8px;
    border-bottom: 2px solid #1f77b4;
    padding-bottom: 4px;
}

/* ── Info Cards ───────────────────────────────────────────────── */
.info-card {
    background: #f8f9fa;
    border-radius: 8px;
    padding: 16px;
    border: 1px solid #e9ecef;
    margin-bottom: 8px;
}
.info-card .card-label {
    font-size: 11px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.info-card .card-value {
    font-size: 20px;
    font-weight: 600;
    color: #262730;
    margin-top: 2px;
}

/* ── Stepper ──────────────────────────────────────────────────── */
.step-done {
    text-align: center; padding: 10px 8px;
    background: #e8f5e9; border-radius: 8px;
    border: 2px solid #4caf50;
}
.step-done strong { color: #4caf50; }

.step-current {
    text-align: center; padding: 10px 8px;
    border-radius: 8px; border: 2px solid;
}
.step-current strong { color: white; }

.step-future {
    text-align: center; padding: 10px 8px;
    background: #f5f5f5; border-radius: 8px;
    border: 2px solid #e0e0e0;
}
.step-future strong { color: #bbb; }

/* ── Tweaks to default Streamlit ──────────────────────────────── */
/* Tighten metric spacing */
[data-testid="stMetric"] {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 8px;
    padding: 12px 16px;
}
[data-testid="stMetric"] label {
    color: #888 !important;
    font-size: 12px !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Dataframe header color */
[data-testid="stDataFrame"] th {
    background-color: #1f77b4 !important;
    color: white !important;
}
</style>
"""


def inject_css():
    """Inject global CSS once per page render."""
    st.markdown(_CSS, unsafe_allow_html=True)


def status_badge(status: str) -> str:
    """Return HTML for a colored status badge."""
    color = STATUS_COLORS.get(status, "#9e9e9e")
    label = STATUS_LABELS.get(status, status)
    return (
        f'<span class="status-badge" style="background-color:{color};">'
        f'{label}</span>'
    )


def pipeline_card(count: int, label: str, color: str) -> str:
    """Return HTML for a pipeline metric card."""
    return (
        f'<div class="pipeline-card" style="border-left-color:{color};">'
        f'<div class="count" style="color:{color};">{count}</div>'
        f'<div class="label">{label}</div></div>'
    )


def section_header(text: str):
    """Render a styled section header."""
    st.markdown(f'<div class="section-header">{text}</div>', unsafe_allow_html=True)
