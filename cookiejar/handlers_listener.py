"""
CookieJar Bot — Listener Mode Handlers
Handles commands for the silent admin/whale channel instances.
The listener bot stays quiet unless an admin uses /save, /cookiejar, or /setmode.
"""

import os
import logging
from pathlib import Path
from telegram import Update, Message, InputFile
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from . import ai_engine, config, knowledge_store, github_sync, ingestion, ingestion_crawler

log = logging.getLogger(__name__)

COOKIE_GIF: Path = Path(__file__).resolve().parent.parent / "assets" / "cookie_reaction.gif"


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_USER_IDS


async def _send_nom_nom(update: Update) -> None:
    """Send a cookie reaction GIF randomly 1-in-10 times, otherwise just text."""
    import random
    text = "Saved. 🍪"
    if random.randint(1, 10) == 1 and COOKIE_GIF.exists():
        with COOKIE_GIF.open("rb") as gif:
            await update.message.reply_animation(
                animation=InputFile(gif, filename="cookie_reaction.gif"),
                caption=text,
            )
    else:
        await update.message.reply_text(text)


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    await update.message.reply_text(
        "🔇 *CookieJar — Listener Mode*\n\n"
        "I'm in silent mode here. I won't answer questions in this channel.\n\n"
        "Use `/save` or `/cookiejar` (as a reply) to drop important messages into the knowledge jar.\n"
        "Use `/setmode answer` to switch me to Q&A mode.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# /updates (public) — recent knowledge digest
# ---------------------------------------------------------------------------
async def cmd_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    await update.message.reply_text("🍪 Checking the jar for recent updates...")
    digest = ai_engine.generate_updates(days=14)
    await update.message.reply_text(digest, parse_mode=ParseMode.MARKDOWN)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    is_admin = _is_admin(update.effective_user.id)
    mode = config.BOT_MODE
    if mode == "listener":
        public = (
            "🔇 *CookieJar — Listener Mode*\n"
            "_Silent mode. Collecting data, not answering questions._\n"
            "`/updates` — Latest updates from the last 2 weeks\n"
            "`/cj status` — Show mode and entry counts\n"
            "`/cj announce` — Post a public intro message\n"
            "`/help` — This message\n"
        )
        admin = (
            "\n\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
            "`/cj` _(reply)_ — Save to the knowledge jar 🍪\n"
            "`/cj ingest <text or url>` — Save text or scrape a URL\n"
            "`/cj crawl <url>` — Crawl entire site and ingest all pages\n"
            "`/cj note <text>` — Save an admin note\n"
            "`/cj pin <text or reply>` — Save as high-priority\n"
            "`/cj stale <id>` — Mark an entry as stale\n"
            "`/cj deletelast` — Delete the last entry (within 5 min)\n"
            "`/listentries` — List active knowledge entries\n"
            "`/liststale` — List stale entries\n"
            "`/syncnow` — Force GitHub sync\n"
            "`/chatid` — Get this channel\'s Telegram ID\n"
            "`/setmode answer` — Switch to answer mode\n"
        )
    else:
        public = (
            "🍪 *CookieJar — Answer Mode*\n"
            "`/ask <question>` — Ask me about $COOK or Cookie Chain\n"
            "`/stats` — See how many cookies are in the jar\n"
            "`/updates` — Latest updates from the last 2 weeks\n"
            "`/cj status` — Show mode and entry counts\n"
            "`/cj announce` — Post a public intro message\n"
            "`/start` — Welcome message\n"
            "`/help` — This message\n"
        )
        admin = (
            "\n\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\u2015\n"
            "`/cj` _(reply)_ — Save to the knowledge jar 🍪\n"
            "`/cj ingest <text or url>` — Save text or scrape a URL\n"
            "`/cj crawl <url>` — Crawl entire site and ingest all pages\n"
            "`/cj note <text>` — Save an admin note\n"
            "`/cj pin <text or reply>` — Save as high-priority\n"
            "`/cj stale <id>` — Mark an entry as stale\n"
            "`/cj deletelast` — Delete the last entry (within 5 min)\n"
            "`/listentries` — List active knowledge entries\n"
            "`/liststale` — List stale entries\n"
            "`/syncnow` — Force GitHub sync\n"
            "`/chatid` — Get this channel\'s Telegram ID\n"
            "`/setmode listen` — Switch to listener mode\n"
        )
    msg = public + (admin if is_admin else "")
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# /save (admin) — reply to a message to save it
# ---------------------------------------------------------------------------
async def cmd_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Only admins can save messages.")
        return

    message: Message = update.message
    replied = message.reply_to_message
    if not replied:
        await message.reply_text(
            "Please *reply to a message* with `/save` to save it.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    content = (replied.text or "").strip()
    if not content:
        await message.reply_text("That message has no text content to save.")
        return

    user_name = update.effective_user.first_name or "admin"
    result = knowledge_store.add_entry(
        content=content,
        source="telegram_listener_save",
        title=f"Saved by {user_name} via /save",
        tags=["listener", "admin", "saved"],
    )

    if result["success"]:
        await message.reply_text(
            f"🍪 *Saved to the cookie jar!*\nEntry ID: `{result['entry_id']}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _send_nom_nom(update)
        github_sync.sync_knowledge_to_github()
    else:
        await message.reply_text(f"❌ Failed to save: {result['error']}")


# ---------------------------------------------------------------------------
# /saveingest (admin) — silently ingest a URL
# ---------------------------------------------------------------------------
async def cmd_saveingest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Only admins can ingest URLs.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: `/saveingest <url>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    url = context.args[0].strip()
    await update.message.reply_text(f"🔄 Ingesting `{url}`...", parse_mode=ParseMode.MARKDOWN)

    result = ingestion.ingest_url(url)
    if result["success"]:
        await update.message.reply_text(
            f"🍪 *Ingested!*\n"
            f"Title: {result['title']}\n"
            f"Entry ID: `{result['entry_id']}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _send_nom_nom(update)
        github_sync.sync_knowledge_to_github()
    else:
        await update.message.reply_text(f"❌ Failed: {result['error']}")


# ---------------------------------------------------------------------------
# /cookiejar (admin) — reply to any message or provide inline text to save it
# ---------------------------------------------------------------------------
async def cmd_cookiejar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /cookiejar (/cj) in listener mode — Universal intake command.
    Sub-commands: ingest, note, pin, stale, deletelast, status, help
    No sub-command + reply: saves the replied-to message.
    """
    if not config.is_allowed_chat(update.effective_chat.id):
        return

    is_admin = _is_admin(update.effective_user.id)
    user = update.effective_user
    user_name = user.first_name or "admin"
    user_id = str(user.id)

    args = context.args or []
    sub = args[0].lower() if args else ""

    # ── /cj help ────────────────────────────────────────────────────────────
    if sub == "help":
        await update.message.reply_text(
            "🍪 *CookieJar (/cj) Commands*\n\n"
            "*Save content:*\n"
            "• `/cj` — Save the replied-to message\n"
            "• `/cj ingest <text>` — Save inline text\n"
            "• `/cj ingest <url>` — Scrape URL and save as knowledge entry\n"
            "• `/cj crawl <url>` — Crawl entire site and ingest all pages/sections\n"
            "• `/cj note <text>` — Save text tagged as an admin note\n"
            "• `/cj pin <text or reply>` — Save and mark as high-priority\n\n"
            "*Manage entries:*\n"
            "• `/cj stale <id>` — Mark an entry as stale\n"
            "• `/cj deletelast` — Delete the last entry (within 5 min)\n\n"
            "*Info:*\n"
            "• `/cj status` — Show mode, entry count, last sync\n"
            "• `/cj help` — This message\n",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── /cj status ──────────────────────────────────────────────────────────
    if sub == "status":
        counts = knowledge_store.entry_count()
        mode = config.BOT_MODE.upper()
        await update.message.reply_text(
            f"🍪 *CookieJar Status*\n"
            f"• Mode: `{mode}`\n"
            f"• Active entries: `{counts.get('active', 0)}`\n"
            f"• Stale entries: `{counts.get('stale', 0)}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # ── No sub-command + reply: save replied-to message (admin only) ─────────
    if not sub and update.message.reply_to_message:
        if not is_admin:
            await update.message.reply_text("🚫 Admin only command.")
            return
        replied_text = (update.message.reply_to_message.text or "").strip()
        if replied_text:
            entry = knowledge_store.add_entry(
                content=replied_text,
                source="telegram_cj_reply_listener",
                title=f"Saved by {user_name} via /cj (listener)",
                tags=["cookiejar", "admin", "reply", "listener"],
                added_by=user_id,
            )
            await update.message.reply_text(
                f"🍪 Saved. `{entry.get('id', '?')}`",
                parse_mode=ParseMode.MARKDOWN,
            )
            await _send_nom_nom(update)
            github_sync.sync_knowledge_to_github()
        else:
            await update.message.reply_text("⚠️ The replied-to message has no text content.")
        return

    # All commands below require admin
    if not is_admin:
        await update.message.reply_text("🚫 Admin only.")
        return

    # ── /cj deletelast ──────────────────────────────────────────────────────
    if sub == "announce":
        announce_msg = (
            "🍪 *Meet CookieJar — your Cookie Chain assistant!*\n\n"
            "I\'m here to answer questions about Cookie Chain, $COOK, the ecosystem, "
            "and anything in the knowledge base.\n\n"
            "*How to use me:*\n"
            "• Ask a question: `/ask What is Cookie Chain?`\n"
            "• Or just mention me: `@mewantcookiesbot <your question>`\n\n"
            "🗣️ *Got questions? Head over to the* *Ask the Cookie Jar* *channel — "
            "that\'s the right place to chat with me and keep things tidy here!*\n\n"
            "_I\'m powered by the official Cookie Chain knowledge base and get smarter "
            "as more content is added._ 🍪"
        )
        await update.message.reply_text(announce_msg, parse_mode=ParseMode.MARKDOWN)
        return

    if sub == "deletelast":
        result = knowledge_store.delete_last_entry(
            requesting_user_id=user_id,
            is_admin=is_admin,
            window_seconds=300,
        )
        if result["success"]:
            entry = result["entry"]
            await update.message.reply_text(
                f"🗑️ *Last entry deleted.*\n"
                f"ID: `{entry['id']}`\n"
                f"Title: {entry.get('title', '?')}",
                parse_mode=ParseMode.MARKDOWN,
            )
            github_sync.sync_knowledge_to_github()
        else:
            await update.message.reply_text(f"❌ {result['reason']}")
        return

    # ── /cj stale <id> ──────────────────────────────────────────────────────
    if sub == "stale":
        if len(args) < 2:
            await update.message.reply_text("Usage: `/cj stale <entry_id>`", parse_mode=ParseMode.MARKDOWN)
            return
        entry_id = args[1]
        if knowledge_store.mark_stale(entry_id):
            await update.message.reply_text(f"✅ Entry `{entry_id}` marked as stale.", parse_mode=ParseMode.MARKDOWN)
            github_sync.sync_knowledge_to_github()
        else:
            await update.message.reply_text(f"❌ Entry `{entry_id}` not found.", parse_mode=ParseMode.MARKDOWN)
        return

    # ── /cj note <text> ─────────────────────────────────────────────────────
    if sub == "note":
        note_text = " ".join(args[1:]).strip()
        if not note_text:
            await update.message.reply_text("Usage: `/cj note <your note text>`", parse_mode=ParseMode.MARKDOWN)
            return
        entry = knowledge_store.add_entry(
            content=note_text,
            source="admin_note_listener",
            title=f"Note by {user_name}",
            tags=["note", "admin", "listener"],
            added_by=user_id,
        )
        await update.message.reply_text(
            f"🍪 *Note saved!*\nEntry ID: `{entry.get('id', '?')}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _send_nom_nom(update)
        github_sync.sync_knowledge_to_github()
        return

    # ── /cj pin <text or reply> ─────────────────────────────────────────────
    if sub == "pin":
        pin_text = " ".join(args[1:]).strip()
        if not pin_text and update.message.reply_to_message:
            pin_text = (update.message.reply_to_message.text or "").strip()
        if not pin_text:
            await update.message.reply_text(
                "Usage: `/cj pin <text>` or reply to a message with `/cj pin`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        entry = knowledge_store.add_entry(
            content=pin_text,
            source="admin_pin_listener",
            title=f"Pinned by {user_name}",
            tags=["pinned", "admin", "listener"],
            priority="pinned",
            added_by=user_id,
        )
        await update.message.reply_text(
            f"🍪 *Pinned!* 📌\nEntry ID: `{entry.get('id', '?')}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _send_nom_nom(update)
        github_sync.sync_knowledge_to_github()
        return

    # ── /cj ingest <url or text> ────────────────────────────────────────────
    if sub == "ingest":
        ingest_arg = " ".join(args[1:]).strip()
        if not ingest_arg:
            await update.message.reply_text(
                "Usage:\n"
                "• `/cj ingest <url>` — scrape a website\n"
                "• `/cj ingest <text>` — save text directly",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        if ingest_arg.startswith("http://") or ingest_arg.startswith("https://"):
            await update.message.reply_text(f"🌐 Scraping `{ingest_arg}`...", parse_mode=ParseMode.MARKDOWN)
            result = ingestion.ingest_url(ingest_arg)
            if result["success"]:
                entry = knowledge_store.add_entry(
                    content=result["content"],
                    source=ingest_arg,
                    title=result.get("title", ingest_arg),
                    tags=["web", "ingested", "listener"],
                    added_by=user_id,
                )
                await update.message.reply_text(
                    f"🍪 *Ingested!*\nTitle: {result.get('title', ingest_arg)}\nEntry ID: `{entry.get('id', '?')}`",
                    parse_mode=ParseMode.MARKDOWN,
                )
                await _send_nom_nom(update)
                github_sync.sync_knowledge_to_github()
            else:
                await update.message.reply_text(f"❌ Failed to scrape: {result.get('error', 'unknown error')}")
        else:
            entry = knowledge_store.add_entry(
                content=ingest_arg,
                source="telegram_cj_ingest_listener",
                title=f"Saved by {user_name} via /cj",
                tags=["cookiejar", "admin", "manual", "listener"],
                added_by=user_id,
            )
            await update.message.reply_text(
                f"🍪 Saved. `{entry.get('id', '?')}`",
                parse_mode=ParseMode.MARKDOWN,
            )
            await _send_nom_nom(update)
            github_sync.sync_knowledge_to_github()
        return

    # ── /cj crawl <url> ────────────────────────────────────────────────────
    if sub == "crawl":
        crawl_url = " ".join(args[1:]).strip()
        if not crawl_url or not (crawl_url.startswith("http://") or crawl_url.startswith("https://")):
            await update.message.reply_text(
                "Usage: `/cj crawl <url>`\nExample: `/cj crawl https://cookiescan.io/docs`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        await update.message.reply_text(
            f"🕷️ Starting site crawl of `{crawl_url}`...\nThis may take a minute — I'll report back when done!",
            parse_mode=ParseMode.MARKDOWN,
        )
        result = ingestion_crawler.crawl_site(crawl_url, max_pages=30)
        if not result["success"]:
            await update.message.reply_text(f"❌ Crawl failed: {result.get('error', 'unknown error')}")
            return
        pages = result["pages"]
        saved = 0
        skipped = 0
        for pg in pages:
            pg_content = pg.get("content", "").strip()
            if len(pg_content) < 80:
                skipped += 1
                continue
            knowledge_store.add_entry(
                content=pg_content,
                source=pg.get("url", crawl_url),
                title=pg.get("title", pg.get("url", "Crawled page")),
                tags=["web", "crawled", "site-ingest", "listener"],
                added_by=user_id,
            )
            saved += 1
        github_sync.sync_knowledge_to_github()
        await update.message.reply_text(
            f"🍪 *Site crawl complete!*\n"
            f"URL: `{crawl_url}`\n"
            f"Pages saved: `{saved}`\n"
            f"Pages skipped (too short): `{skipped}`\n"
            f"Total discovered: `{result['count']}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return


# ---------------------------------------------------------------------------
# /setmode — switch between listen and answer modes at runtime (admin only)
# ---------------------------------------------------------------------------
async def cmd_setmode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /setmode listen  — stay in listener/silent mode
    /setmode answer  — switch to primary/answer mode
    /setmode status  — show the current mode
    """
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only.")
        return

    arg = (context.args[0].lower() if context.args else "status")

    if arg in ("listen", "listener"):
        config.BOT_MODE = "listener"
        await update.message.reply_text(
            "🔇 *Mode set to LISTENER.* Silent mode active.",
            parse_mode=ParseMode.MARKDOWN,
        )
    elif arg in ("answer", "primary"):
        config.BOT_MODE = "primary"
        await update.message.reply_text(
            "🍪 Answer mode active.",
            parse_mode=ParseMode.MARKDOWN,
        )
    elif arg == "status":
        mode = config.BOT_MODE
        emoji = "🔇" if mode == "listener" else "🍪"
        await update.message.reply_text(
            f"{emoji} *Current mode:* `{mode.upper()}`",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            "Usage: `/setmode answer` | `/setmode listen` | `/setmode status`",
            parse_mode=ParseMode.MARKDOWN,
        )


# ---------------------------------------------------------------------------
# Message handler — stays silent in listener mode, redirects @mentions
# ---------------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    message: Message = update.message
    if not message or not message.text:
        return
    text = message.text.strip()
    bot_username = f"@{config.BOT_USERNAME}"

    # If someone @mentions the listener bot, gently redirect them
    if bot_username.lower() in text.lower():
        await message.reply_text(
            "🍪 I'm in listener mode here — I don't answer questions in this channel. "
            "Head to the main community channel to ask CookieJar a question!"
        )
