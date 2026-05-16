"""
handlers.py — Single unified handler file for CookieJar bot.

All commands route through shared utilities:
  - _is_admin()         permission check
  - _nom_nom()          1-in-10 GIF response after ingestion
  - _intake()           all ingestion paths (reply, text, url)
  - _answer()           all AI answer paths (/ask, @mention, DM)
  - _load_chain_data()  reads cookiechain.json for /tg /x /ca /links

Mode (listener vs answer) controls what the bot responds to,
not which code path it takes.
"""

import asyncio
import json
import logging
import random
from pathlib import Path

from telegram import BotCommand, Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from . import ai_engine, config, github_sync, ingestion_crawler, knowledge_store

log = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).parent.parent / "assets"
GIF_PATH   = ASSETS_DIR / "cookie_reaction.gif"
CHAIN_JSON = Path(__file__).parent.parent / "cookiechain.json"

# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

async def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    True if the user is a Telegram group admin/owner in the current chat,
    OR is listed in the ADMIN_USER_IDS env var (for DM / private-chat use).
    """
    user = update.effective_user
    if not user:
        return False
    # Always allow env-var owners (works in DMs and groups)
    if user.id in config.ADMIN_USER_IDS:
        return True
    # In a group/supergroup, check Telegram's own admin list
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup"):
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            return member.status in ("administrator", "creator")
        except Exception:
            return False
    return False


_chain_cache: dict | None = None


def _load_chain_data(force_reload: bool = False) -> dict:
    """Load cookiechain.json once at startup and cache it in memory.
    Pass force_reload=True (e.g. from /syncnow) to refresh the cache.
    """
    global _chain_cache
    if _chain_cache is None or force_reload:
        try:
            _chain_cache = json.loads(CHAIN_JSON.read_text())
        except Exception:
            _chain_cache = {}
    return _chain_cache


async def _intake(
    update: Update,
    content: str,
    source: str,
    title: str,
    tags: list,
    priority: str = "normal",
) -> None:
    """
    Shared ingestion path. Saves content to KB, syncs to GitHub,
    then either sends the Cookie Monster GIF (1-in-10) or a plain
    text confirmation — never both.
    """
    user_id = update.effective_user.id if update.effective_user else 0
    entry = knowledge_store.add_entry(
        content=content,
        source=source,
        title=title,
        tags=tags,
        priority=priority,
        added_by=user_id,
    )
    entry_id = entry.get("id", "?")
    github_sync.sync_knowledge_to_github()
    captions = ["Nom nom. 🍪", "In the jar. 🍪", "Saved. 🍪", "Got it. 🍪", "Stored. 🍪"]
    caption = f"{random.choice(captions)} `{entry_id}`"
    if random.randint(1, 10) == 1 and GIF_PATH.exists():
        with open(GIF_PATH, "rb") as gif:
            await update.message.reply_animation(animation=gif, caption=caption, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(caption, parse_mode=ParseMode.MARKDOWN)


async def _answer(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str) -> None:
    """
    Shared answer path. Sends a placeholder, runs AI, edits in-place.
    Also detects update-intent questions and routes to the digest.
    """
    user_name = update.effective_user.first_name or "community member"
    UPDATE_TRIGGERS = {
        "what's new", "any updates", "latest updates", "news",
        "status update", "what happened", "anything new",
        "catch me up", "recent news", "new developments",
    }
    q_lower = question.lower()
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )
    placeholder = await update.message.reply_text("🍪 ...")
    if any(t in q_lower for t in UPDATE_TRIGGERS):
        result = await asyncio.to_thread(ai_engine.generate_updates)
    else:
        result = await asyncio.to_thread(ai_engine.answer_question, question, user_name)
    await placeholder.edit_text(result, parse_mode=ParseMode.MARKDOWN)


def _build_help(is_admin: bool) -> str:
    """Build the condensed help menu based on mode and admin status."""
    mode = config.BOT_MODE
    if mode == "listener":
        header = "🔇 *CookieJar — Listener Mode*\n"
        public = (
            "`/updates` — Latest updates\n"
            "`/tg` — Official Telegram\n"
            "`/x` — Official X account\n"
            "`/ca` — Contract address\n"
            "`/links` — Official links\n"
            "`/help` — This menu\n"
        )
    else:
        header = "🍪 *CookieJar — Answer Mode*\n"
        public = (
            "`/ask <question>` — Ask me anything\n"
            "`/updates` — Latest updates\n"
            "`/tg` — Official Telegram\n"
            "`/x` — Official X account\n"
            "`/ca` — Contract address\n"
            "`/links` — Official links\n"
            "`/stats` — Knowledge base stats\n"
            "`/help` — This menu\n"
        )
    admin = (
        "\n\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
        "`/save` — Reply to save a message\n"
        "`/save <text or url>` — Save inline\n"
        "`/crawl <url>` — Crawl entire site\n"
        "`/stale <id>` — Mark entry stale\n"
        "`/deletelast` — Undo last save\n"
        "`/announce` — Post intro message\n"
        "`/listentries` — List KB entries\n"
        "`/liststale` — List stale entries\n"
        "`/syncnow` — Force GitHub sync\n"
        "`/setmode answer|listen` — Switch mode\n"
        "`/chatid` — Get channel ID\n"
        "`/admin list` — List group admins\n"
    )
    return header + public + (admin if is_admin else "")


# ---------------------------------------------------------------------------
# Public commands
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    await update.message.reply_text(
        "🍪 *CookieJar*\nYour Cookie Chain knowledge assistant.\nType `/help` to see what I can do.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    is_admin = await _is_admin(update, context)
    await update.message.reply_text(_build_help(is_admin), parse_mode=ParseMode.MARKDOWN)


async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if config.BOT_MODE == "listener":
        return
    question = " ".join(context.args).strip() if context.args else ""
    if not question:
        await update.message.reply_text("Usage: `/ask <your question>`", parse_mode=ParseMode.MARKDOWN)
        return
    await _answer(update, context, question)


async def cmd_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    placeholder = await update.message.reply_text("🍪 ...")
    result = await asyncio.to_thread(ai_engine.generate_updates)
    await placeholder.edit_text(result, parse_mode=ParseMode.MARKDOWN)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    counts = knowledge_store.entry_count()
    active = counts.get("active", 0)
    stale  = counts.get("stale", 0)
    await update.message.reply_text(
        f"🍪 *Knowledge Jar*\nActive entries: `{active}`\nStale entries: `{stale}`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_tg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    data = _load_chain_data()
    url = data.get("telegram_url", "")
    if url:
        await update.message.reply_text(f"🍪 Official Telegram: {url}")
    else:
        await update.message.reply_text("🍪 Telegram link not set yet — check back soon!")


async def cmd_x(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    data = _load_chain_data()
    url = data.get("twitter_url", "")
    if url:
        await update.message.reply_text(f"🍪 Official X: {url}")
    else:
        await update.message.reply_text("🍪 X link not set yet — check back soon!")


async def cmd_ca(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    data = _load_chain_data()
    ca = data.get("ca", "")
    if ca and ca != "PASTE_CONTRACT_ADDRESS_HERE":
        await update.message.reply_text(
            f"🍪 *$COOK Contract Address*\n`{ca}`",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text("🍪 Contract address not set yet — check back soon!")


async def cmd_links(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    data = _load_chain_data()
    links = data.get("links", [])
    if not links:
        await update.message.reply_text("🍪 No official links set yet — check back soon!")
        return
    lines = ["🍪 *Official Links*"]
    for item in links:
        label = item.get("label", "Link")
        url   = item.get("url", "")
        if url:
            lines.append(f"• [{label}]({url})")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# Admin commands
# ---------------------------------------------------------------------------

async def cmd_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /save              — reply to a message to save it
    /save <text>       — save inline text
    /save <url>        — save URL as a metadata entry (no crawl)
    """
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_admin(update, context):
        await update.message.reply_text("🚫 Admin only.")
        return
    arg = " ".join(context.args).strip() if context.args else ""

    # Case 1: reply to a message
    if not arg and update.message.reply_to_message:
        replied = (update.message.reply_to_message.text or "").strip()
        if not replied:
            await update.message.reply_text("🍪 That message has no text to save.")
            return
        await _intake(
            update, content=replied,
            source="telegram_reply",
            title=f"Saved reply from {update.effective_user.first_name}",
            tags=["telegram", "reply"],
        )
        return

    # Case 2: URL (with optional description after it)
    # Formats: /save <url>  OR  /save <url> <description text>
    first_token = context.args[0] if context.args else ""
    if first_token and not first_token.startswith("http") and "." in first_token:
        first_token = "https://" + first_token
    if first_token.startswith("http://") or first_token.startswith("https://"):
        url = first_token
        # Everything after the URL is the description
        description = " ".join(context.args[1:]).strip() if context.args and len(context.args) > 1 else ""
        content = description if description else f"Official link: {url}"
        title = description[:80] if description else url
        await _intake(
            update, content=content,
            source=url,
            title=title,
            tags=["link", "url"],
        )
        return

    # Case 3: inline text
    if arg:
        await _intake(
            update, content=arg,
            source="telegram_inline",
            title=f"Saved by {update.effective_user.first_name}",
            tags=["telegram", "manual"],
        )
        return

    await update.message.reply_text(
        "Usage:\n"
        "• Reply to a message + `/save`\n"
        "• `/save <text>`\n"
        "• `/save <url>` — saves URL as a link entry (use `/crawl` to ingest full site)",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_crawl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /crawl <url> — crawl entire site and ingest all pages into KB.
    Uses Playwright for SPAs, falls back to static scraping.
    """
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_admin(update, context):
        await update.message.reply_text("🚫 Admin only.")
        return
    crawl_url = " ".join(context.args).strip() if context.args else ""
    # Be forgiving: strip whitespace, auto-prepend https:// if missing
    crawl_url = crawl_url.strip().rstrip("/")
    if crawl_url and not crawl_url.startswith("http://") and not crawl_url.startswith("https://"):
        crawl_url = "https://" + crawl_url
    if not crawl_url or "." not in crawl_url:
        await update.message.reply_text(
            "Usage: `/crawl <url>`\nExample: `/crawl https://cookiescan.io/docs`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await update.message.reply_text(f"🕷️ Crawling `{crawl_url}`...", parse_mode=ParseMode.MARKDOWN)

    # Run the blocking Playwright crawl in a thread so the event loop stays free
    result = await asyncio.to_thread(ingestion_crawler.crawl_site, crawl_url, 30)
    if not result["success"]:
        await update.message.reply_text(f"❌ Crawl failed: {result.get('error', 'unknown')}")
        return

    user_id = update.effective_user.id
    saved, skipped = 0, 0
    for pg in result["pages"]:
        pg_content = pg.get("content", "").strip()
        if len(pg_content) < 50:
            skipped += 1
            continue
        knowledge_store.add_entry(
            content=pg_content,
            source=pg.get("url", crawl_url),
            title=pg.get("title", pg.get("url", "Crawled page")),
            tags=["web", "crawled"],
            added_by=user_id,
        )
        saved += 1

    github_sync.sync_knowledge_to_github()
    await update.message.reply_text(
        f"🍪 Crawl done. Saved: `{saved}` — Skipped: `{skipped}` — Total: `{result['count']}`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_stale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_admin(update, context):
        await update.message.reply_text("🚫 Admin only.")
        return
    entry_id = context.args[0] if context.args else ""
    if not entry_id:
        await update.message.reply_text("Usage: `/stale <entry_id>`", parse_mode=ParseMode.MARKDOWN)
        return
    ok = knowledge_store.mark_stale(entry_id)
    if ok:
        await update.message.reply_text(f"🍪 Entry `{entry_id}` marked stale.", parse_mode=ParseMode.MARKDOWN)
        github_sync.sync_knowledge_to_github()
    else:
        await update.message.reply_text(f"❌ Entry `{entry_id}` not found.", parse_mode=ParseMode.MARKDOWN)


async def cmd_deletelast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_admin(update, context):
        await update.message.reply_text("🚫 Admin only.")
        return
    user_id = update.effective_user.id
    result = knowledge_store.delete_last_entry(
        requesting_user_id=str(user_id),
        is_admin=True,
        window_seconds=300,
    )
    if result["success"]:
        entry_id = result["entry"]["id"]
        await update.message.reply_text(f"🍪 Deleted entry `{entry_id}`.", parse_mode=ParseMode.MARKDOWN)
        github_sync.sync_knowledge_to_github()
    else:
        await update.message.reply_text(f"🍪 {result['reason']}")


async def cmd_announce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_admin(update, context):
        await update.message.reply_text("🚫 Admin only.")
        return
    data = _load_chain_data()
    ask_channel = data.get("ask_channel", "the Ask the Cookie Jar channel")
    msg = (
        "🍪 *Meet CookieJar — your Cookie Chain assistant!*\n\n"
        "I'm here to answer questions about Cookie Chain, $COOK, and the ecosystem.\n\n"
        "*How to use me:*\n"
        "• `/ask What is Cookie Chain?`\n"
        f"• Or mention me directly: `@{config.BOT_USERNAME} <question>`\n\n"
        f"🗣️ *Got questions? Head to {ask_channel} — that's the right place to chat with me!*\n\n"
        "_Powered by the official Cookie Chain knowledge base._ 🍪"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_listentries(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_admin(update, context):
        await update.message.reply_text("🚫 Admin only.")
        return
    entries = knowledge_store.list_entries(status="active")
    if not entries:
        await update.message.reply_text("🍪 No active entries.")
        return
    lines = ["🍪 *Active KB Entries*"]
    for e in entries[:20]:
        lines.append(f"• `{e['id'][:8]}` — {e.get('title', 'Untitled')[:60]}")
    if len(entries) > 20:
        lines.append(f"_...and {len(entries) - 20} more_")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_liststale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_admin(update, context):
        await update.message.reply_text("🚫 Admin only.")
        return
    entries = knowledge_store.list_entries(status="stale")
    if not entries:
        await update.message.reply_text("🍪 No stale entries.")
        return
    lines = ["🍪 *Stale KB Entries*"]
    for e in entries[:20]:
        lines.append(f"• `{e['id'][:8]}` — {e.get('title', 'Untitled')[:60]}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_syncnow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_admin(update, context):
        await update.message.reply_text("🚫 Admin only.")
        return
    github_sync.sync_knowledge_to_github()
    _load_chain_data(force_reload=True)
    await update.message.reply_text("🍪 Synced to GitHub.")


async def cmd_setmode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_admin(update, context):
        await update.message.reply_text("🚫 Admin only.")
        return
    arg = (context.args[0].lower() if context.args else "status")
    if arg in ("listen", "listener"):
        config.BOT_MODE = "listener"
        await update.message.reply_text("🔇 Listener mode active.")
    elif arg in ("answer", "primary"):
        config.BOT_MODE = "answer"
        await update.message.reply_text("🍪 Answer mode active.")
    elif arg == "status":
        emoji = "🔇" if config.BOT_MODE == "listener" else "🍪"
        await update.message.reply_text(f"{emoji} Mode: `{config.BOT_MODE.upper()}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("Usage: `/setmode answer|listen|status`", parse_mode=ParseMode.MARKDOWN)


async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_admin(update, context):
        await update.message.reply_text("🚫 Admin only.")
        return
    await update.message.reply_text(
        f"🍪 Chat ID: `{update.effective_chat.id}`", parse_mode=ParseMode.MARKDOWN
    )


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    user = update.effective_user
    if not user:
        return
    is_adm = await _is_admin(update, context)
    tier = "admin" if is_adm else "member"
    uname_line = f"@{user.username} · " if user.username else ""
    await update.message.reply_text(
        f"🍪 *Your info*\n"
        f"ID: `{uname_line}{user.id}`\n"
        f"Role: `{tier}`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /admin list  - list all Telegram group admins (any admin)
    Admins are managed directly in Telegram group settings.
    Promote/demote in the group - the bot picks it up automatically.
    """
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_admin(update, context):
        await update.message.reply_text("🚫 Admin only.")
        return
    chat = update.effective_chat
    # If called from a DM, use the first configured group chat
    target_chat_id = chat.id
    if chat.type == "private":
        if config.ALLOWED_CHAT_IDS:
            target_chat_id = next(iter(config.ALLOWED_CHAT_IDS))
        else:
            await update.message.reply_text(
                "ℹ️ Run `/admin` inside the group to see the admin list.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
    try:
        admins = await context.bot.get_chat_administrators(target_chat_id)
    except Exception as e:
        await update.message.reply_text(f"❌ Could not fetch admin list: {e}")
        return
    lines = ["🍪 *Group Admins*"]
    for member in admins:
        u = member.user
        uname = f"@{u.username}" if u.username else u.full_name or str(u.id)
        tier = "👑" if member.status == "creator" else "🔑"
        lines.append(f"{tier} {uname} (`{u.id}`)")  
    lines.append("\n_To grant bot admin rights, promote the user in Telegram group settings._")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# Message handler — @mention and DM questions
# ---------------------------------------------------------------------------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    message: Message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()
    bot_username = f"@{config.BOT_USERNAME}"

    # In listener mode: redirect @mentions, ignore everything else
    if config.BOT_MODE == "listener":
        if bot_username.lower() in text.lower():
            await message.reply_text(
                "🍪 I'm in listener mode here — head to the main channel to ask me questions!"
            )
        return

    # Answer mode: handle @mention reply (post adjustment)
    if text.startswith(bot_username) and message.reply_to_message:
        instruction = text[len(bot_username):].strip()
        original = message.reply_to_message.text or ""
        if not original:
            await message.reply_text("I can only adjust text messages.")
            return
        if not instruction:
            instruction = "Improve this post for the Cookie Chain community."
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        placeholder = await message.reply_text("🍪 ...")
        user_name = update.effective_user.first_name or "community member"
        adjusted = await asyncio.to_thread(ai_engine.adjust_post, original, instruction, user_name)
        await placeholder.edit_text(f"*Adjusted post:*\n\n{adjusted}", parse_mode=ParseMode.MARKDOWN)
        return

    # Answer mode: handle @mention question
    if text.startswith(bot_username):
        question = text[len(bot_username):].strip()
        if question:
            await _answer(update, context, question)
        return

    # Answer mode: DM — treat as question
    if update.effective_chat.type == "private":
        await _answer(update, context, text)


# ---------------------------------------------------------------------------
# Bot command list (for Telegram's command menu)
# ---------------------------------------------------------------------------

def get_bot_commands(is_admin_context: bool = False) -> list:
    """Return the BotCommand list for set_my_commands."""
    public = [
        BotCommand("ask",     "Ask me about $COOK or Cookie Chain"),
        BotCommand("updates", "Latest updates from the last 2 weeks"),
        BotCommand("tg",      "Official Telegram"),
        BotCommand("x",       "Official X account"),
        BotCommand("ca",      "Contract address"),
        BotCommand("links",   "All official links"),
        BotCommand("stats",   "Knowledge base stats"),
        BotCommand("help",    "Show commands"),
    ]
    admin_extra = [
        BotCommand("save",        "[Admin] Save a message or text"),
        BotCommand("crawl",       "[Admin] Crawl entire site"),
        BotCommand("stale",       "[Admin] Mark entry stale"),
        BotCommand("deletelast",  "[Admin] Undo last save"),
        BotCommand("announce",    "[Admin] Post intro message"),
        BotCommand("listentries", "[Admin] List KB entries"),
        BotCommand("liststale",   "[Admin] List stale entries"),
        BotCommand("syncnow",     "[Admin] Force GitHub sync"),
        BotCommand("setmode",     "[Admin] Switch answer/listen mode"),
        BotCommand("chatid",      "[Admin] Get channel ID"),
        BotCommand("admin",  "[Admin] List group admins"),
        BotCommand("whoami", "Show your user ID and role"),
    ]
    return public + admin_extra
