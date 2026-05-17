"""
CookieJar Bot — Knowledge Store (v2, topic-based)

Storage layout:
  knowledge/
    active.jsonl          <- source of truth for admin commands (/listentries etc.)
    index.json            <- topic registry: name, keywords, file, entry_count
    topics/
      general.jsonl       <- catch-all
      chain.jsonl         <- architecture, consensus, validators, bridge
      token.jsonl         <- $COOK, tokenomics, staking
      community.jsonl     <- Telegram groups (whales, memes, devs, general)
      dev.jsonl           <- developer guide, SDK, RPC, contracts
      faq.jsonl           <- FAQ, getting started, wallets
      lore.jsonl          <- origin story, history, culture
      links.jsonl         <- official websites, docs, explorer, bridge URLs
      socials.jsonl       <- official X/Twitter accounts, community Twitter
    archive/
      YYYY-MM.jsonl       <- monthly archives (unchanged)

Write path:  add_entry() -> active.jsonl  +  matching topic file
Read path:   classify question -> load 1-2 topic files (not the whole KB)
Admin path:  list_entries / mark_stale / archive_entry all use active.jsonl
"""

import json
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from . import config
from .utils import now_iso as _now_iso

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Topic definitions — order matters for classification priority
# ---------------------------------------------------------------------------

TOPICS: list[dict] = [
    {
        "name": "lore",
        "description": "Cookie Chain origin story, history, culture, lore, Gorboy/Goyboy meme token history",
        "keywords": [
            "origin", "story", "history", "lore", "culture", "recipe",
            "cookie recipe", "founded", "beginning", "birth", "genesis",
            "cookie boy", "cookie chain story",
            "gorboy", "goyboy", "gor-boy", "gorbagio",
        ],
        "tags": ["lore", "origin", "history", "culture", "cookie-chain"],
    },
    {
        "name": "chain",
        "description": "Cookie Chain blockchain architecture, consensus, validators, bridge",
        "keywords": [
            "architecture", "consensus", "validator", "validators", "bridge",
            "chain", "blockchain", "network", "node", "block", "transaction",
            "cookiechain", "cookie chain", "layer", "protocol",
            "break gorbagana", "gorbagana",
        ],
        "tags": ["chain", "architecture", "consensus", "validator", "bridge", "web"],
    },
    {
        "name": "token",
        "description": "$COOK token, tokenomics, staking, contract address, Gorboy/GORBOY token whitepaper and tokenomics",
        "keywords": [
            "$cook", "tokenomics", "staking", "stake",
            "supply", "allocation", "airdrop", "reward",
            "emission", "burn",
            "gorboy", "goyboy", "gorboy whitepaper", "gorboy token", "gorboy tokenomics",
        ],
        "tags": ["token", "cook", "tokenomics", "staking", "ca"],
    },
    {
        "name": "community",
        "description": "Telegram groups: whales, memes, devs, general, announcements",
        "keywords": [
            "telegram", "group", "community", "chat", "whales", "meme",
            "memes", "devs", "developers", "general", "announcements",
            "join", "t.me", "tg", "channel",
        ],
        "tags": ["community", "telegram", "tg", "group"],
    },
    {
        "name": "dev",
        "description": "Developer guide, SDK, RPC, smart contracts, API",
        "keywords": [
            "developer", "sdk", "api", "rpc", "smart contract", "deploy",
            "build", "dapp", "integration", "endpoint", "playground",
            "trading api", "cookiescan api",
        ],
        "tags": ["dev", "developer", "sdk", "api", "rpc"],
    },
    {
        "name": "faq",
        "description": "FAQ, getting started, wallets, how-to guides",
        "keywords": [
            "faq", "getting started", "wallet", "how to", "how do",
            "what is", "guide", "tutorial", "setup", "install", "metamask",
            "phantom", "connect", "beginner", "new user",
        ],
        "tags": ["faq", "getting-started", "wallet", "guide"],
    },
    {
        "name": "links",
        "description": "Official websites, docs, explorer, bridge, swap URLs",
        "keywords": [
            "website", "site", "url", "link", "cookiescan", "cookoven",
            "candyshop", "swap", "explorer", "docs", "documentation",
            "gorbagana.cash", "bridge", "multisig", "cookiequads",
        ],
        "tags": ["links", "website", "url", "official"],
    },
    {
        "name": "socials",
        "description": "Official X/Twitter accounts, community Twitter handles",
        "keywords": [
            "twitter", "x.com", "tweet", "social", "follow", "handle",
            "account", "@thecookiechain", "official twitter",
        ],
        "tags": ["socials", "twitter", "x", "social"],
    },
    {
        "name": "general",
        "description": "General Cookie Chain information and catch-all",
        "keywords": [],
        "tags": [],
    },
]

_TOPIC_BY_NAME: dict[str, dict] = {t["name"]: t for t in TOPICS}

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _topics_dir() -> Path:
    d = config.CACHE_DIR / "topics"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _topic_path(name: str) -> Path:
    return _topics_dir() / f"{name}.jsonl"

def _index_path() -> Path:
    return config.CACHE_DIR / "index.json"

# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------

def _build_default_index() -> dict:
    return {
        "version": 2,
        "topics": {
            t["name"]: {
                "name": t["name"],
                "description": t["description"],
                "file": f"topics/{t['name']}.jsonl",
                "entry_count": 0,
            }
            for t in TOPICS
        },
    }

def _load_index() -> dict:
    p = _index_path()
    if p.exists():
        try:
            idx = json.loads(p.read_text(encoding="utf-8"))
            # Merge in any missing topics
            for t in TOPICS:
                if t["name"] not in idx.get("topics", {}):
                    idx.setdefault("topics", {})[t["name"]] = {
                        "name": t["name"],
                        "description": t["description"],
                        "file": f"topics/{t['name']}.jsonl",
                        "entry_count": 0,
                    }
            return idx
        except Exception:
            pass
    return _build_default_index()

def _save_index(index: dict) -> None:
    _index_path().write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

def _increment_topic_count(topic_name: str, delta: int = 1) -> None:
    idx = _load_index()
    if topic_name in idx["topics"]:
        idx["topics"][topic_name]["entry_count"] = max(
            0, idx["topics"][topic_name].get("entry_count", 0) + delta
        )
    _save_index(idx)

def rebuild_index_counts() -> None:
    """Recount entries in every topic file and update index.json."""
    idx = _load_index()
    for name in idx["topics"]:
        path = _topic_path(name)
        count = 0
        if path.exists():
            count = sum(
                1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
            )
        idx["topics"][name]["entry_count"] = count
    _save_index(idx)
    log.info("Rebuilt index counts: %s", {k: v["entry_count"] for k, v in idx["topics"].items()})

# ---------------------------------------------------------------------------
# Topic classification (rule-based, no LLM needed)
# ---------------------------------------------------------------------------

def classify_to_topic(entry: dict) -> str:
    """
    Classify an entry into a topic based on its tags, source URL, and title.
    Returns the topic name string.
    """
    tags = [t.lower() for t in entry.get("tags", [])]
    source = entry.get("source", "").lower()
    title = entry.get("title", "").lower()
    content_snippet = entry.get("content", "")[:500].lower()
    combined = " ".join(tags) + " " + source + " " + title + " " + content_snippet

    # Hard-coded source-pattern overrides (checked before keyword matching)
    if "t.me/" in source or "telegram.me/" in source:
        return "community"
    if source.startswith("https://x.com/") or source.startswith("https://twitter.com/"):
        return "socials"

    for topic in TOPICS:
        if topic["name"] == "general":
            continue
        if any(tag in tags for tag in topic["tags"]):
            return topic["name"]
        if any(kw in combined for kw in topic["keywords"]):
            return topic["name"]

    return "general"


def classify_question_to_topics(question: str) -> list[str]:
    """
    Classify a user question into 1-3 topic names using keyword matching.
    Returns a list of topic names to load (most relevant first).
    Always includes 'general' as a fallback.
    """
    q = question.lower()
    matched: list[str] = []

    for topic in TOPICS:
        if topic["name"] == "general":
            continue
        if any(kw in q for kw in topic["keywords"]):
            matched.append(topic["name"])
        if len(matched) >= 2:
            break

    if not matched:
        matched = ["general"]
    elif "general" not in matched:
        matched.append("general")

    return matched[:3]

# ---------------------------------------------------------------------------
# Low-level I/O
# ---------------------------------------------------------------------------

def _make_id(source: str, content: str) -> str:
    raw = f"{source}::{content[:512]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def _read_entries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                log.warning("Skipping malformed JSONL line in %s", path.name)
    return entries

def _write_entries(path: Path, entries: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
        encoding="utf-8",
    )

def _append_entry_to_file(path: Path, entry: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

# ---------------------------------------------------------------------------
# Public API — write path
# ---------------------------------------------------------------------------

def add_entry(
    source: str,
    content: str,
    title: str = "",
    tags: Optional[list[str]] = None,
    priority: str = "normal",
    added_by: Optional[str] = None,
) -> dict:
    """
    Add a new knowledge entry.
    Writes to active.jsonl (source of truth) AND the matching topic file.
    Returns the created entry dict.
    Skips duplicates by ID.
    """
    _ensure_dirs()
    tags = tags or []
    entry_id = _make_id(source, content)

    # Check for duplicate in active.jsonl
    existing = _read_entries(config.ACTIVE_CACHE)
    for e in existing:
        if e["id"] == entry_id:
            log.info("Duplicate entry %s — skipping", entry_id)
            return e

    entry = {
        "id": entry_id,
        "source": source,
        "title": title or source,
        "content": content,
        "tags": tags,
        "priority": priority,
        "added_by": added_by or "",
        "status": "active",
        "ingested_at": _now_iso(),
        "updated_at": _now_iso(),
    }

    # Classify topic and write it into the entry before saving
    topic = classify_to_topic(entry)
    entry["topic"] = topic

    # Write to active.jsonl
    _append_entry_to_file(config.ACTIVE_CACHE, entry)

    # Write to topic file
    _append_entry_to_file(_topic_path(topic), entry)
    _increment_topic_count(topic)

    log.info("Added entry %s -> topic=%s title=%r", entry_id, topic, (title or source)[:60])
    return entry

# ---------------------------------------------------------------------------
# Public API — read path
# ---------------------------------------------------------------------------

def load_active() -> list[dict]:
    """Return all active entries from active.jsonl."""
    return [e for e in _read_entries(config.ACTIVE_CACHE) if e.get("status") == "active"]

def load_topic(topic_name: str) -> list[dict]:
    """Load all entries from a specific topic file."""
    return _read_entries(_topic_path(topic_name))

def load_topics_for_question(question: str) -> list[dict]:
    """
    Classify the question, load the relevant topic files, and return
    a deduplicated list of active entries sorted by priority then date.
    """
    topics = classify_question_to_topics(question)
    log.info("Question topics: %s for %r", topics, question[:80])

    seen_ids: set[str] = set()
    entries: list[dict] = []

    for topic_name in topics:
        for e in load_topic(topic_name):
            if e.get("status") == "active" and e["id"] not in seen_ids:
                seen_ids.add(e["id"])
                entries.append(e)

    priority_order = {"pinned": 0, "high": 1, "normal": 2, "low": 3}
    entries.sort(
        key=lambda e: (
            priority_order.get(e.get("priority", "normal"), 2),
            e.get("ingested_at", ""),
        )
    )
    return entries

def get_knowledge_context(max_chars: int = 12000) -> str:
    """
    Build a context block from ALL active entries (used by /updates, admin tools).
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

def get_topic_knowledge_context(question: str, max_chars: int = 8000) -> str:
    """
    Build a focused context block from only the topic-relevant entries.
    Used by answer_question() for efficient, targeted responses.
    """
    entries = load_topics_for_question(question)
    if not entries:
        return "No relevant knowledge entries found."
    parts = []
    total = 0
    for e in entries:
        block = f"[{e['title']}] (source: {e['source']}, added: {e['ingested_at'][:10]})\n{e['content']}\n"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n---\n".join(parts)

# ---------------------------------------------------------------------------
# Public API — admin commands (all use active.jsonl)
# ---------------------------------------------------------------------------

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

def delete_last_entry(
    requesting_user_id,
    is_admin: bool,
    window_seconds: int = 300,
) -> dict:
    """
    Delete the most recently ingested active entry if within the time window
    AND the requester is either an admin OR the original poster.
    Returns {"success": bool, "entry": dict|None, "reason": str}
    """
    entries = _read_entries(config.ACTIVE_CACHE)
    active = [e for e in entries if e.get("status") == "active"]
    if not active:
        return {"success": False, "entry": None, "reason": "No active entries to delete."}
    last = max(active, key=lambda e: e.get("ingested_at", ""))
    ingested = datetime.fromisoformat(last["ingested_at"])
    age_seconds = (datetime.now(timezone.utc) - ingested).total_seconds()
    if age_seconds > window_seconds:
        mins = int(window_seconds / 60)
        return {
            "success": False,
            "entry": last,
            "reason": f"Last entry is older than {mins} minutes — cannot delete.",
        }
    if not is_admin and last.get("added_by") != str(requesting_user_id):
        return {
            "success": False,
            "entry": last,
            "reason": "You can only delete entries you added yourself.",
        }
    remaining = [e for e in entries if e["id"] != last["id"]]
    _write_entries(config.ACTIVE_CACHE, remaining)
    _remove_from_topic(last)
    log.info("Deleted last entry %s by user %s", last["id"], requesting_user_id)
    return {"success": True, "entry": last, "reason": "Deleted."}

def _remove_from_topic(entry: dict) -> None:
    """Remove a single entry from its topic file (best-effort)."""
    topic = classify_to_topic(entry)
    path = _topic_path(topic)
    if not path.exists():
        return
    entries = _read_entries(path)
    remaining = [e for e in entries if e["id"] != entry["id"]]
    if len(remaining) < len(entries):
        _write_entries(path, remaining)
        _increment_topic_count(topic, delta=-1)

def mark_stale(entry_id: str) -> bool:
    """Mark an entry as stale by ID in active.jsonl. Returns True if found."""
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
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    archive_path = config.ARCHIVE_DIR / f"{month_key}.jsonl"
    config.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
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
            raw_ts = e.get("ingested_at")
            if not raw_ts:
                log.warning("auto_stale_check: entry %s missing ingested_at — skipping", e.get("id", "?"))
                continue
            ingested = datetime.fromisoformat(raw_ts)
            if ingested < cutoff:
                e["status"] = "stale"
                e["updated_at"] = _now_iso()
                count += 1
    if count:
        _write_entries(config.ACTIVE_CACHE, entries)
        log.info("Auto-staled %d entries", count)
    return count

# ---------------------------------------------------------------------------
# Sync cookiechain.json -> links.jsonl + socials.jsonl + community.jsonl
# ---------------------------------------------------------------------------

def sync_cookiechain(cookiechain_path: Optional[Path] = None) -> dict:
    """
    Read cookiechain.json and upsert entries into links.jsonl, socials.jsonl,
    and community.jsonl so the KB stays in sync with /tg, /x, /links commands.
    Returns {"links": int, "socials": int, "community": int} counts of upserted entries.
    """
    if cookiechain_path is None:
        for candidate in [
            config.RUNTIME_DIR / "cookiechain.json",
            config.BUNDLE_DIR / "cookiechain.json",
        ]:
            if candidate.exists():
                cookiechain_path = candidate
                break
    if cookiechain_path is None or not cookiechain_path.exists():
        log.warning("cookiechain.json not found — skipping sync")
        return {"links": 0, "socials": 0, "community": 0}

    try:
        data = json.loads(cookiechain_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.error("Failed to read cookiechain.json: %s", exc)
        return {"links": 0, "socials": 0, "community": 0}

    counts = {"links": 0, "socials": 0, "community": 0}

    # Official links
    for item in data.get("links", []):
        if item.get("url") and item.get("label"):
            _upsert_topic_entry(
                topic="links",
                source=item["url"],
                title=item["label"],
                content=f"Official Cookie Chain link: {item['label']} — {item['url']}",
                tags=["links", "official", "website"],
                priority="high",
            )
            counts["links"] += 1

    # Official Twitter/X
    twitter_url = data.get("twitter_url", "")
    if twitter_url:
        _upsert_topic_entry(
            topic="socials",
            source=twitter_url,
            title="Cookie Chain — Official X/Twitter",
            content=f"Official Cookie Chain X/Twitter account: {twitter_url}",
            tags=["socials", "twitter", "official"],
            priority="high",
        )
        counts["socials"] += 1

    # Community Twitter accounts
    for ct in data.get("community_twitter", []):
        if ct.get("url"):
            _upsert_topic_entry(
                topic="socials",
                source=ct["url"],
                title=ct.get("label", "Community Twitter"),
                content=f"Community Twitter account: {ct.get('label', '')} — {ct['url']}",
                tags=["socials", "twitter", "community"],
                priority="normal",
            )
            counts["socials"] += 1

    # Official Telegram
    telegram_url = data.get("telegram_url", "")
    if telegram_url:
        _upsert_topic_entry(
            topic="community",
            source=telegram_url,
            title="Cookie Chain — Official Telegram Group",
            content=f"Official Cookie Chain Telegram community group: {telegram_url}",
            tags=["community", "telegram", "official"],
            priority="high",
        )
        counts["community"] += 1

    # Community Telegram groups
    for grp in data.get("telegram_groups", []):
        if grp.get("url"):
            _upsert_topic_entry(
                topic="community",
                source=grp["url"],
                title=grp.get("label", "Community Telegram Group"),
                content=(
                    f"Cookie Chain Telegram group: {grp.get('label', '')} — "
                    f"{grp.get('description', '')} — {grp['url']}"
                ),
                tags=["community", "telegram", "group"],
                priority="normal",
            )
            counts["community"] += 1

    rebuild_index_counts()
    log.info("sync_cookiechain complete: %s", counts)
    return counts


def _upsert_topic_entry(
    topic: str,
    source: str,
    title: str,
    content: str,
    tags: list,
    priority: str = "normal",
) -> None:
    """
    Write an entry to a topic file, skipping if the source URL already exists.
    Does NOT write to active.jsonl (these are sync-only entries).
    """
    path = _topic_path(topic)
    existing = _read_entries(path)
    if any(e.get("source") == source for e in existing):
        return
    entry = {
        "id": _make_id(source, content),
        "source": source,
        "title": title,
        "content": content,
        "tags": tags,
        "priority": priority,
        "added_by": "cookiechain_sync",
        "status": "active",
        "ingested_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    _append_entry_to_file(path, entry)

# ---------------------------------------------------------------------------
# Topic file rebuild  (called after a GitHub pull)
# ---------------------------------------------------------------------------

def rebuild_topic_files() -> dict:
    """
    Rebuild all topic files from scratch using active.jsonl as the source
    of truth.  Called after every GitHub pull so local topic files always
    reflect the canonical active.jsonl.

    Returns a dict mapping topic_name -> entry_count.
    """
    _ensure_dirs()

    # Wipe existing topic files
    for f in _topics_dir().glob("*.jsonl"):
        f.unlink()

    # Distribute every active entry into the matching topic file.
    # Honour the topic already stored on the entry; only re-classify
    # if the field is absent (e.g. entries saved before the topic system).
    counts: dict[str, int] = {}
    for entry in _read_entries(config.ACTIVE_CACHE):
        if entry.get("status") != "active":
            continue
        topic = entry.get("topic") or classify_to_topic(entry)
        _append_entry_to_file(_topic_path(topic), entry)
        counts[topic] = counts.get(topic, 0) + 1

    # Rebuild index.json from fresh counts
    # Use .items() to get topic_name directly — avoids KeyError if a topic
    # object in index.json is missing the 'name' field (e.g. after a manual edit).
    # Write both 'entry_count' and 'count' for compatibility with any reader
    # that expects either field name.
    index = _load_index()
    for topic_name, t in index["topics"].items():
        n = counts.get(topic_name, 0)
        t["entry_count"] = n
        t["count"] = n
    _save_index(index)

    log.info("Topic files rebuilt from active.jsonl: %s", counts)
    return counts


# ---------------------------------------------------------------------------
# Ensure knowledge directory structure exists on import
# ---------------------------------------------------------------------------

def _ensure_dirs() -> None:
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _topics_dir()
    config.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    config.SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    if not _index_path().exists():
        _save_index(_build_default_index())

_ensure_dirs()
