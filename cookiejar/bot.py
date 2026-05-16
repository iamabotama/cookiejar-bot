"""
bot.py — CookieJar bot entry point.

Registers all handlers from the single unified handlers.py module.
Mode (listener vs answer) is set in config; the same handler set is
registered regardless of mode — mode only affects what the bot responds to.
"""

import fcntl
import logging
import sys
import threading

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from . import config, github_sync, knowledge_store
from .handlers import (
    cmd_admin,
    cmd_announce,
    cmd_ask,
    cmd_ca,
    cmd_chatid,
    cmd_crawl,
    cmd_deletelast,
    cmd_help,
    cmd_links,
    cmd_listentries,
    cmd_liststale,
    cmd_save,
    cmd_setmode,
    cmd_start,
    cmd_stale,
    cmd_stats,
    cmd_syncnow,
    cmd_tg,
    cmd_updates,
    cmd_whoami,
    cmd_x,
    get_bot_commands,
    handle_message,
)

log = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
        stream=sys.stdout,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)


def _validate_config() -> None:
    missing = config.validate()
    if missing:
        log.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)


async def _post_init(app: Application) -> None:
    cmds = get_bot_commands()
    await app.bot.set_my_commands(cmds)
    log.info("CookieJar started in %s mode. Bot: @%s", config.BOT_MODE.upper(), config.BOT_USERNAME)


def build_app() -> Application:
    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(_post_init)
        .build()
    )

    # Public commands
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("ask",      cmd_ask))
    app.add_handler(CommandHandler("updates",  cmd_updates))
    app.add_handler(CommandHandler("stats",    cmd_stats))
    app.add_handler(CommandHandler("tg",       cmd_tg))
    app.add_handler(CommandHandler("x",        cmd_x))
    app.add_handler(CommandHandler("ca",       cmd_ca))
    app.add_handler(CommandHandler("token",    cmd_ca))   # alias for /ca
    app.add_handler(CommandHandler("links",    cmd_links))

    # Admin commands
    app.add_handler(CommandHandler("save",        cmd_save))
    app.add_handler(CommandHandler("crawl",       cmd_crawl))
    app.add_handler(CommandHandler("stale",       cmd_stale))
    app.add_handler(CommandHandler("deletelast",  cmd_deletelast))
    app.add_handler(CommandHandler("announce",    cmd_announce))
    app.add_handler(CommandHandler("listentries", cmd_listentries))
    app.add_handler(CommandHandler("liststale",   cmd_liststale))
    app.add_handler(CommandHandler("syncnow",     cmd_syncnow))
    app.add_handler(CommandHandler("setmode",     cmd_setmode))
    app.add_handler(CommandHandler("chatid",      cmd_chatid))
    app.add_handler(CommandHandler("admin",       cmd_admin))
    app.add_handler(CommandHandler("whoami",      cmd_whoami))

    # Message handler for @mentions and DMs
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app


def main() -> None:
    _setup_logging()
    _validate_config()

    # Prevent two instances from running simultaneously with the same token.
    # A second process will fail to acquire the lock and exit cleanly.
    lock_path = config.CACHE_DIR / "cookiejar.lock"
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log.error(
            "Another CookieJar instance is already running (lock: %s). Exiting.",
            lock_path,
        )
        sys.exit(1)

    log.info("CookieJar starting in %s mode", config.BOT_MODE.upper())

    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    config.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    config.SOURCES_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Pulling knowledge cache from GitHub...")
    github_sync.sync_knowledge_from_github()

    staled = knowledge_store.auto_stale_check()
    if staled:
        log.info("Startup stale check: %d entries marked stale", staled)

    sync_thread = threading.Thread(target=github_sync.start_sync_loop, daemon=True)
    sync_thread.start()

    app = build_app()
    log.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
