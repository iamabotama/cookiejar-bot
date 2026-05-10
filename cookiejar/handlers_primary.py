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
        await update.message.reply_text(caption or _nom_nom_caption())

log = logging.getLogger(__name__)


# Telegram's anonymous admin ID - only group admins can post with this ID
ANONYMOUS_ADMIN_ID = 1087968824


def _is_admin(user_id: int) -> bool:
    """Check if user ID is in the ADMIN_USER_IDS env list."""
    return user_id in config.ADMIN_USER_IDS


async def _is_chat_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Check if the sender is an admin of the current chat.
    This handles anonymous admin posting (where Telegram uses @GroupAnonymousBot).
    Returns True if:
      - User ID is in ADMIN_USER_IDS, OR
      - User ID is the anonymous admin ID (only admins can post anonymously), OR
      - User is a Telegram admin/owner of the current group/channel
    """
    user = update.effective_user
    chat = update.effective_chat

    # First check env list
    if user.id in config.ADMIN_USER_IDS:
        return True

    # Check for anonymous admin posting - if someone posts with this ID,
    # they MUST be an admin (only admins can post anonymously in Telegram)
    if user.id == ANONYMOUS_ADMIN_ID:
        log.info(f"User authorized as anonymous admin in chat {chat.id}")
        return True

    # For private chats, only env list matters
    if chat.type == "private":
        return False

    # For groups/channels, check if user is a Telegram admin
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status in ("administrator", "creator"):
            log.info(f"User {user.id} authorized as Telegram chat admin in {chat.id}")
            return True
    except Exception as e:
        log.warning(f"Could not check chat admin status: {e}")

    return False


def _fmt_entry_list(entries: list, status: str) -> str:
    if not entries:
        return f"No {status} entries found."
    lines = [f"*{status.upper()} entries ({len(entries)}):*"]
    for e in entries[:20]:
        ts = e.get("ingested_at", "?")[:10]
        title = e.get("title", "untitled")[:50]
        eid = e.get("id", "?")[:8]
        lines.append(f"• `{eid}` [{ts}] {title}")
    if len(entries) > 20:
        lines.append(f"_...and {len(entries) - 20} more_")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    await update.message.reply_text(
        "🍪 *NOM NOM NOM! Me CookieJar!*\n\n"
        "Me the official Cookie Boy ($COOK) community assistant!\n"
        "Me know everything about CookieNet and $COOK.\n\n"
        "Ask me anything with `/ask <your question>` or just `@mewantcookiesbot <question>`!\n\n"
        "Type `/help` to see all commands.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    is_admin = _is_admin(update.effective_user.id)
    mode = config.BOT_MODE

    if mode == "listener":
        # In listener mode, only show listener-relevant commands
        public_listener = (
            "🔇 *CookieJar — Listener Mode*\n"
            "_I am currently in silent mode. I collect cookies but don't answer questions._\n\n"
            "• `/cookiejar` — Reply to any message to save it to the jar\n"
            "• `/help` — This message\n"
        )
        admin_listener = (
            "\n*Admin only:*\n"
            "• `/cookiejar` — Reply to any message to save it to the jar\n"
            "• `/addpost <text>` — Add manual text to the knowledge base\n"
            "• `/ingest <url>` — Scrape a website into the knowledge base\n"
            "• `/listentries` — List active knowledge entries\n"
            "• `/liststale` — List stale entries\n"
            "• `/stale <id>` — Mark an entry as stale\n"
            "• `/archive <id>` — Archive an entry\n"
            "• `/syncnow` — Force GitHub sync\n"
            "• `/chatid` — Get this channel's Telegram ID\n"
            "• `/setmode answer` — Switch to answer mode\n"
            "• `/setmode status` — Check current mode\n"
        )
        msg = public_listener + (admin_listener if is_admin else "")
    else:
        # In answer/primary mode, show full Q&A commands
        public = (
            "🍪 *CookieJar Commands*\n\n"
            "*Public:*\n"
            "• `/ask <question>` — Ask me about $COOK or CookieNet\n"
            "• `/stats` — See how many cookies are in the jar\n"
            "• `/start` — Welcome message\n"
            "• `/help` — This message\n"
        )
        admin = (
            "\n*Admin only:*\n"
            "• `/ingest <url>` — Scrape a website into the knowledge base\n"
            "• `/addpost <text>` — Add manual text to the knowledge base\n"
            "• `/cookiejar` — Reply to any message to save it to the jar\n"
            "• `/listentries` — List active knowledge entries\n"
            "• `/liststale` — List stale entries\n"
            "• `/stale <id>` — Mark an entry as stale\n"
            "• `/archive <id>` — Archive an entry\n"
            "• `/syncnow` — Force GitHub sync\n"
            "• `/stalecheck` — Run auto stale check\n"
            "• `/chatid` — Get this channel's Telegram ID\n"
            "• `/setmode listen|status` — Switch bot mode\n"
        )
        msg = public + (admin if is_admin else "")

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# /ask
# ---------------------------------------------------------------------------
async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
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
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    stats = knowledge_store.get_stats()
    await update.message.reply_text(
        f"🍪 *Cookie Jar Stats*\n\n"
        f"Active entries: `{stats.get('active', 0)}`\n"
        f"Stale entries: `{stats.get('stale', 0)}`\n"
        f"Archived entries: `{stats.get('archived', 0)}`\n"
        f"Total sources ingested: `{stats.get('sources', 0)}`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------------------------
# /ingest (admin)
# ---------------------------------------------------------------------------
async def cmd_ingest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_chat_admin(update, context):
        await update.message.reply_text("🚫 Admin only command.")
        return
    url = context.args[0] if context.args else ""
    if not url:
        await update.message.reply_text(
            "Usage: `/ingest <url>`\nExample: `/ingest https://cookienet.io/about`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    msg = await update.message.reply_text(f"🍪 Ingesting `{url}`...", parse_mode=ParseMode.MARKDOWN)
    result = ingestion.ingest_url(url)
    if result["success"]:
        await msg.edit_text(
            f"✅ Ingested!\nEntry ID: `{result['entry_id']}`\n"
            f"Characters: `{result.get('char_count', '?')}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _send_nom_nom(update)
        github_sync.sync_knowledge_to_github()
    else:
        await msg.edit_text(f"❌ Ingestion failed: {result['error']}")


# ---------------------------------------------------------------------------
# /addpost (admin)
# ---------------------------------------------------------------------------
async def cmd_addpost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_chat_admin(update, context):
        await update.message.reply_text("🚫 Admin only command.")
        return
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text(
            "Usage: `/addpost <text>`\nExample: `/addpost CookieNet launches mainnet on June 1st`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    user_name = update.effective_user.first_name or "admin"
    result = knowledge_store.add_entry(
        content=text,
        source=f"telegram_admin_post",
        title=f"Admin post by {user_name}",
        tags=["manual", "admin"],
    )
    if result["success"]:
        await update.message.reply_text(
            f"✅ Post added to the cookie jar!\nEntry ID: `{result['entry_id']}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _send_nom_nom(update)
    else:
        await update.message.reply_text(f"❌ Failed to add post: {result['error']}")


# ---------------------------------------------------------------------------
# /listentries and /liststale (admin)
# ---------------------------------------------------------------------------
async def cmd_listentries(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_chat_admin(update, context):
        await update.message.reply_text("🚫 Admin only command.")
        return
    entries = knowledge_store.list_entries("active")
    await update.message.reply_text(
        _fmt_entry_list(entries, "active"), parse_mode=ParseMode.MARKDOWN
    )


async def cmd_liststale(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_chat_admin(update, context):
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
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_chat_admin(update, context):
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
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_chat_admin(update, context):
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
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_chat_admin(update, context):
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
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_chat_admin(update, context):
        await update.message.reply_text("🚫 Admin only command.")
        return
    count = knowledge_store.auto_stale_check()
    await update.message.reply_text(
        f"✅ Stale check complete. {count} entr{'y' if count == 1 else 'ies'} marked as stale."
    )


# ---------------------------------------------------------------------------
# /cookiejar (/cj) — universal intake command router
# ---------------------------------------------------------------------------

CJ_HELP = (
    "🍪 *CookieJar (/cj) Commands*\n\n"
    "*Save content:*\n"
    "• `/cj` — Save the replied-to message\n"
    "• `/cj ingest <text>` — Save inline text\n"
    "• `/cj ingest <url>` — Scrape URL and save as knowledge entry\n"
    "• `/cj note <text>` — Save text tagged as an admin note\n"
    "• `/cj pin <text or reply>` — Save and mark as high-priority\n\n"
    "*Manage entries:*\n"
    "• `/cj stale <id>` — Mark an entry as stale\n"
    "• `/cj deletelast` — Delete the last entry (within 5 min)\n\n"
    "*Info:*\n"
    "• `/cj status` — Show mode, entry count, last sync\n"
    "• `/cj help` — This message\n"
)


async def _cj_save(
    update,
    context,
    content: str,
    source: str,
    tags: list,
    priority: str = "normal",
    user_name: str = "admin",
    user_id: str = "",
) -> None:
    """Shared save logic for all /cj intake sub-commands."""
    entry = knowledge_store.add_entry(
        content=content,
        source=source,
        title=f"Saved by {user_name} via /cj",
        tags=tags,
        priority=priority,
        added_by=user_id,
    )
    entry_id = entry.get("id", "?")
    pin_label = " 📌 *PINNED*" if priority == "pinned" else ""
    await update.message.reply_text(
        f"🍪 *Dropped in the cookie jar!*{pin_label}\nEntry ID: `{entry_id}`",
        parse_mode=ParseMode.MARKDOWN,
    )
    await _send_nom_nom(update)
    github_sync.sync_knowledge_to_github()


async def cmd_cookiejar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /cookiejar (/cj) — Universal intake command.
    Sub-commands: ingest, note, pin, stale, deletelast, status, help
    No sub-command + reply: saves the replied-to message.
    """
    if not config.is_allowed_chat(update.effective_chat.id):
        return

    is_admin = await _is_chat_admin(update, context)
    user = update.effective_user
    user_name = user.first_name or "admin"
    user_id = str(user.id)

    args = context.args or []
    sub = args[0].lower() if args else ""

    # ── /cj help ────────────────────────────────────────────────────────────
    if sub == "help":
        await update.message.reply_text(CJ_HELP, parse_mode=ParseMode.MARKDOWN)
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

    # All commands below require admin
    if not is_admin:
        await update.message.reply_text("🚫 Admin only command.")
        return

    # ── /cj deletelast ──────────────────────────────────────────────────────
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
        await _cj_save(update, context, note_text,
                       source="admin_note",
                       tags=["note", "admin"],
                       user_name=user_name, user_id=user_id)
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
        await _cj_save(update, context, pin_text,
                       source="admin_pin",
                       tags=["pinned", "admin"],
                       priority="pinned",
                       user_name=user_name, user_id=user_id)
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
                    tags=["web", "ingested"],
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
            await _cj_save(update, context, ingest_arg,
                           source="telegram_cj_ingest",
                           tags=["cookiejar", "admin", "manual"],
                           user_name=user_name, user_id=user_id)
        return

    # ── No sub-command: save replied-to message ─────────────────────────────
    replied_text = ""
    if update.message.reply_to_message:
        replied_text = (update.message.reply_to_message.text or "").strip()

    if not replied_text:
        await update.message.reply_text(CJ_HELP, parse_mode=ParseMode.MARKDOWN)
        return

    await _cj_save(update, context, replied_text,
                   source="telegram_cj_reply",
                   tags=["cookiejar", "admin", "reply"],
                   user_name=user_name, user_id=user_id)


# ---------------------------------------------------------------------------
# /whoami — debug command to show the calling user's Telegram ID
# ---------------------------------------------------------------------------
async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Returns the calling user's Telegram ID. Useful for diagnosing admin access issues."""
    user = update.effective_user
    chat = update.effective_chat
    in_env_list = _is_admin(user.id)
    is_chat_admin = await _is_chat_admin(update, context)
    await update.message.reply_text(
        f"🍪 *Your Telegram info:*\n"
        f"User ID: `{user.id}`\n"
        f"Username: @{user.username or 'none'}\n"
        f"First name: {user.first_name}\n"
        f"In ADMIN_USER_IDS: {'✅ YES' if in_env_list else '❌ NO'}\n"
        f"Is chat admin: {'✅ YES' if is_chat_admin else '❌ NO'}\n"
        f"*Bot admin access: {'✅ YES' if is_chat_admin else '❌ NO'}*\n\n"
        f"*This chat:*\n"
        f"Chat ID: `{chat.id}`\n"
        f"Chat type: {chat.type}",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------------------------
# /chatid — returns the current chat's Telegram ID (for ALLOWED_CHAT_IDS config)
# ---------------------------------------------------------------------------
async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Returns the chat ID of the current group/channel. Useful for setting ALLOWED_CHAT_IDS."""
    chat = update.effective_chat
    await update.message.reply_text(
        f"🍪 *Chat ID for this channel:*\n`{chat.id}`\n\n"
        f"Add this to your `.env` file:\n"
        f"`ALLOWED_CHAT_IDS={chat.id}`\n\n"
        f"For multiple channels, separate with commas:\n"
        f"`ALLOWED_CHAT_IDS={chat.id},-1009876543210`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------------------------
# /setmode — switch between listen and answer modes at runtime (admin only)
# ---------------------------------------------------------------------------
async def cmd_setmode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /setmode listen  — switch to listener mode (stops answering questions)
    /setmode answer  — switch back to primary/answer mode
    /setmode status  — show the current mode
    """
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    if not await _is_chat_admin(update, context):
        await update.message.reply_text("🚫 Admin only command.")
        return

    arg = (context.args[0].lower() if context.args else "status")

    if arg in ("listen", "listener"):
        config.BOT_MODE = "listener"
        await update.message.reply_text(
            "🔇 *Mode set to LISTENER.*\n"
            "I will no longer answer questions in this session. "
            "I will only save messages when admins use `/cookiejar` or `/save`.",
            parse_mode=ParseMode.MARKDOWN,
        )
    elif arg in ("answer", "primary"):
        config.BOT_MODE = "primary"
        await update.message.reply_text(
            "🍪 *Mode set to ANSWER (primary).*\n"
            "I'm back! Ask me anything about $COOK and CookieNet. NOM NOM NOM!",
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
            "Usage:\n"
            "• `/setmode answer` — enable Q&A mode\n"
            "• `/setmode listen` — enable listener/silent mode\n"
            "• `/setmode status` — show current mode",
            parse_mode=ParseMode.MARKDOWN,
        )


# ---------------------------------------------------------------------------
# Message handler: @mention replies and plain questions
# ---------------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not config.is_allowed_chat(update.effective_chat.id):
        return
    # In listener mode, ignore all non-command messages
    if config.BOT_MODE == "listener":
        return
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
# /debug — dump full runtime config (no auth required so we can diagnose)
# ---------------------------------------------------------------------------
async def cmd_debug(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dumps runtime config for diagnostics. Available to everyone."""
    import os
    user = update.effective_user
    chat = update.effective_chat
    sender_chat = update.message.sender_chat  # set when posting as a channel/group

    token_preview = config.BOT_TOKEN[:10] + "..." if config.BOT_TOKEN else "NOT SET"
    grok_preview  = config.AI_API_KEY[:10] + "..." if config.AI_API_KEY else "NOT SET"
    github_preview = config.GITHUB_TOKEN[:10] + "..." if config.GITHUB_TOKEN else "NOT SET"

    lines = [
        "🍪 *CookieJar Debug Dump*",
        "",
        "*Runtime config:*",
        f"• BOT\\_TOKEN: `{token_preview}`",
        f"• GROK\\_API\\_KEY: `{grok_preview}`",
        f"• GITHUB\\_TOKEN: `{github_preview}`",
        f"• GITHUB\\_REPO: `{config.GITHUB_REPO}`",
        f"• BOT\\_MODE: `{config.BOT_MODE}`",
        f"• BOT\\_USERNAME: `{config.BOT_USERNAME}`",
        f"• ADMIN\\_USER\\_IDS: `{config.ADMIN_USER_IDS}`",
        f"• ALLOWED\\_CHAT\\_IDS: `{config.ALLOWED_CHAT_IDS}`",
        "",
        "*Caller info:*",
        f"• effective\\_user.id: `{user.id if user else 'None'}`",
        f"• effective\\_user.username: `@{user.username if user else 'None'}`",
        f"• sender\\_chat: `{sender_chat.id if sender_chat else 'None'}` ({sender_chat.type if sender_chat else 'N/A'})",
        f"• chat.id: `{chat.id}`",
        f"• chat.type: `{chat.type}`",
        f"• is\\_admin: `{_is_admin(user.id) if user else False}`",
        "",
        "*Env check (raw os.environ):*",
        f"• ADMIN\\_USER\\_IDS env: `{os.environ.get('ADMIN_USER_IDS', 'NOT SET')}`",
        f"• BOT\\_MODE env: `{os.environ.get('BOT_MODE', 'NOT SET')}`",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
