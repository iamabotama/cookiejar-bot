"""CookieJar Bot — run this file to start the bot."""

from pathlib import Path
from dotenv import load_dotenv

# MUST load .env before any cookiejar module is imported,
# because config.py reads os.environ at import time.
load_dotenv(Path(__file__).parent / ".env")

from cookiejar.bot import main  # noqa: E402

if __name__ == "__main__":
    main()
