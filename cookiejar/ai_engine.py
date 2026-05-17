"""
CookieJar Bot — AI Engine  (v2 — multi-agent RAG pipeline)

answer_question() now runs a 3-stage pipeline:

  Stage 1 — CLASSIFIER AGENT
    An LLM call (fast model) reads the question and returns a JSON list of
    the 1-3 most relevant topic names.  Falls back to the rule-based
    keyword classifier in knowledge_store if the LLM call fails.

  Stage 2 — TOPIC AGENTS (parallel threads)
    One lightweight LLM call per matched topic.  Each agent receives only
    the entries for its topic and returns a short focused summary of what
    it found that is relevant to the question.  Topics with no relevant
    entries return None and are silently dropped.

  Stage 3 — ORCHESTRATOR AGENT
    Receives all topic summaries and synthesises them into a single,
    persona-compliant, guardrail-checked final answer.

All other public functions (adjust_post, generate_updates, generate_summary)
are unchanged.

System prompt layering (highest → lowest priority):
  1. GUARDRAILS  — non-negotiable rules loaded from guardrails_v1.md
  2. PERSONA     — Cookie Boy character voice from config.BOT_PERSONA
  3. KNOWLEDGE   — entries / summaries passed per stage
"""
import concurrent.futures
import json
import logging
from typing import Optional

from openai import OpenAI

from . import config, knowledge_store

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Guardrails loader
# ---------------------------------------------------------------------------

_GUARDRAILS_DIR   = config.COOKIEJAR_MODULE_DIR
_GUARDRAILS_CACHE: Optional[str] = None


def _load_guardrails() -> str:
    global _GUARDRAILS_CACHE
    if _GUARDRAILS_CACHE is not None:
        return _GUARDRAILS_CACHE

    candidates = sorted(
        _GUARDRAILS_DIR.glob("guardrails_v*.md"),
        key=lambda p: int(p.stem.split("_v")[-1]) if p.stem.split("_v")[-1].isdigit() else 0,
        reverse=True,
    )
    if candidates:
        try:
            _GUARDRAILS_CACHE = candidates[0].read_text(encoding="utf-8").strip()
            log.info("Loaded guardrails from %s", candidates[0].name)
            return _GUARDRAILS_CACHE
        except Exception as exc:
            log.error("Failed to read guardrails file: %s", exc)

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
        _client = OpenAI(api_key=config.AI_API_KEY, base_url=config.AI_BASE_URL)
    return _client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_complex_query(question: str) -> bool:
    return len(question) > 300 or question.count("?") > 2


def _build_system_prompt(knowledge: str, extra_instruction: str = "") -> str:
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
# All topic names (must match knowledge_store.TOPICS)
# ---------------------------------------------------------------------------

_ALL_TOPIC_NAMES = [t["name"] for t in knowledge_store.TOPICS]
_ALL_TOPIC_DESCRIPTIONS = {
    t["name"]: t["description"] for t in knowledge_store.TOPICS
}


# ===========================================================================
# STAGE 1 — CLASSIFIER AGENT
# ===========================================================================

def _classify_topics_llm(question: str) -> list[str]:
    """
    Ask the fast LLM to classify the question into 1-3 topic names.
    Returns a list of valid topic names.
    Falls back to the rule-based classifier on any error.
    """
    topic_list = "\n".join(
        f'  "{name}": {desc}'
        for name, desc in _ALL_TOPIC_DESCRIPTIONS.items()
        if name != "general"
    )
    system = (
        "You are a topic classifier for a Telegram community bot about Cookie Chain ($COOK), "
        "a Solana-fork blockchain.\n\n"
        "Available topics and what they cover:\n"
        f"{topic_list}\n\n"
        "Given a user question, return a JSON array of 1-3 topic names that are most likely "
        "to contain a relevant answer. Order them from most to least relevant.\n"
        "Return ONLY a valid JSON array of strings, e.g.: [\"faq\", \"chain\"]\n"
        "Do not include explanations or any other text."
    )
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=config.AI_MODEL,          # fast model for classification
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": question},
            ],
            max_tokens=60,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        topics = json.loads(raw)
        valid = [t for t in topics if t in _ALL_TOPIC_NAMES]
        if valid:
            log.info("[Classifier] LLM topics: %s", valid)
            # Always include general as a fallback bucket
            if "general" not in valid:
                valid.append("general")
            return valid[:3]
    except Exception as exc:
        log.warning("[Classifier] LLM classification failed (%s) — falling back to keywords", exc)

    # Rule-based fallback
    fallback = knowledge_store.classify_question_to_topics(question)
    log.info("[Classifier] Keyword fallback topics: %s", fallback)
    return fallback


# ===========================================================================
# STAGE 2 — TOPIC AGENTS
# ===========================================================================

def _topic_agent(question: str, topic_name: str) -> Optional[str]:
    """
    One topic agent: loads all entries for `topic_name`, asks the fast LLM
    to extract and summarise only the parts relevant to the question.
    Returns a concise summary string, or None if nothing relevant was found.
    """
    entries = knowledge_store.load_topic(topic_name)
    active  = [e for e in entries if e.get("status") == "active"]
    if not active:
        log.debug("[TopicAgent:%s] No active entries — skipping", topic_name)
        return None

    # --- Keyword pre-filter ---
    # Extract meaningful words from the question (3+ chars, ignore stop words)
    _STOP = {'the','and','for','are','was','you','can','tell','me','about','what',
             'how','why','when','where','who','is','it','in','of','to','a','an',
             'do','did','does','have','has','been','be','this','that','with','from'}
    q_words = {w.lower() for w in question.replace('?','').replace(',','').split()
               if len(w) >= 3 and w.lower() not in _STOP}

    def _entry_matches(e: dict) -> bool:
        """Return True if any question word appears in the entry's searchable fields."""
        haystack = ' '.join([
            e.get('title', ''),
            ' '.join(e.get('tags', [])),
            e.get('content', '')[:500],   # first 500 chars of content
        ]).lower()
        return any(w in haystack for w in q_words)

    matched = [e for e in active if _entry_matches(e)]
    # Fall back to all active entries if nothing matched (avoids silent empty results)
    if not matched:
        log.debug("[TopicAgent:%s] No keyword match — using all %d active entries", topic_name, len(active))
        matched = active
    else:
        log.info("[TopicAgent:%s] Keyword pre-filter: %d/%d entries matched", topic_name, len(matched), len(active))

    # Sort matched entries: lowest priority number first, then newest first
    matched.sort(key=lambda e: (e.get('priority', 5), '~' if not e.get('ingested_at') else e.get('ingested_at')), reverse=True)
    matched.sort(key=lambda e: e.get('priority', 5))

    # Build a compact context block for this topic
    context_parts = []
    total = 0
    for e in matched:
        block = (
            f"ENTRY: {e.get('title', '?')}\n"
            f"SOURCE: {e.get('source', '?')}\n"
            f"{e.get('content', '').strip()}\n"
        )
        if total + len(block) > 12000:   # generous limit — summaries are now compact
            break
        context_parts.append(block)
        total += len(block)

    if not context_parts:
        return None

    context = "\n---\n".join(context_parts)
    topic_desc = _ALL_TOPIC_DESCRIPTIONS.get(topic_name, topic_name)

    system = (
        f"You are a specialist research agent for the '{topic_name}' knowledge domain "
        f"({topic_desc}) of the Cookie Chain ($COOK) community bot.\n\n"
        "Your job:\n"
        "1. Read the knowledge entries below.\n"
        "2. Extract ONLY the facts that are directly relevant to the user's question.\n"
        "3. Return a concise, factual summary (2-5 sentences max) of what you found.\n"
        "4. If NOTHING in these entries is relevant to the question, reply with exactly: "
        "NO_RELEVANT_DATA\n\n"
        "Rules:\n"
        "- Do NOT answer the question directly — just summarise the relevant facts.\n"
        "- Do NOT add information not present in the entries.\n"
        "- Do NOT include greetings, preamble, or explanations.\n\n"
        f"=== {topic_name.upper()} KNOWLEDGE ENTRIES ===\n"
        f"{context}\n"
        f"=== END ENTRIES ==="
    )

    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=config.AI_MODEL,          # fast model per topic agent
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": f"Question: {question}"},
            ],
            max_tokens=300,
            temperature=0.1,
        )
        summary = resp.choices[0].message.content.strip()
        if summary == "NO_RELEVANT_DATA" or not summary:
            log.debug("[TopicAgent:%s] No relevant data found", topic_name)
            return None
        log.info("[TopicAgent:%s] Summary (%d chars)", topic_name, len(summary))
        return f"[{topic_name.upper()} FINDINGS]\n{summary}"
    except Exception as exc:
        log.error("[TopicAgent:%s] Error: %s", topic_name, exc)
        return None


def _run_topic_agents_parallel(question: str, topics: list[str]) -> list[str]:
    """
    Spin up one thread per topic, run all topic agents in parallel,
    collect and return non-None summaries.
    """
    summaries: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(topics)) as pool:
        future_map = {
            pool.submit(_topic_agent, question, topic): topic
            for topic in topics
        }
        for future in concurrent.futures.as_completed(future_map):
            topic = future_map[future]
            try:
                result = future.result(timeout=15)
                if result:
                    summaries.append(result)
            except Exception as exc:
                log.error("[TopicAgent:%s] Thread error: %s", topic, exc)
    return summaries


# ===========================================================================
# STAGE 3 — ORCHESTRATOR AGENT
# ===========================================================================

def _orchestrate(
    question: str,
    summaries: list[str],
    user_name: str,
    model: str,
) -> str:
    """
    Consolidate topic-agent summaries into a single final answer.
    Applies full guardrails + persona.
    """
    if summaries:
        combined = "\n\n".join(summaries)
    else:
        combined = "(No topic agents returned relevant data.)"

    system_prompt = _build_system_prompt(
        knowledge=combined,
        extra_instruction=(
            "You have received research summaries from specialist topic agents above. "
            "Synthesise them into a single, clear, helpful answer for the community member. "
            "Rules:\n"
            "- Use ONLY the facts provided in the topic agent summaries above.\n"
            "- If no summaries contain a relevant answer, use a friendly cookie-themed "
            "deflection as described in the guardrails.\n"
            "- Never speculate, never hallucinate, never add information not in the summaries.\n"
            "- Keep the answer concise and scannable (bullet points where helpful).\n"
            "- Respond in the Cookie Boy persona."
        ),
    )

    client = _get_client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": f"{user_name} asks: {question}"},
        ],
        max_tokens=600,
        temperature=0.4,
    )
    answer = resp.choices[0].message.content.strip()
    log.info(
        "[Orchestrator] Final answer (model=%s, tokens=%s)",
        model,
        resp.usage.total_tokens,
    )
    return answer


# ===========================================================================
# INGEST-TIME SUMMARIZATION
# ===========================================================================

# Pages shorter than this (chars) are stored as-is; longer ones get summarized
_SUMMARIZE_THRESHOLD = 1200


def summarize_for_storage(content: str, source_url: str, title: str) -> str:
    """
    Summarize raw page/document content into a compact, LLM-friendly entry.

    - Content under _SUMMARIZE_THRESHOLD chars is returned unchanged.
    - Longer content is summarized by the LLM to ~800 words, extracting:
        * What the document is about (1-2 sentences)
        * The 5-10 highest-value specific facts, figures, names, addresses
        * What questions this document can answer
    The source URL is appended so the bot can always point users back to it.
    """
    if len(content) <= _SUMMARIZE_THRESHOLD:
        # Short enough to store verbatim
        return content

    system = (
        "You are a knowledge extraction agent for a community bot. "
        "Your job is to read a document and extract the most valuable information "
        "in a compact, structured format that will help the bot answer questions later.\n\n"
        "Extract the following in order of priority:\n"
        "1. What this document is about (1-2 sentences)\n"
        "2. The 5-10 most important specific facts: numbers, dates, addresses, names, "
        "mechanisms, or unique claims\n"
        "3. What specific questions this document can answer\n"
        "4. Any official links, contract addresses, or resources mentioned\n\n"
        "Rules:\n"
        "- Be specific, not generic. Extract actual values, not descriptions of values.\n"
        "- Keep total output under 800 words.\n"
        "- Do NOT add information not present in the document.\n"
        "- Do NOT include greetings, preamble, or meta-commentary.\n"
        "- End with: Source: " + source_url
    )

    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=config.AI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": f"Document title: {title}\n\n{content[:12000]}"},
            ],
            max_tokens=1000,
            temperature=0.1,
        )
        summary = resp.choices[0].message.content.strip()
        log.info("[Summarizer] %s -> %d chars (was %d)", title[:50], len(summary), len(content))
        return summary
    except Exception as exc:
        log.error("[Summarizer] Failed for %s: %s", title[:50], exc)
        # Fall back to first 1200 chars if summarization fails
        return content[:1200] + f"\n\nSource: {source_url}"


# ===========================================================================
# PUBLIC API
# ===========================================================================

def answer_question(question: str, user_name: str = "community member") -> str:
    """
    Answer a question using the 3-stage multi-agent RAG pipeline:

      Stage 1 — Classifier agent  : LLM identifies 1-3 relevant topics
      Stage 2 — Topic agents      : one parallel LLM call per topic,
                                    each summarises its entries
      Stage 3 — Orchestrator      : consolidates summaries into final answer

    Guardrails and persona are enforced at the orchestration stage.
    """
    model = config.AI_MODEL_HEAVY if _is_complex_query(question) else config.AI_MODEL

    try:
        # ── Stage 1: Classify ──────────────────────────────────────────────
        topics = _classify_topics_llm(question)
        log.info("[Pipeline] Question=%r  Topics=%s", question[:80], topics)

        # ── Stage 2: Topic agents (parallel) ──────────────────────────────
        summaries = _run_topic_agents_parallel(question, topics)
        log.info("[Pipeline] %d/%d topic agents returned data", len(summaries), len(topics))

        # ── Stage 3: Orchestrate ───────────────────────────────────────────
        return _orchestrate(question, summaries, user_name, model)

    except Exception as exc:
        log.error("[Pipeline] Unhandled error: %s", exc)
        return (
            "Hmm, the cookie jar seems to be stuck right now. "
            "Please try again in a moment! \U0001f36a"
        )


def adjust_post(original_post: str, instruction: str, user_name: str = "admin") -> str:
    """
    Adjust or rewrite a post based on an instruction, using the full knowledge
    base to ensure factual accuracy about CookieNet / $COOK.
    Uses the combined text of the original post + instruction as the question
    to load only the relevant topic context (not the full KB).
    """
    combined_query = f"{original_post} {instruction}"
    knowledge = knowledge_store.get_topic_knowledge_context(combined_query, max_chars=6000)
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
        resp = client.chat.completions.create(
            model=config.AI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            max_tokens=800,
            temperature=0.5,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        log.error("AI post adjustment error: %s", exc)
        return "Cookie jar error — could not adjust post. Please try again!"


def generate_updates(days: int = 14) -> str:
    """
    Scan knowledge base entries from the last `days` days, rank by importance,
    and return a formatted top-10 digest suitable for posting in Telegram.
    """
    from datetime import datetime, timezone, timedelta  # noqa: PLC0415 — lazy import OK here
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

    context_lines = []
    for i, e in enumerate(recent, 1):
        title   = e.get("title", "untitled")[:80]
        snippet = e.get("content", "")[:300].replace("\n", " ")
        added   = e.get("ingested_at", "?")[:10]
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
        resp = client.chat.completions.create(
            model=config.AI_MODEL_HEAVY,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": f"Generate a top-10 update digest from the last {days} days."},
            ],
            max_tokens=900,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        log.error("generate_updates error: %s", exc)
        return "🍪 Cookie jar error — could not generate updates. Try again in a moment!"


def generate_summary(content: str, max_sentences: int = 5) -> str:
    """
    Generate a short summary of ingested content for confirmation messages.
    Guardrails are NOT applied here — internal admin-only utility.
    """
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=config.AI_MODEL,
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
        return resp.choices[0].message.content.strip()
    except Exception as exc:
        log.error("Summary generation error: %s", exc)
        return "(Summary unavailable)"
