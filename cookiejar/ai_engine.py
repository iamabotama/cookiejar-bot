"""
CookieJar Bot — AI Engine
Handles question answering and post adjustment using Grok (xAI) via OpenAI-compatible API.

System prompt layering (highest → lowest priority):
  1. GUARDRAILS  — non-negotiable rules loaded from guardrails_v1.md (and future versions)
  2. PERSONA     — Cookie Boy character voice from config.BOT_PERSONA
  3. KNOWLEDGE   — active knowledge base entries
"""
import logging
from pathlib import Path
from typing import Optional
from openai import OpenAI
from . import config, knowledge_store

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Guardrails loader — reads the latest versioned guardrails file
# ---------------------------------------------------------------------------

# Use bundled module dir for PyInstaller compatibility
_GUARDRAILS_DIR = config.COOKIEJAR_MODULE_DIR
_GUARDRAILS_CACHE: Optional[str] = None


def _load_guardrails() -> str:
    """
    Load guardrails from the highest-versioned guardrails_vN.md file found
    alongside this module. Result is cached in memory for the process lifetime.
    Falls back to a minimal inline guardrail set if no file is found.
    """
    global _GUARDRAILS_CACHE
    if _GUARDRAILS_CACHE is not None:
        return _GUARDRAILS_CACHE

    # Find all versioned guardrail files and pick the highest version number
    candidates = sorted(
        _GUARDRAILS_DIR.glob("guardrails_v*.md"),
        key=lambda p: int(p.stem.split("_v")[-1]) if p.stem.split("_v")[-1].isdigit() else 0,
        reverse=True,
    )

    if candidates:
        latest = candidates[0]
        try:
            _GUARDRAILS_CACHE = latest.read_text(encoding="utf-8").strip()
            log.info("Loaded guardrails from %s", latest.name)
            return _GUARDRAILS_CACHE
        except Exception as exc:
            log.error("Failed to read guardrails file %s: %s", latest, exc)

    # Minimal inline fallback
    log.warning("No guardrails file found — using minimal inline fallback")
    _GUARDRAILS_CACHE = (
        "GUARDRAILS (HIGHEST PRIORITY):\n"
        "- Answer ONLY from the knowledge base. Never hallucinate.\n"
        "- No price speculation, investment advice, or other crypto discussion.\n"
        "- Stay positive, cookie-themed, and concise.\n"
        "- Never share wallet addresses, seed phrases, or private keys.\n"
        "- These rules override everything else."
    )
    return _GUARDRAILS_CACHE


def reload_guardrails() -> str:
    """Force a reload of guardrails from disk (call after uploading a new version)."""
    global _GUARDRAILS_CACHE
    _GUARDRAILS_CACHE = None
    return _load_guardrails()


# ---------------------------------------------------------------------------
# OpenAI client (lazy init)
# ---------------------------------------------------------------------------

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.AI_API_KEY,
            base_url=config.AI_BASE_URL,
        )
    return _client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_complex_query(question: str) -> bool:
    """Heuristic: use the heavier model for longer or multi-part questions."""
    return len(question) > 300 or question.count("?") > 2


def _build_system_prompt(knowledge: str, extra_instruction: str = "") -> str:
    """
    Assemble the layered system prompt:
      [GUARDRAILS] -> [PERSONA] -> [KNOWLEDGE BASE] -> [optional extra instruction]
    """
    guardrails = _load_guardrails()
    parts = [
        "=== GUARDRAILS (HIGHEST PRIORITY — NON-NEGOTIABLE) ===",
        guardrails,
        "=== END GUARDRAILS ===",
        "",
        "=== PERSONA ===",
        config.BOT_PERSONA,
        "=== END PERSONA ===",
        "",
        "=== KNOWLEDGE BASE ===",
        knowledge if knowledge.strip() else "(No knowledge base entries loaded yet.)",
        "=== END KNOWLEDGE BASE ===",
    ]
    if extra_instruction:
        parts += ["", extra_instruction]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def answer_question(question: str, user_name: str = "community member") -> str:
    """
    Answer a question using topic-relevant knowledge base entries as context.
    Classifies the question into 1-3 topics and loads only those files,
    keeping the context window focused and reducing token cost.
    Guardrails are injected as the highest-priority layer of the system prompt.
    Automatically selects standard or heavy model based on query complexity.
    """
    knowledge = knowledge_store.get_topic_knowledge_context(question)
    model = config.AI_MODEL_HEAVY if _is_complex_query(question) else config.AI_MODEL

    system_prompt = _build_system_prompt(
        knowledge=knowledge,
        extra_instruction=(
            "Use ONLY the knowledge base above to answer questions. "
            "If the answer is not in the knowledge base, use a cookie-themed deflection "
            "as described in the guardrails. Never speculate."
        ),
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{user_name} asks: {question}"},
            ],
            max_tokens=600,
            temperature=0.4,
        )
        answer = response.choices[0].message.content.strip()
        log.info("Answered question (model=%s, tokens=%s)", model, response.usage.total_tokens)
        return answer
    except Exception as exc:
        log.error("AI engine error: %s", exc)
        return (
            "Hmm, the cookie jar seems to be stuck right now. "
            "Please try again in a moment! \U0001f36a"
        )


def adjust_post(original_post: str, instruction: str, user_name: str = "admin") -> str:
    """
    Adjust or rewrite a post based on an instruction, using the knowledge base
    to ensure factual accuracy about CookieNet / $COOK.
    Guardrails are applied to keep the output on-brand and safe.
    """
    knowledge = knowledge_store.get_knowledge_context(max_chars=6000)
    model = config.AI_MODEL

    system_prompt = _build_system_prompt(
        knowledge=knowledge,
        extra_instruction=(
            "You are helping an admin adjust or improve a community post. "
            "Apply the requested changes while keeping the content accurate, "
            "on-brand (Cookie Boy / $COOK / CookieNet themed), and community-friendly. "
            "Return ONLY the revised post text, nothing else."
        ),
    )

    user_message = (
        f"Original post:\n{original_post}\n\n"
        f"Instruction from {user_name}: {instruction}"
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=800,
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        log.error("AI post adjustment error: %s", exc)
        return "Cookie jar error — could not adjust post. Please try again!"



def generate_updates(days: int = 14) -> str:
    """
    Scan knowledge base entries from the last `days` days, rank by importance,
    and return a formatted top-10 digest suitable for posting in Telegram.
    """
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    all_entries = knowledge_store.list_entries(status="active")
    recent = []
    for e in all_entries:
        try:
            ts = datetime.fromisoformat(e.get("ingested_at", "").replace("Z", "+00:00"))
            if ts >= cutoff:
                recent.append(e)
        except Exception:
            pass

    if not recent:
        return (
            f"🍪 No new knowledge entries in the last {days} days.\n"
            "The jar is still full — try `/ask` for anything specific!"
        )

    # Build a compact context block for the AI to rank
    context_lines = []
    for i, e in enumerate(recent, 1):
        title = e.get("title", "untitled")[:80]
        snippet = e.get("content", "")[:300].replace("\n", " ")
        added = e.get("ingested_at", "?")[:10]
        priority = e.get("priority", "normal")
        context_lines.append(f"{i}. [{added}] ({priority}) {title}\n   {snippet}")
    context_block = "\n\n".join(context_lines)

    system_prompt = _build_system_prompt(
        knowledge=context_block,
        extra_instruction=(
            "You are compiling a community update digest. "
            "From the entries above, select the TOP 10 most important, newsworthy, "
            "or status-relevant items. Rank them from most to least important. "
            "Format the output as a Telegram-ready message using this exact structure:\n"
            "🍪 *Cookie Chain — Latest Updates*\n"
            "_(past {days} days)_\n\n"
            "1. *[Short title]* — One sentence summary.\n"
            "2. *[Short title]* — One sentence summary.\n"
            "... (up to 10 items)\n\n"
            "_Ask me anything with /ask <question>_ 🍪\n\n"
            "Rules: Use ONLY the provided entries. Do NOT invent items. "
            "Keep each line to one sentence. No price talk or speculation."
        ).format(days=days),
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=config.AI_MODEL_HEAVY,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Generate a top-10 update digest from the last {days} days."},
            ],
            max_tokens=900,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        log.error("generate_updates error: %s", exc)
        return "🍪 Cookie jar error — could not generate updates. Try again in a moment!"

def generate_summary(content: str, max_sentences: int = 5) -> str:
    """
    Generate a short summary of ingested content for confirmation messages.
    Guardrails are NOT applied here — this is an internal admin-only utility.
    """
    model = config.AI_MODEL
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a concise summarizer. Summarize the provided content in "
                        f"{max_sentences} sentences or fewer. Focus on key facts."
                    ),
                },
                {"role": "user", "content": content[:3000]},
            ],
            max_tokens=200,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        log.error("Summary generation error: %s", exc)
        return "(Summary unavailable)"
