"""
CookieJar Bot — Admin Store
Manages the dynamic admin list at runtime.

Two tiers:
  SUPER_ADMIN  — set via ADMIN_USER_IDS env var; cannot be removed at runtime;
                 the only tier that can add/remove other admins.
  ADMIN        — granted at runtime via /admin add; stored in admins.json;
                 can use all admin commands but cannot manage other admins.

Storage: <runtime_dir>/admins.json
  {
    "admins": [
      {
        "user_id": 123456789,
        "username": "alice",          // may be null if not available
        "added_by": 987654321,        // super-admin user_id
        "added_at": "2026-05-16T...",
        "note": ""                    // optional label
      }
    ]
  }

The env-var ADMIN_USER_IDS list is the immutable super-admin seed.
admins.json holds only the dynamically-added admins.
is_admin() returns True for BOTH tiers.
is_super_admin() returns True only for the env-var tier.

is_admin() uses a 60-second in-memory cache to avoid a disk read on every
permission check. The cache is invalidated immediately on add/remove.

After every add/remove, admins.json is immediately pushed to GitHub so
changes are persisted and visible to other bot instances.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from . import config
from .utils import now_iso as _now_iso

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory cache for the dynamic admin list
# ---------------------------------------------------------------------------

_CACHE_TTL = 60  # seconds

_cache_data: Optional[dict] = None
_cache_ts: float = 0.0


def _invalidate_cache() -> None:
    global _cache_data, _cache_ts
    _cache_data = None
    _cache_ts = 0.0


# ---------------------------------------------------------------------------
# Path
# ---------------------------------------------------------------------------

def _store_path() -> Path:
    return config.RUNTIME_DIR / "admins.json"


# ---------------------------------------------------------------------------
# Low-level I/O
# ---------------------------------------------------------------------------

def _load() -> dict:
    """
    Load admins.json from disk, with a 60-second in-memory cache.
    Cache is invalidated immediately on add/remove.
    """
    global _cache_data, _cache_ts
    now = time.monotonic()
    if _cache_data is not None and (now - _cache_ts) < _CACHE_TTL:
        return _cache_data

    p = _store_path()
    if p.exists():
        try:
            _cache_data = json.loads(p.read_text(encoding="utf-8"))
            _cache_ts = now
            return _cache_data
        except Exception as exc:
            log.error("Failed to read admins.json: %s", exc)

    _cache_data = {"admins": []}
    _cache_ts = now
    return _cache_data


def _save(data: dict) -> None:
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    _invalidate_cache()


def _push_to_github() -> None:
    """Best-effort push of admins.json to GitHub. Non-fatal on failure."""
    try:
        from . import github_sync
        github_sync.push_admins_to_github()
    except Exception as exc:
        log.warning("Failed to push admins.json to GitHub (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_super_admin(user_id: int) -> bool:
    """True if the user is in the immutable ADMIN_USER_IDS env-var list."""
    return user_id in config.ADMIN_USER_IDS


def is_admin(user_id: int) -> bool:
    """
    True if the user is either a super-admin (env var) or a dynamically-added admin.
    Uses a 60-second in-memory cache — no disk read on every permission check.
    """
    if is_super_admin(user_id):
        return True
    data = _load()
    return any(entry["user_id"] == user_id for entry in data.get("admins", []))


def add_admin(
    user_id: int,
    added_by: int,
    username: Optional[str] = None,
    note: str = "",
) -> dict:
    """
    Grant admin privileges to user_id.
    Returns {"success": bool, "reason": str}.
    Only super-admins can call this (enforced in the handler, not here).
    Invalidates the cache and immediately pushes admins.json to GitHub on success.
    """
    if is_super_admin(user_id):
        return {"success": False, "reason": "That user is already a super-admin (env var)."}

    data = _load()
    admins = data.setdefault("admins", [])

    # Check for duplicate
    for entry in admins:
        if entry["user_id"] == user_id:
            return {"success": False, "reason": f"User {user_id} is already an admin."}

    entry = {
        "user_id": user_id,
        "username": username,
        "added_by": added_by,
        "added_at": _now_iso(),
        "note": note,
    }
    admins.append(entry)
    _save(data)       # also invalidates cache
    _push_to_github()
    log.info("Admin added: user_id=%s username=%s by=%s", user_id, username, added_by)
    return {"success": True, "reason": "Admin added."}


def remove_admin(user_id: int, removed_by: int) -> dict:
    """
    Revoke admin privileges from user_id.
    Returns {"success": bool, "reason": str}.
    Cannot remove super-admins (env-var tier).
    Invalidates the cache and immediately pushes admins.json to GitHub on success.
    """
    if is_super_admin(user_id):
        return {
            "success": False,
            "reason": "Cannot remove a super-admin. Edit ADMIN_USER_IDS in the environment.",
        }

    data = _load()
    admins = data.get("admins", [])
    original_count = len(admins)
    data["admins"] = [e for e in admins if e["user_id"] != user_id]

    if len(data["admins"]) == original_count:
        return {"success": False, "reason": f"User {user_id} is not a dynamic admin."}

    _save(data)       # also invalidates cache
    _push_to_github()
    log.info("Admin removed: user_id=%s by=%s", user_id, removed_by)
    return {"success": True, "reason": "Admin removed."}


def list_admins() -> list[dict]:
    """
    Return a combined list of all admins:
      - Super-admins from env var (marked tier='super')
      - Dynamic admins from admins.json (marked tier='admin')
    """
    result = []
    for uid in config.ADMIN_USER_IDS:
        result.append({
            "user_id": uid,
            "username": None,
            "tier": "super",
            "added_at": None,
            "note": "env var",
        })
    data = _load()
    for entry in data.get("admins", []):
        result.append({
            "user_id": entry["user_id"],
            "username": entry.get("username"),
            "tier": "admin",
            "added_at": entry.get("added_at", ""),
            "note": entry.get("note", ""),
        })
    return result
