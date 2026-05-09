"""
CookieJar Bot — Primary Mode Handlers
Handles all commands and messages for the public Q&A / community channel.
"""

import logging
from pathlib import Path
from telegram import Update, Message, InputFile
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from . import config, ingestion, knowledge_store, ai_engine, github_sync

# Path to the Cookie Boy nom-nom image bundled with the bot
NOM_NOM_IMAGE: Path = Path(__file__).resolve().parent.parent / "assets" / "nom_nom.png"

# Rotating captions shown with the nom-nom image on each ingestion
NOM_NOM_CAPTIONS = [
    "NOM NOM NOM! 🍪 Cookie Boy just ate that data right up!",
    "COOKIES! Cookie Boy is CHOMPING! 🍪 Data ingested into the jar!",
    "Cookie Boy LOVES data cookies! Chomp chomp chomp! 🍪",
    "Om nom nom... dis data SO GOOD! 🍪 Cookie Boy stored it in the jar!",
    "*Cookie Boy devours entire website* NOM NOM NOM! 🍪",
    "Cookie Boy can't stop! Data too delicious! NOM NOM! 🍪",
    "COOOOOKIES! 🍪 Cookie Boy goes nom nom nom nom nom!",
    "Cookie Boy ate the data. NOM NOM NOM! 🍪 Yum! $COOK!",
    "Dev is cooking AND Cookie Boy is eating! 🍪 Data stored!",
    "Accept all cookies? Cookie Boy already did. NOM! 🍪",
]

_nom_nom_counter = 0


def _nom_nom_caption() -> str:
    global _nom_nom_counter
    caption = NOM_NOM_CAPTIONS[_nom_nom_counter % len(NOM_NOM_CAPTIONS)]
    _nom_nom_counter += 1
    return caption


async def _send_nom_nom(update: Update, caption: str = "") -> None:
    """Send the Cookie Boy eating image with an optional caption."""
    if NOM_NOM_IMAGE.exists():
        with NOM_NOM_IMAGE.open("rb") as img:
            await update.message.reply_photo(
                photo=InputFile(img, filename="nom_nom.png"),
                caption=caption or _nom_nom_caption(),
            )
    else:
        # Fallback if image file is missing
        await update.message.reply_text(caption or _nom_nom_caption())

log = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_USER_IDS


def _fmt_entry_list(entries: list[dict], status: str = "active") -> str:
    if not entries:
        return f"No {status} entries found in the cookie jar."
    lines = [f"*{status.upper()} ENTRIES ({len(entries)})*\n"]
    for e in entries[:20]:  # cap display at 20
        lines.append(
            f"• `{e['id']}` — {e['title'][:50]}\n"
            f"  Source: {e['source'][:60]}\n"
            f"  Added: {e['ingested_at'][:10]}"
        )
    if len(entries) > 20:
        lines.append(f"\n_...and {len(entries) - 20} more._")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🍪 *Welcome to CookieJar!*\n\n"
        "I'm the official AI assistant for the *Cookie Boy* community on CookieNet.\n\n"
        "Ask me anything about *$COOK*, *CookieNet*, or the Cookie Boy community — "
        "just type your question or reply to any message with `@CookieJarBot`.\n\n"
        "Type /help to see all available commands.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    is_admin = _is_admin(update.effective_user.id)
    public_cmds = (
        "🍪 *CookieJar Commands*\n\n"
        "*Anyone can use:*\n"
        "/start — Welcome message\n"
        "/help — This help message\n"
        "/ask `<question>` — Ask CookieJar a question\n"
        "/stats — Show knowledge base stats\n\n"
        "You can also just ask a question directly, or reply to any message "
        "with `@CookieJarBot <instruction>` to adjust it."
    )
    admin_cmds = (
        "\n\n*Admin only:*\n"
        "/ingest `<url>` — Ingest a website into the knowledge base\n"
        "/addpost `<text>` — Add a manual post to the knowledge base\n"
        "/listentries — List active knowledge entries\n"
        "/liststale — List stale knowledge entries\n"
        "/stale `<id>` — Mark an entry as stale\n"
        "/archive `<id>` — Archive an entry\n"
        "/syncnow — Force sync knowledge base to/from GitHub\n"
        "/stalcheck — Run automatic stale check\n"
    )
    msg = public_cmds + (admin_cmds if is_admin else "")
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# /ask
# ---------------------------------------------------------------------------
async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(context.args) if context.args else ""
    if not question:
        await update.message.reply_text(
            "Please provide a question. Example:\n`/ask What is CookieNet?`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await update.message.reply_text("🍪 Reaching into the cookie jar...")
    user_name = update.effective_user.first_name or "community member"
    answer = ai_engine.answer_question(question, user_name=user_name)
    await update.message.reply_text(answer)


# ---------------------------------------------------------------------------
# /stats
# ---------------------------------------------------------------------------
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    counts = knowledge_store.entry_count()
    await update.message.reply_text(
        f"📊 *CookieJar Knowledge Stats*\n\n"
        f"Active entries: {counts.get('active', 0)}\n"
        f"Stale entries: {counts.get('stale', 0)}\n"
        f"Archived entries: {counts.get('archived', 0)}",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------------------------
# /ingest (admin)
# ---------------------------------------------------------------------------
async def cmd_ingest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only command.")
        return

    url = context.args[0] if context.args else ""
    if not url or not url.startswith("http"):
        await update.message.reply_text(
            "Usage: `/ingest <url>`\nExample: `/ingest https://cookienet.io/about`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    msg = await update.message.reply_text(f"🍪 Ingesting `{url}` ...", parse_mode=ParseMode.MARKDOWN)
    result = ingestion.ingest_url(url)

    if result["success"]:
        summary = ai_engine.generate_summary(
            knowledge_store.load_active()[-1]["content"] if knowledge_store.load_active() else ""
        )
        await msg.edit_text(
            f"✅ *Ingested successfully!*\n\n"
            f"Title: {result['title']}\n"
            f"Entry ID: `{result['entry_id']}`\n"
            f"Characters stored: {result['char_count']}\n\n"
            f"*Summary:* {summary}",
            parse_mode=ParseMode.MARKDOWN,
        )
        # Send the Cookie Boy nom-nom image as a fun confirmation
        await _send_nom_nom(update)
    else:
        await msg.edit_text(f"❌ Ingestion failed: {result['error']}")


# ---------------------------------------------------------------------------
# /addpost (admin)
# ---------------------------------------------------------------------------
async def cmd_addpost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only command.")
        return

    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text(
            "Usage: `/addpost <your text here>`\n"
            "Or reply to a message with `/addpost` to add that message's content.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    user_name = update.effective_user.username or update.effective_user.first_name
    result = ingestion.ingest_text(
        content=text,
        source_label=f"manual_post:{user_name}",
        title=f"Manual post by {user_name}",
        tags=["manual", "admin"],
    )

    if result["success"]:
        await update.message.reply_text(
            f"✅ Post added to the cookie jar!\nEntry ID: `{result['entry_id']}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        # Send the Cookie Boy nom-nom image as a fun confirmation
        await _send_nom_nom(update)
    else:
        await update.message.reply_text(f"❌ Failed to add post: {result['error']}")


# ---------------------------------------------------------------------------
# /listentries and /liststale (admin)
# ---------------------------------------------------------------------------
async def cmd_listentries(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only command.")
        return
    entries = knowledge_store.list_entries("active")
    await update.message.reply_text(
        _fmt_entry_list(entries, "active"), parse_mode=ParseMode.MARKDOWN
    )


async def cmd_liststale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only command.")
        return
    entries = knowledge_store.list_entries("stale")
    await update.message.reply_text(
        _fmt_entry_list(entries, "stale"), parse_mode=ParseMode.MARKDOWN
    )


# ---------------------------------------------------------------------------
# /stale (admin)
# ---------------------------------------------------------------------------
async def cmd_stale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only command.")
        return
    entry_id = context.args[0] if context.args else ""
    if not entry_id:
        await update.message.reply_text("Usage: `/stale <entry_id>`", parse_mode=ParseMode.MARKDOWN)
        return
    if knowledge_store.mark_stale(entry_id):
        await update.message.reply_text(f"✅ Entry `{entry_id}` marked as stale.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"❌ Entry `{entry_id}` not found.")


# ---------------------------------------------------------------------------
# /archive (admin)
# ---------------------------------------------------------------------------
async def cmd_archive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only command.")
        return
    entry_id = context.args[0] if context.args else ""
    if not entry_id:
        await update.message.reply_text("Usage: `/archive <entry_id>`", parse_mode=ParseMode.MARKDOWN)
        return
    if knowledge_store.archive_entry(entry_id):
        github_sync.sync_knowledge_to_github()
        await update.message.reply_text(f"✅ Entry `{entry_id}` archived.", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"❌ Entry `{entry_id}` not found.")


# ---------------------------------------------------------------------------
# /syncnow (admin)
# ---------------------------------------------------------------------------
async def cmd_syncnow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only command.")
        return
    msg = await update.message.reply_text("🔄 Syncing with GitHub...")
    ok = github_sync.sync_knowledge_to_github()
    github_sync.sync_knowledge_from_github()
    await msg.edit_text("✅ Sync complete!" if ok else "⚠️ Sync completed with some errors. Check logs.")


# ---------------------------------------------------------------------------
# /stalecheck (admin)
# ---------------------------------------------------------------------------
async def cmd_stalecheck(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only command.")
        return
    count = knowledge_store.auto_stale_check()
    await update.message.reply_text(
        f"✅ Stale check complete. {count} entr{'y' if count == 1 else 'ies'} marked as stale."
    )


# ---------------------------------------------------------------------------
# Message handler: @mention replies and plain questions
# ---------------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message: Message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()
    bot_username = f"@{config.BOT_USERNAME}"
    user_name = update.effective_user.first_name or "community member"

    # Case 1: @BotName reply — adjust the replied-to post
    if text.startswith(bot_username) and message.reply_to_message:
        instruction = text[len(bot_username):].strip()
        original = message.reply_to_message.text or ""
        if not original:
            await message.reply_text("I can only adjust text messages.")
            return
        if not instruction:
            instruction = "Improve this post for the Cookie Boy community."
        await message.reply_text("🍪 Adjusting that post...")
        adjusted = ai_engine.adjust_post(original, instruction, user_name=user_name)
        await message.reply_text(f"*Adjusted post:*\n\n{adjusted}", parse_mode=ParseMode.MARKDOWN)
        return

    # Case 2: @BotName question (no reply)
    if text.startswith(bot_username):
        question = text[len(bot_username):].strip()
        if not question:
            return
        await message.reply_text("🍪 Reaching into the cookie jar...")
        answer = ai_engine.answer_question(question, user_name=user_name)
        await message.reply_text(answer)
        return

    # Case 3: Direct message in a private chat — treat as question
    if update.effective_chat.type == "private":
        await message.reply_text("🍪 Reaching into the cookie jar...")
        answer = ai_engine.answer_question(text, user_name=user_name)
        await message.reply_text(answer)


# ---------------------------------------------------------------------------
# /cookiejar (admin) — reply to any message to save it into the knowledge base
# ---------------------------------------------------------------------------
async def cmd_cookiejar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /cookiejar — When used as a reply to a message, saves that message's text
    into the knowledge base. Works in both group channels and DMs.

    Usage:
      - Reply to any message with /cookiejar to save it.
      - /cookiejar <text> to save inline text directly (no reply needed).
    """
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only command.")
        return

    user_name = update.effective_user.first_name or "admin"

    # Priority 1: inline text after the command
    inline_text = " ".join(context.args).strip() if context.args else ""

    # Priority 2: replied-to message text
    replied_text = ""
    if update.message.reply_to_message:
        replied_text = (update.message.reply_to_message.text or "").strip()

    content = inline_text or replied_text

    if not content:
        await update.message.reply_text(
            "Usage:\n"
            "• Reply to any message with `/cookiejar` to drop it in the jar.\n"
            "• Or: `/cookiejar <text>` to save text directly.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    result = knowledge_store.add_entry(
        content=content,
        source="telegram_cookiejar_command",
        title=f"Saved by {user_name} via /cookiejar",
        tags=["cookiejar", "admin", "manual"],
    )

    if result["success"]:
        await update.message.reply_text(
            f"🍪 *Dropped in the cookie jar!*\nEntry ID: `{result['entry_id']}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _send_nom_nom(update)
        github_sync.sync_knowledge_to_github()
    else:
        await update.message.reply_text(f"❌ Failed to save: {result['error']}")


# ---------------------------------------------------------------------------
# /cookiejar (admin) — reply to any message to save it into the knowledge base
# ---------------------------------------------------------------------------
async def cmd_cookiejar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /cookiejar — When used as a reply to a message, saves that message's text
    into the knowledge base. Works in both group channels and DMs.

    Usage:
      - Reply to any message with /cookiejar to save it.
      - /cookiejar <text> to save inline text directly (no reply needed).
    """
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only command.")
        return

    user_name = update.effective_user.first_name or "admin"

    # Priority 1: inline text after the command
    inline_text = " ".join(context.args).strip() if context.args else ""

    # Priority 2: replied-to message text
    replied_text = ""
    if update.message.reply_to_message:
        replied_text = (update.message.reply_to_message.text or "").strip()

    content = inline_text or replied_text

    if not content:
        await update.message.reply_text(
            "Usage:\n"
            "• Reply to any message with `/cookiejar` to drop it in the jar.\n"
            "• Or: `/cookiejar <text>` to save text directly.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    result = knowledge_store.add_entry(
        content=content,
        source="telegram_cookiejar_command",
        title=f"Saved by {user_name} via /cookiejar",
        tags=["cookiejar", "admin", "manual"],
    )

    if result["success"]:
        await update.message.reply_text(
            f"🍪 *Dropped in the cookie jar!*\nEntry ID: `{result['entry_id']}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _send_nom_nom(update)
        github_sync.sync_knowledge_to_github()
    else:
        await update.message.reply_text(f"❌ Failed to save: {result['error']}")
