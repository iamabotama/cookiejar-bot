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

from . import config, knowledge_store, github_sync

log = logging.getLogger(__name__)

NOM_NOM_IMAGE: Path = Path(__file__).resolve().parent.parent / "assets" / "nom_nom.png"


def _is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_USER_IDS


async def _send_nom_nom(update: Update) -> None:
    """Send the Cookie Boy eating image."""
    if NOM_NOM_IMAGE.exists():
        with NOM_NOM_IMAGE.open("rb") as img:
            await update.message.reply_photo(
                photo=InputFile(img, filename="nom_nom.png"),
                caption="NOM NOM NOM! 🍪 Cookie Boy ate that data! $COOK!",
            )
    else:
        await update.message.reply_text("NOM NOM NOM! 🍪 Dropped in the cookie jar!")


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
# /cookiejar (admin) — reply to any message or provide inline text to save it
# ---------------------------------------------------------------------------
async def cmd_cookiejar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Listener-mode /cookiejar: saves a replied-to message or inline text
    into the shared knowledge base so the primary bot can use it.

    Usage:
      - Reply to any message with /cookiejar to save it.
      - /cookiejar <text> to save inline text directly.
    """
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Admin only.")
        return

    user_name = update.effective_user.first_name or "admin"
    inline_text = " ".join(context.args).strip() if context.args else ""
    replied_text = ""
    if update.message.reply_to_message:
        replied_text = (update.message.reply_to_message.text or "").strip()

    content = inline_text or replied_text

    if not content:
        await update.message.reply_text(
            "Reply to a message with `/cookiejar` to drop it in the jar, "
            "or use `/cookiejar <text>` to save text directly.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    result = knowledge_store.add_entry(
        content=content,
        source="telegram_cookiejar_listener",
        title=f"Saved by {user_name} via /cookiejar (listener)",
        tags=["cookiejar", "admin", "listener"],
    )

    if result["success"]:
        await update.message.reply_text(
            f"🍪 *Dropped in the cookie jar!*\nEntry ID: `{result['entry_id']}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _send_nom_nom(update)
        github_sync.sync_knowledge_to_github()
    else:
        await update.message.reply_text(f"❌ Failed: {result['error']}")


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
            "🍪 *Mode set to ANSWER (primary).* NOM NOM NOM! Ready to answer questions!",
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
