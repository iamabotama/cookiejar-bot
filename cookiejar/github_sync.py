"""
CookieJar Bot — GitHub Sync

Pushes the local knowledge cache to GitHub and pulls updates from it.

Sync scope:
  PUSH: active.jsonl, archive/*.jsonl, knowledge/topics/*.jsonl,
        knowledge/index.json, admins.json
  PULL: active.jsonl, cookiechain.json, admins.json
        → after pull, topic files are rebuilt from active.jsonl

cookiechain.json is pull-only (managed in the repo, not by the bot).
admins.json is both pushed (when admins are added/removed) and pulled
(so a multi-instance deployment stays in sync).
"""

import base64
import logging
import time
from pathlib import Path
from typing import Optional

import requests

from . import config

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


# ---------------------------------------------------------------------------
# Low-level GitHub API helpers
# ---------------------------------------------------------------------------

def _headers() -> dict:
    return {
        "Authorization": f"token {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get_file_sha(path_in_repo: str) -> Optional[str]:
    """Get the current SHA of a file in the repo (required for updates)."""
    url = f"{GITHUB_API}/repos/{config.GITHUB_REPO}/contents/{path_in_repo}"
    r = requests.get(url, headers=_headers(), params={"ref": config.GITHUB_BRANCH}, timeout=15)
    if r.status_code == 200:
        return r.json().get("sha")
    return None


def push_file(local_path: Path, repo_path: str, commit_message: str) -> bool:
    """
    Push a local file to the GitHub repo (create or update).
    Returns True on success.
    """
    if not config.GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN not set — skipping push")
        return False
    if not local_path.exists():
        log.warning("Local file %s does not exist — skipping push", local_path)
        return False

    content = local_path.read_bytes()
    encoded = base64.b64encode(content).decode()
    sha = _get_file_sha(repo_path)

    payload: dict = {
        "message": commit_message,
        "content": encoded,
        "branch": config.GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha

    url = f"{GITHUB_API}/repos/{config.GITHUB_REPO}/contents/{repo_path}"
    r = requests.put(url, headers=_headers(), json=payload, timeout=30)

    if r.status_code in (200, 201):
        log.info("Pushed %s -> %s", local_path.name, repo_path)
        return True
    else:
        log.error("Failed to push %s: %s %s", repo_path, r.status_code, r.text[:200])
        return False


def pull_file(repo_path: str, local_path: Path) -> bool:
    """
    Pull a file from the GitHub repo and save it locally.
    Returns True on success.
    """
    if not config.GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN not set — skipping pull")
        return False

    url = f"{GITHUB_API}/repos/{config.GITHUB_REPO}/contents/{repo_path}"
    r = requests.get(url, headers=_headers(), params={"ref": config.GITHUB_BRANCH}, timeout=15)

    if r.status_code == 200:
        data = r.json()
        content = base64.b64decode(data["content"])
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(content)
        log.info("Pulled %s -> %s", repo_path, local_path.name)
        return True
    elif r.status_code == 404:
        log.info("Remote file %s not found — nothing to pull", repo_path)
        return False
    else:
        log.error("Failed to pull %s: %s", repo_path, r.status_code)
        return False


# ---------------------------------------------------------------------------
# High-level sync operations
# ---------------------------------------------------------------------------

def sync_knowledge_to_github() -> bool:
    """
    Push the full knowledge state to GitHub:
      - knowledge/active.jsonl
      - knowledge/archive/*.jsonl
      - knowledge/topics/*.jsonl
      - knowledge/index.json
      - admins.json
    """
    success = True

    # active.jsonl
    if config.ACTIVE_CACHE.exists():
        success &= push_file(
            config.ACTIVE_CACHE,
            "knowledge/active.jsonl",
            "chore: sync active knowledge cache",
        )

    # archive files
    if config.ARCHIVE_DIR.exists():
        for f in config.ARCHIVE_DIR.glob("*.jsonl"):
            success &= push_file(f, f"knowledge/archive/{f.name}", f"chore: sync archive {f.name}")

    # topic files
    topics_dir = config.CACHE_DIR / "topics"
    if topics_dir.exists():
        for f in topics_dir.glob("*.jsonl"):
            success &= push_file(f, f"knowledge/topics/{f.name}", f"chore: sync topic {f.name}")

    # index.json
    index_file = config.CACHE_DIR / "index.json"
    if index_file.exists():
        success &= push_file(index_file, "knowledge/index.json", "chore: sync knowledge index")

    # admins.json (runtime admin list)
    admins_file = config.RUNTIME_DIR / "admins.json"
    if admins_file.exists():
        success &= push_file(admins_file, "admins.json", "chore: sync admin list")

    return success


def sync_knowledge_from_github() -> bool:
    """
    Pull the latest knowledge state from GitHub:
      - knowledge/active.jsonl  → rebuild topic files locally after pull
      - cookiechain.json        → read-only config managed in the repo
      - admins.json             → keep admin list in sync across instances

    Topic files are rebuilt from active.jsonl after each pull so the
    local topic cache always reflects the canonical active.jsonl.
    """
    success = True

    # Pull active.jsonl
    pulled = pull_file("knowledge/active.jsonl", config.ACTIVE_CACHE)
    success &= pulled

    # Rebuild topic files from the freshly-pulled active.jsonl
    if pulled:
        try:
            from . import knowledge_store
            knowledge_store.rebuild_topic_files()
            log.info("Topic files rebuilt after pull")
        except Exception as exc:
            log.error("Failed to rebuild topic files after pull: %s", exc)

    # Pull cookiechain.json (repo-managed, pull-only)
    chain_json = config.RUNTIME_DIR / "cookiechain.json"
    success &= pull_file("cookiechain.json", chain_json)

    # Pull admins.json (bi-directional — keeps multi-instance in sync)
    admins_json = config.RUNTIME_DIR / "admins.json"
    pull_file("admins.json", admins_json)   # 404 on first run is fine — not fatal

    return success


def push_admins_to_github() -> bool:
    """
    Push only admins.json to GitHub.
    Called immediately after add_admin / remove_admin so the change
    is persisted to the repo without waiting for the next full sync.
    """
    admins_file = config.RUNTIME_DIR / "admins.json"
    return push_file(admins_file, "admins.json", "chore: update admin list")


def push_source_file(source_id: str, content: str) -> bool:
    """Save a raw ingested source to the sources/ directory in the repo."""
    local_path = config.SOURCES_DIR / f"{source_id}.txt"
    local_path.write_text(content, encoding="utf-8")
    return push_file(local_path, f"sources/{source_id}.txt", f"feat: add source {source_id}")


# ---------------------------------------------------------------------------
# Background sync loop (runs in a daemon thread)
# ---------------------------------------------------------------------------

_stop_sync = False


def start_sync_loop() -> None:
    """Periodically pull knowledge from GitHub. Runs in a background thread."""
    global _stop_sync
    _stop_sync = False
    log.info("GitHub sync loop started (interval: %ds)", config.CACHE_SYNC_INTERVAL)
    while not _stop_sync:
        try:
            sync_knowledge_from_github()
        except Exception as exc:
            log.error("Sync loop error: %s", exc)
        time.sleep(config.CACHE_SYNC_INTERVAL)


def stop_sync_loop() -> None:
    global _stop_sync
    _stop_sync = True
