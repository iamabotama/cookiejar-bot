"""
CookieJar Bot — AI Engine
Handles question answering and post adjustment using Grok (xAI) via OpenAI-compatible API.
"""

import logging
from typing import Optional

from openai import OpenAI

from . import config, knowledge_store

log = logging.getLogger(__name__)

# Lazy-init client
_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.AI_API_KEY,
            base_url=config.AI_BASE_URL,
        )
    return _client


def _is_complex_query(question: str) -> bool:
    """
    Heuristic: use the heavier model for longer or multi-part questions.
    """
    return len(question) > 300 or question.count("?") > 2


def answer_question(question: str, user_name: str = "community member") -> str:
    """
    Answer a question using the active knowledge base as context.
    Automatically selects standard or heavy model based on complexity.
    """
    knowledge = knowledge_store.get_knowledge_context()
    model = config.AI_MODEL_HEAVY if _is_complex_query(question) else config.AI_MODEL

    system_prompt = (
        f"{config.BOT_PERSONA}\n\n"
        "--- KNOWLEDGE BASE ---\n"
        f"{knowledge}\n"
        "--- END KNOWLEDGE BASE ---\n\n"
        "Use ONLY the knowledge above to answer questions. "
        "If the answer is not in the knowledge base, say: "
        "'I don't have specific information on that yet — please check official "
        "Cookie Boy community channels for the latest updates.' "
        "Never speculate on price, never discuss other coins or networks."
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
            "Please try again in a moment! 🍪"
        )


def adjust_post(original_post: str, instruction: str, user_name: str = "admin") -> str:
    """
    Adjust or rewrite a post based on an instruction, using the knowledge base
    to ensure factual accuracy about CookieNet / $COOK.
    """
    knowledge = knowledge_store.get_knowledge_context(max_chars=6000)
    model = config.AI_MODEL

    system_prompt = (
        f"{config.BOT_PERSONA}\n\n"
        "--- KNOWLEDGE BASE ---\n"
        f"{knowledge}\n"
        "--- END KNOWLEDGE BASE ---\n\n"
        "You are helping an admin adjust or improve a community post. "
        "Apply the requested changes while keeping the content accurate, "
        "on-brand (Cookie Boy / $COOK / CookieNet themed), and community-friendly. "
        "Return ONLY the revised post text, nothing else."
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


def generate_summary(content: str, max_sentences: int = 5) -> str:
    """
    Generate a short summary of ingested content for confirmation messages.
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
