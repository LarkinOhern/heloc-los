"""Currency, percentage, and date formatting helpers."""

from datetime import datetime


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
    """Format an ISO 8601 string to a readable date."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%b %d, %Y")
    except (ValueError, TypeError):
        return iso_str


def fmt_datetime(iso_str: str | None) -> str:
    """Format an ISO 8601 string to a readable datetime."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%b %d, %Y %I:%M %p")
    except (ValueError, TypeError):
        return iso_str


def now_utc() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.utcnow().isoformat()
