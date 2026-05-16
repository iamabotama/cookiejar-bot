"""
CookieJar Bot — Shared utilities

Small helpers used across multiple modules.
Import from here rather than duplicating in each file.
"""

from datetime import datetime, timezone


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()
