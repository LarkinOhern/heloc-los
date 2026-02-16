"""Config manager — reads from DB settings table, falls back to config.py defaults.

This lets the admin page override any configurable value at runtime. The engines
and pages call get_setting() instead of importing from config.py directly.
On fresh startup, seed_settings() populates the DB from config.py defaults.
"""

import json
from src.database import get_connection
from src.utils.formatters import now_utc
from src import config


# ── All configurable keys with their config.py default values ────────────────
# Each entry: (key, default_value)
# Values are stored as JSON in the DB, so lists/dicts work fine.

SETTING_DEFAULTS = {
    # Underwriting
    "min_credit_score":     config.MIN_CREDIT_SCORE,
    "max_cltv":             config.MAX_CLTV,
    "max_dti":              config.MAX_DTI,
    "min_property_value":   config.MIN_PROPERTY_VALUE,
    "min_heloc_amount":     config.MIN_HELOC_AMOUNT,
    "max_heloc_amount":     config.MAX_HELOC_AMOUNT,
    "credit_tiers":         config.CREDIT_TIERS,

    # Pricing
    "prime_rate":           config.PRIME_RATE,
    "base_margin":          config.BASE_MARGIN,
    "fico_adjustments":     config.FICO_ADJUSTMENTS,
    "ltv_adjustments":      config.LTV_ADJUSTMENTS,
    "amount_adjustments":   config.AMOUNT_ADJUSTMENTS,
    "autopay_discount":     config.AUTOPAY_DISCOUNT,
    "rate_lock_days":       config.RATE_LOCK_DAYS,
    "rate_floor":           config.RATE_FLOOR,
    "rate_ceiling":         config.RATE_CEILING,
}


def seed_settings():
    """Populate the settings table with defaults if keys are missing."""
    conn = get_connection()
    now = now_utc()
    for key, default in SETTING_DEFAULTS.items():
        existing = conn.execute("SELECT key FROM settings WHERE key = ?", (key,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (key, json.dumps(default), now),
            )
    conn.commit()
    conn.close()


def get_setting(key: str):
    """Get a setting value from the DB, falling back to config.py default.

    Special case: 'fico_adjustments' is derived from 'credit_tiers' so they
    stay in sync. The admin edits credit_tiers (which has labels + adjustments),
    and the pricing engine reads fico_adjustments.
    """
    if key == "fico_adjustments":
        tiers = get_setting("credit_tiers")
        return [{"min_score": t["min_score"], "adjustment": t["rate_adjustment"]}
                for t in tiers]

    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row:
        return json.loads(row["value"])
    return SETTING_DEFAULTS.get(key)


def set_setting(key: str, value):
    """Write a setting value to the DB."""
    conn = get_connection()
    now = now_utc()
    conn.execute(
        """INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = ?""",
        (key, json.dumps(value), now, json.dumps(value), now),
    )
    conn.commit()
    conn.close()


def get_all_settings() -> dict:
    """Get all settings as a dict."""
    conn = get_connection()
    rows = conn.execute("SELECT key, value, updated_at FROM settings").fetchall()
    conn.close()
    result = {}
    for row in rows:
        result[row["key"]] = {
            "value": json.loads(row["value"]),
            "updated_at": row["updated_at"],
        }
    return result


def reset_setting(key: str):
    """Reset a setting to its config.py default."""
    default = SETTING_DEFAULTS.get(key)
    if default is not None:
        set_setting(key, default)


def reset_all_settings():
    """Reset all settings to config.py defaults."""
    for key, default in SETTING_DEFAULTS.items():
        set_setting(key, default)
