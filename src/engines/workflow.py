"""Workflow rules that sit on top of the status transition map.

Pure functions: callers pass in the conditions and act on the answer.
"""

# Which open condition types stop an application from entering a status.
# Funding needs every condition cleared; closing only the prior-to-closing ones
# (plus internal review items, which must be cleared before anything moves on).
_BLOCKING_TYPES = {
    "CLOSING": {"PRIOR_TO_CLOSING", "INTERNAL_REVIEW"},
    "FUNDED": {"PRIOR_TO_CLOSING", "PRIOR_TO_FUNDING", "INTERNAL_REVIEW"},
}


def blocking_conditions(target_status: str, conditions: list[dict]) -> list[dict]:
    """Open conditions that must be resolved before moving to ``target_status``."""
    types = _BLOCKING_TYPES.get(target_status, set())
    return [
        c for c in conditions
        if c["status"] == "OPEN" and c["condition_type"] in types
    ]
