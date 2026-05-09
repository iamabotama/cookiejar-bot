"""
CookieJar Bot — Web Ingestion
Scrapes a URL, extracts clean text, and adds it to the knowledge store.
"""

import hashlib
import logging
import re
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from . import knowledge_store, github_sync

log = logging.getLogger(__name__)

# Max characters to store per ingested page
MAX_CONTENT_CHARS = 8000

# Request timeout in seconds
REQUEST_TIMEOUT = 20

# Headers to mimic a real browser
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; CookieJarBot/1.0; "
        "+https://github.com/iamabotama/cookiejar-bot)"
    )
}


def _clean_text(html: str) -> str:
    """Extract readable text from HTML, stripping scripts, styles, and nav."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    # Collapse excessive whitespace
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def _url_to_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def ingest_url(url: str, tags: Optional[list[str]] = None) -> dict:
    """
    Fetch a URL, extract its text content, store it in the knowledge base,
    and push both the raw source and the updated cache to GitHub.

    Returns a result dict with keys: success, entry_id, title, char_count, error.
    """
    result = {"success": False, "entry_id": None, "title": "", "char_count": 0, "error": ""}

    # Validate URL
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        result["error"] = "Invalid URL scheme. Only http/https are supported."
        return result

    try:
        log.info("Fetching %s", url)
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        result["error"] = f"Failed to fetch URL: {exc}"
        log.error("Fetch error for %s: %s", url, exc)
        return result

    # Extract title
    soup = BeautifulSoup(resp.text, "html.parser")
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else parsed.netloc

    # Extract clean text
    content = _clean_text(resp.text)
    if not content:
        result["error"] = "No readable content found on page."
        return result

    # Truncate
    content = content[:MAX_CONTENT_CHARS]

    # Store in knowledge base
    entry = knowledge_store.add_entry(
        source=url,
        content=content,
        title=title,
        tags=tags or ["web"],
    )

    # Push raw source and updated cache to GitHub (non-blocking best-effort)
    source_id = _url_to_id(url)
    try:
        github_sync.push_source_file(source_id, f"URL: {url}\nTitle: {title}\n\n{content}")
        github_sync.sync_knowledge_to_github()
    except Exception as exc:
        log.warning("GitHub push failed (non-fatal): %s", exc)

    result.update({
        "success": True,
        "entry_id": entry["id"],
        "title": title,
        "char_count": len(content),
        "error": "",
    })
    return result


def ingest_text(
    content: str,
    source_label: str,
    title: str = "",
    tags: Optional[list[str]] = None,
) -> dict:
    """
    Directly ingest a text post (e.g., admin push or manual paste).
    Returns the same result dict as ingest_url.
    """
    result = {"success": False, "entry_id": None, "title": title, "char_count": 0, "error": ""}

    if not content.strip():
        result["error"] = "Empty content provided."
        return result

    content = content[:MAX_CONTENT_CHARS]
    entry = knowledge_store.add_entry(
        source=source_label,
        content=content,
        title=title or source_label,
        tags=tags or ["manual"],
    )

    try:
        github_sync.sync_knowledge_to_github()
    except Exception as exc:
        log.warning("GitHub push failed (non-fatal): %s", exc)

    result.update({
        "success": True,
        "entry_id": entry["id"],
        "title": entry["title"],
        "char_count": len(content),
        "error": "",
    })
    return result
