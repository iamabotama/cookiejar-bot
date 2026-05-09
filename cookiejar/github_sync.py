"""
CookieJar Bot — GitHub Sync
Pushes the local knowledge cache to GitHub and pulls updates from it.
"""

import base64
import json
import logging
import time
from pathlib import Path
from typing import Optional

import requests

from . import config

log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"


def _headers() -> dict:
    return {
        "Authorization": f"token {config.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get_file_sha(path_in_repo: str) -> Optional[str]:
    """Get the current SHA of a file in the repo (needed for updates)."""
    url = f"{GITHUB_API}/repos/{config.GITHUB_REPO}/contents/{path_in_repo}"
    r = requests.get(url, headers=_headers(), params={"ref": config.GITHUB_BRANCH}, timeout=15)
    if r.status_code == 200:
        return r.json().get("sha")
    return None


def push_file(local_path: Path, repo_path: str, commit_message: str) -> bool:
    """
    Push a local file to the GitHub repo.
    Creates or updates the file as needed.
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
        log.info("Pushed %s → %s", local_path.name, repo_path)
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
        log.info("Pulled %s → %s", repo_path, local_path.name)
        return True
    elif r.status_code == 404:
        log.info("Remote file %s not found — nothing to pull", repo_path)
        return False
    else:
        log.error("Failed to pull %s: %s", repo_path, r.status_code)
        return False


def sync_knowledge_to_github() -> bool:
    """Push the active knowledge cache and all archive files to GitHub."""
    success = True

    # Push active cache
    if config.ACTIVE_CACHE.exists():
        ok = push_file(
            config.ACTIVE_CACHE,
            "knowledge/active.jsonl",
            "chore: sync active knowledge cache",
        )
        success = success and ok

    # Push archive files
    if config.ARCHIVE_DIR.exists():
        for archive_file in config.ARCHIVE_DIR.glob("*.jsonl"):
            ok = push_file(
                archive_file,
                f"knowledge/archive/{archive_file.name}",
                f"chore: sync archive {archive_file.name}",
            )
            success = success and ok

    return success


def sync_knowledge_from_github() -> bool:
    """Pull the active knowledge cache from GitHub to refresh the local copy."""
    return pull_file("knowledge/active.jsonl", config.ACTIVE_CACHE)


def push_source_file(source_id: str, content: str) -> bool:
    """Save a raw ingested source to the sources/ directory in the repo."""
    local_path = config.SOURCES_DIR / f"{source_id}.txt"
    local_path.write_text(content, encoding="utf-8")
    return push_file(
        local_path,
        f"sources/{source_id}.txt",
        f"feat: add source {source_id}",
    )


# ---------------------------------------------------------------------------
# Background sync loop (run in a thread)
# ---------------------------------------------------------------------------
_stop_sync = False


def start_sync_loop() -> None:
    """Periodically sync knowledge from GitHub. Runs in a background thread."""
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
