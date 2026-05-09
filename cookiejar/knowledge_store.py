"""
CookieJar Bot — Knowledge Store
Manages the local JSONL cache, timestamped entries, stale detection, and archiving.
"""

import json
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from . import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Entry schema
# ---------------------------------------------------------------------------
# Each entry is a JSON object on a single line (JSONL) with these fields:
#   id          : str   — SHA-256 hash of (source + content)
#   source      : str   — URL, "manual_post", "admin_push", etc.
#   title       : str   — short human-readable label
#   content     : str   — the actual text content
#   ingested_at : str   — ISO-8601 UTC timestamp
#   updated_at  : str   — ISO-8601 UTC timestamp of last modification
#   status      : str   — "active" | "stale" | "archived"
#   tags        : list  — optional list of topic tags


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_id(source: str, content: str) -> str:
    raw = f"{source}::{content[:512]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Ensure directories exist
# ---------------------------------------------------------------------------
def _ensure_dirs() -> None:
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    config.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    config.SOURCES_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Read / write helpers
# ---------------------------------------------------------------------------
def _read_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    log.warning("Skipping malformed JSONL line in %s", path)
    return entries


def _write_entries(path: Path, entries: list[dict]) -> None:
    _ensure_dirs()
    with path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_active() -> list[dict]:
    """Return all active entries from the local cache."""
    return [e for e in _read_entries(config.ACTIVE_CACHE) if e.get("status") == "active"]


def add_entry(
    source: str,
    content: str,
    title: str = "",
    tags: Optional[list[str]] = None,
) -> dict:
    """
    Add a new entry (or update an existing one by source).
    Returns the entry dict.
    """
    _ensure_dirs()
    entry_id = _make_id(source, content)
    entries = _read_entries(config.ACTIVE_CACHE)

    # Check for duplicate by id
    for existing in entries:
        if existing["id"] == entry_id:
            log.info("Duplicate entry %s — skipping", entry_id)
            return existing

    entry = {
        "id": entry_id,
        "source": source,
        "title": title or source,
        "content": content,
        "ingested_at": _now_iso(),
        "updated_at": _now_iso(),
        "status": "active",
        "tags": tags or [],
    }
    entries.append(entry)
    _write_entries(config.ACTIVE_CACHE, entries)
    log.info("Added entry %s from %s", entry_id, source)
    return entry


def mark_stale(entry_id: str) -> bool:
    """Mark an entry as stale by ID. Returns True if found."""
    entries = _read_entries(config.ACTIVE_CACHE)
    found = False
    for e in entries:
        if e["id"] == entry_id:
            e["status"] = "stale"
            e["updated_at"] = _now_iso()
            found = True
    if found:
        _write_entries(config.ACTIVE_CACHE, entries)
    return found


def archive_entry(entry_id: str) -> bool:
    """
    Move an entry from active.jsonl to the monthly archive file.
    Returns True if the entry was found and moved.
    """
    entries = _read_entries(config.ACTIVE_CACHE)
    to_archive = [e for e in entries if e["id"] == entry_id]
    remaining = [e for e in entries if e["id"] != entry_id]

    if not to_archive:
        return False

    entry = to_archive[0]
    entry["status"] = "archived"
    entry["updated_at"] = _now_iso()

    # Write to monthly archive file
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    archive_path = config.ARCHIVE_DIR / f"{month_key}.jsonl"
    with archive_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    _write_entries(config.ACTIVE_CACHE, remaining)
    log.info("Archived entry %s to %s", entry_id, archive_path.name)
    return True


def auto_stale_check() -> int:
    """
    Automatically mark entries older than STALE_AFTER_DAYS as stale.
    Returns the number of entries newly marked stale.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.STALE_AFTER_DAYS)
    entries = _read_entries(config.ACTIVE_CACHE)
    count = 0
    for e in entries:
        if e.get("status") == "active":
            ingested = datetime.fromisoformat(e["ingested_at"])
            if ingested < cutoff:
                e["status"] = "stale"
                e["updated_at"] = _now_iso()
                count += 1
    if count:
        _write_entries(config.ACTIVE_CACHE, entries)
        log.info("Auto-staled %d entries", count)
    return count


def get_knowledge_context(max_chars: int = 12000) -> str:
    """
    Build a single text block from all active entries for injection into
    the AI system prompt. Truncates to max_chars to stay within token limits.
    """
    entries = load_active()
    if not entries:
        return "No knowledge entries available yet."

    parts = []
    total = 0
    for e in entries:
        block = f"[{e['title']}] (source: {e['source']}, added: {e['ingested_at'][:10]})\n{e['content']}\n"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)

    return "\n---\n".join(parts)


def list_entries(status: str = "active") -> list[dict]:
    """Return entries filtered by status."""
    return [e for e in _read_entries(config.ACTIVE_CACHE) if e.get("status") == status]


def entry_count() -> dict:
    """Return counts by status."""
    entries = _read_entries(config.ACTIVE_CACHE)
    counts: dict[str, int] = {"active": 0, "stale": 0, "archived": 0}
    for e in entries:
        s = e.get("status", "active")
        counts[s] = counts.get(s, 0) + 1
    return counts
