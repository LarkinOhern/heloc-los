"""Currency, percentage, and date formatting helpers."""

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Timestamps are stored as naive UTC ISO strings and shown in Central Time.
# ZoneInfo follows daylight saving (CST UTC-6 / CDT UTC-5). On Windows the
# zone data comes from the `tzdata` package in requirements.txt.
_CENTRAL = ZoneInfo("America/Chicago")


def _to_central(dt: datetime) -> datetime:
    """Convert a naive (UTC) datetime to Central Time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_CENTRAL)


def fmt_currency(value: float) -> str:
    """Format a number as USD currency."""
    return f"${value:,.2f}"


def fmt_percent(value: float, decimals: int = 2) -> str:
    """Format a decimal or percentage value. If value < 1, treat as decimal (0.43 -> 43.00%)."""
    if value < 1:
        return f"{value * 100:.{decimals}f}%"
    return f"{value:.{decimals}f}%"


def fmt_rate(value: float) -> str:
    """Format an interest rate (already in percent form, e.g. 8.50)."""
    return f"{value:.3f}%"


def fmt_date(iso_str: str | None) -> str:
    """Format an ISO 8601 string to a readable date (Central Time)."""
    if not iso_str:
        return "--"
    try:
        dt = datetime.fromisoformat(iso_str)
        ct = _to_central(dt)
        return ct.strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return iso_str


def fmt_datetime(iso_str: str | None) -> str:
    """Format an ISO 8601 string to a readable datetime (Central Time)."""
    if not iso_str:
        return "--"
    try:
        dt = datetime.fromisoformat(iso_str)
        ct = _to_central(dt)
        return ct.strftime("%b %d, %Y %I:%M %p CT")
    except (ValueError, TypeError):
        return iso_str


def utcnow() -> datetime:
    """Current UTC time as a naive datetime, matching how timestamps are stored."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def now_utc() -> str:
    """Return current UTC time as ISO 8601 string."""
    return utcnow().isoformat()


def days_remaining(expiration_iso: str, now: datetime | None = None) -> int:
    """Whole days left until a UTC expiration, counting a partial day as a day.

    A 60-day lock taken a few seconds ago still has 60 days left; truncating
    with timedelta.days showed 59 (finding F-03).
    """
    now = now or utcnow()
    seconds = (datetime.fromisoformat(expiration_iso) - now).total_seconds()
    return max(0, math.ceil(seconds / 86400))


def md_escape(text) -> str:
    """Escape text for st.write / st.markdown.

    Streamlit treats anything between two "$" signs as LaTeX math, so a line
    like "Monthly debts: $2,000 vs. income: $5,000" lost its dollar signs and
    turned italic (finding N-01). Escape them whenever text is dynamic.
    """
    return str(text).replace("$", "\\$")


def describe_changes(changes: dict) -> str:
    """'Label: old → new' for each changed setting, joined with '; '.

    ``changes`` maps a label to a (before, after) pair of display strings.
    Unchanged settings are left out, so the audit log says what moved.
    """
    return "; ".join(
        f"{label}: {before} → {after}"
        for label, (before, after) in changes.items()
        if before != after
    )
