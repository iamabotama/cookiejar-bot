"""
CookieJar Bot — Main Entry Point
Wires together handlers, starts the background sync loop, and launches the bot.
"""

import logging
import threading
import sys

from telegram import BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from . import config, github_sync, knowledge_store
from .handlers_primary import (
    cmd_cookiejar,
    cmd_start as primary_start,
    cmd_help as primary_help,
    cmd_ask,
    cmd_stats,
    cmd_ingest,
    cmd_addpost,
    cmd_listentries,
    cmd_liststale,
    cmd_stale,
    cmd_archive,
    cmd_syncnow,
    cmd_stalecheck,
    handle_message as primary_message,
)
from .handlers_listener import (
    cmd_cookiejar as listener_cookiejar,
    cmd_start as listener_start,
    cmd_help as listener_help,
    cmd_save,
    cmd_saveingest,
    handle_message as listener_message,
)

log = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
        stream=sys.stdout,
    )
    # Reduce noise from httpx
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _validate_config() -> None:
    missing = config.validate()
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)


def _set_bot_commands_primary(app: Application) -> None:
    """Register slash command descriptions shown in Telegram's command menu."""
    commands = [
        BotCommand("start", "Welcome message"),
        BotCommand("help", "Show all commands"),
        BotCommand("ask", "Ask CookieJar a question"),
        BotCommand("stats", "Knowledge base statistics"),
        BotCommand("ingest", "[Admin] Ingest a website URL"),
        BotCommand("addpost", "[Admin] Add a manual post"),
        BotCommand("listentries", "[Admin] List active entries"),
        BotCommand("liststale", "[Admin] List stale entries"),
        BotCommand("stale", "[Admin] Mark entry as stale"),
        BotCommand("archive", "[Admin] Archive an entry"),
        BotCommand("syncnow", "[Admin] Force GitHub sync"),
        BotCommand("stalecheck", "[Admin] Run auto stale check"),
        BotCommand("cookiejar", "[Admin] Drop a reply or text into the knowledge jar"),
    ]
    # Commands are set at startup via post_init
    return commands


def _set_bot_commands_listener(app: Application) -> None:
    return [
        BotCommand("start", "Welcome message"),
        BotCommand("help", "Show commands"),
        BotCommand("save", "[Admin] Save replied message to knowledge base"),
        BotCommand("saveingest", "[Admin] Ingest a URL into knowledge base"),
        BotCommand("cookiejar", "[Admin] Drop a reply into the knowledge jar"),
    ]


async def _post_init_primary(app: Application) -> None:
    cmds = _set_bot_commands_primary(app)
    await app.bot.set_my_commands(cmds)
    log.info("CookieJar PRIMARY mode started. Bot: @%s", config.BOT_USERNAME)


async def _post_init_listener(app: Application) -> None:
    cmds = _set_bot_commands_listener(app)
    await app.bot.set_my_commands(cmds)
    log.info("CookieJar LISTENER mode started. Bot: @%s", config.BOT_USERNAME)


def build_primary_app() -> Application:
    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(_post_init_primary)
        .build()
    )

    app.add_handler(CommandHandler("start", primary_start))
    app.add_handler(CommandHandler("help", primary_help))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("ingest", cmd_ingest))
    app.add_handler(CommandHandler("addpost", cmd_addpost))
    app.add_handler(CommandHandler("listentries", cmd_listentries))
    app.add_handler(CommandHandler("liststale", cmd_liststale))
    app.add_handler(CommandHandler("stale", cmd_stale))
    app.add_handler(CommandHandler("archive", cmd_archive))
    app.add_handler(CommandHandler("syncnow", cmd_syncnow))
    app.add_handler(CommandHandler("stalecheck", cmd_stalecheck))
    app.add_handler(CommandHandler("cookiejar", cmd_cookiejar))

    # Handle all text messages (for @mention and DM questions)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, primary_message))

    return app


def build_listener_app() -> Application:
    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(_post_init_listener)
        .build()
    )

    app.add_handler(CommandHandler("start", listener_start))
    app.add_handler(CommandHandler("help", listener_help))
    app.add_handler(CommandHandler("save", cmd_save))
    app.add_handler(CommandHandler("saveingest", cmd_saveingest))
    app.add_handler(CommandHandler("cookiejar", listener_cookiejar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, listener_message))

    return app


def main() -> None:
    _setup_logging()
    _validate_config()

    log.info("CookieJar starting in %s mode", config.BOT_MODE.upper())

    # Ensure local directories exist
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    config.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    config.SOURCES_DIR.mkdir(parents=True, exist_ok=True)

    # Initial pull from GitHub
    log.info("Pulling knowledge cache from GitHub...")
    github_sync.sync_knowledge_from_github()

    # Run auto stale check on startup
    staled = knowledge_store.auto_stale_check()
    if staled:
        log.info("Startup stale check: %d entries marked stale", staled)

    # Start background GitHub sync thread
    sync_thread = threading.Thread(target=github_sync.start_sync_loop, daemon=True)
    sync_thread.start()

    # Build and run the appropriate bot
    if config.BOT_MODE == "listener":
        app = build_listener_app()
    else:
        app = build_primary_app()

    log.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
