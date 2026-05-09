"""
CookieJar Bot — Configuration
Loads all settings from environment variables with sensible defaults.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Bot identity
# ---------------------------------------------------------------------------
BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BOT_USERNAME: str = os.environ.get("TELEGRAM_BOT_USERNAME", "CookieJarBot")  # without @

# ---------------------------------------------------------------------------
# Operating mode
#   primary  — answers questions, ingests URLs, handles @mentions & commands
#   listener — silently captures admin-flagged messages and pushes to repo
# ---------------------------------------------------------------------------
BOT_MODE: str = os.environ.get("BOT_MODE", "primary").lower()

# ---------------------------------------------------------------------------
# AI backend  (xAI Grok — OpenAI-compatible)
# ---------------------------------------------------------------------------
AI_API_KEY: str = os.environ.get("GROK_API_KEY", os.environ.get("OPENAI_API_KEY", ""))
AI_BASE_URL: str = os.environ.get("AI_BASE_URL", "https://api.x.ai/v1")
AI_MODEL: str = os.environ.get("AI_MODEL", "grok-3-mini")          # fast default
AI_MODEL_HEAVY: str = os.environ.get("AI_MODEL_HEAVY", "grok-3")   # complex queries

# ---------------------------------------------------------------------------
# GitHub knowledge store
# ---------------------------------------------------------------------------
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO: str = os.environ.get("GITHUB_REPO", "iamabotama/cookiejar-bot")
GITHUB_BRANCH: str = os.environ.get("GITHUB_BRANCH", "main")

# ---------------------------------------------------------------------------
# Local cache
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent.parent
CACHE_DIR: Path = BASE_DIR / "knowledge"
ACTIVE_CACHE: Path = CACHE_DIR / "active.jsonl"
ARCHIVE_DIR: Path = CACHE_DIR / "archive"
SOURCES_DIR: Path = BASE_DIR / "sources"

# How often (seconds) the bot re-syncs the local cache from GitHub
CACHE_SYNC_INTERVAL: int = int(os.environ.get("CACHE_SYNC_INTERVAL", "1800"))  # 30 min

# Entries older than this many days are flagged as stale automatically
STALE_AFTER_DAYS: int = int(os.environ.get("STALE_AFTER_DAYS", "90"))

# ---------------------------------------------------------------------------
# Admin controls
# ---------------------------------------------------------------------------
# Comma-separated Telegram user IDs allowed to use admin commands
ADMIN_USER_IDS: list[int] = [
    int(uid.strip())
    for uid in os.environ.get("ADMIN_USER_IDS", "").split(",")
    if uid.strip().isdigit()
]

# ---------------------------------------------------------------------------
# Community identity (used in AI system prompt)
# ---------------------------------------------------------------------------
COMMUNITY_NAME: str = "Cookie Monster"
COIN_TICKER: str = "$COOK"
NETWORK_NAME: str = "CookieNet"
NETWORK_BASE: str = "Solana fork"
BOT_PERSONA: str = (
    "You are CookieJar, the official AI assistant for the Cookie Monster crypto community. "
    "You are an expert on the CookieNet blockchain (a Solana fork), the $COOK token, "
    "and everything Cookie Monster themed in this community. "
    "You answer questions ONLY based on the reference knowledge provided to you. "
    "You do NOT speculate on price movements, price targets, or investment returns. "
    "You do NOT discuss other cryptocurrencies, blockchains, or networks. "
    "If a question is outside your knowledge base, say so honestly and suggest the user "
    "check official community channels. Keep answers friendly, on-brand, and cookie-themed."
)

# ---------------------------------------------------------------------------
# Validate critical settings at import time
# ---------------------------------------------------------------------------
def validate() -> list[str]:
    """Return a list of missing critical config keys."""
    missing = []
    if not BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not AI_API_KEY:
        missing.append("GROK_API_KEY (or OPENAI_API_KEY)")
    if not GITHUB_TOKEN:
        missing.append("GITHUB_TOKEN")
    return missing
