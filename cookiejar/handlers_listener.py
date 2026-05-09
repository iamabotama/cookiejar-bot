"""
CookieJar Bot — Listener Mode Handlers
A lightweight mode for admin/whale/private channels.
Admins reply to a message with /save or @BotName save to push it to the knowledge repo.
The bot does NOT answer questions in this mode.
"""

import logging
from pathlib import Path
from telegram import Update, Message
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from . import config, ingestion, github_sync

log = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_USER_IDS


# ---------------------------------------------------------------------------
# /start (listener mode)
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🍪 *CookieJar Listener* is active.\n\n"
        "Reply to any message with `/save` or `/save <label>` to push it to the knowledge base.\n"
        "Only admins can save messages.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------------------------
# /help (listener mode)
# ---------------------------------------------------------------------------
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🍪 *CookieJar Listener Commands*\n\n"
        "/save `[label]` — Reply to a message to save it to the knowledge base\n"
        "/saveingest `<url>` — Ingest a URL directly into the knowledge base\n"
        "/start — Show welcome message\n\n"
        "_This bot is in listener mode and does not answer questions._",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------------------------
# /save (admin — reply to a message)
# ---------------------------------------------------------------------------
async def cmd_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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

    content = replied.text or replied.caption or ""
    if not content:
        await message.reply_text("That message has no text content to save.")
        return

    # Optional label from command args
    label = " ".join(context.args) if context.args else ""
    user_name = update.effective_user.username or update.effective_user.first_name
    chat_title = update.effective_chat.title or "private"
    source_label = f"admin_push:{user_name}:{chat_title}"
    title = label or f"Admin capture from {chat_title}"

    result = ingestion.ingest_text(
        content=content,
        source_label=source_label,
        title=title,
        tags=["admin_push", "listener"],
    )

    if result["success"]:
        await message.reply_text(
            f"✅ Saved to the cookie jar!\nEntry ID: `{result['entry_id']}`",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await message.reply_text(f"❌ Save failed: {result['error']}")


# ---------------------------------------------------------------------------
# /saveingest (admin — ingest a URL)
# ---------------------------------------------------------------------------
async def cmd_saveingest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Only admins can ingest URLs.")
        return

    url = context.args[0] if context.args else ""
    if not url or not url.startswith("http"):
        await update.message.reply_text(
            "Usage: `/saveingest <url>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    msg = await update.message.reply_text(f"🍪 Ingesting `{url}` ...", parse_mode=ParseMode.MARKDOWN)
    from . import ingestion as ing
    result = ing.ingest_url(url, tags=["admin_push", "listener"])

    if result["success"]:
        await msg.edit_text(
            f"✅ Ingested!\nTitle: {result['title']}\nEntry ID: `{result['entry_id']}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        # Send the Cookie Monster nom-nom image
        nom_path = Path(__file__).resolve().parent.parent / "assets" / "nom_nom.png"
        if nom_path.exists():
            with nom_path.open("rb") as img:
                from telegram import InputFile
                await update.message.reply_photo(
                    photo=InputFile(img, filename="nom_nom.png"),
                    caption="NOM NOM NOM! 🍪 Data cookies ingested into the jar!",
                )
    else:
        await msg.edit_text(f"❌ Ingestion failed: {result['error']}")


# ---------------------------------------------------------------------------
# @mention handler in listener mode — silently ignore or acknowledge
# ---------------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message: Message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()
    bot_username = f"@{config.BOT_USERNAME}"

    # If someone @mentions the listener bot, gently redirect
    if bot_username.lower() in text.lower():
        await message.reply_text(
            "🍪 I'm in listener mode here — I don't answer questions in this channel. "
            "Head to the main community channel to ask CookieJar a question!"
        )
