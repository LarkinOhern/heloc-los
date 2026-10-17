"""Borrower-facing view of the application audit log.

The audit log is written for staff: it names officers, quotes engine output
and records internal notes. Borrowers get a filtered, reworded timeline
instead (finding C-01). Anything not listed here stays internal.
"""

import re

from src.config import STATUS_LABELS

_STATUS_RE = re.compile(r"(?:to|→)\s*([A-Z_]+)\.?\s*$")
_DECISION_RE = re.compile(r"decision:\s*([A-Z_]+)")
_RATE_RE = re.compile(r"Rate of ([\d.]+%)")
_EXPIRES_RE = re.compile(r"expires (\d{4}-\d{2}-\d{2})")

_DECISION_LABELS = {
    "APPROVE": "Approved",
    "APPROVE_WITH_CONDITIONS": "Approved with conditions",
    "DENY": "Not approved",
}


def _status_item(details: str) -> dict | None:
    m = _STATUS_RE.search(details)
    if not m:
        return None
    status = m.group(1)
    if status == "SUBMITTED":
        return {"title": "Application submitted",
                "detail": "We received your application and sent your initial disclosure."}
    label = STATUS_LABELS.get(status, status.replace("_", " ").title())
    return {"title": f"Status: {label}", "detail": ""}


def _decision_item(details: str) -> dict | None:
    m = _DECISION_RE.search(details)
    if not m:
        return None
    label = _DECISION_LABELS.get(m.group(1), "Decision made")
    detail = {
        "APPROVE_WITH_CONDITIONS": "See Outstanding items for anything we still need from you.",
        "DENY": "Your decision letter explains why. It is in Documents.",
        "APPROVE": "Your approval letter is in Documents.",
    }.get(m.group(1), "")
    return {"title": f"Decision: {label}", "detail": detail}


def _rate_item(details: str) -> dict:
    rate = _RATE_RE.search(details)
    exp = _EXPIRES_RE.search(details)
    parts = []
    if rate:
        parts.append(f"Your rate of {rate.group(1)} is locked")
    if exp:
        parts.append(f"until {exp.group(1)}")
    return {"title": "Rate locked", "detail": " ".join(parts) + "." if parts else ""}


def borrower_timeline(entries: list[dict]) -> list[dict]:
    """Translate audit entries into borrower-safe timeline items.

    Each item is ``{"when": iso, "title": str, "detail": str}``.
    """
    items = []
    for e in entries:
        action, details = e["action"], e.get("details") or ""
        item = None
        if action == "APPLICATION_CREATED":
            item = {"title": "Application started", "detail": ""}
        elif action == "STATUS_CHANGE":
            item = _status_item(details)
        elif action == "UNDERWRITING_DECISION":
            item = _decision_item(details)
        elif action == "RATE_LOCKED":
            item = _rate_item(details)
        elif action == "DOCUMENT_GENERATED":
            item = {"title": "New document available", "detail": "Find it under Documents."}
        elif action == "DOCUMENT_UPLOADED":
            item = {"title": "Document received", "detail": details}
        if item:
            item["when"] = e["performed_at"]
            items.append(item)
    return items
