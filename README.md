# 🍪 CookieJar Bot

**CookieJar** is an AI-powered Telegram bot built specifically for the **Cookie Boy ($COOK / CookieNet)** crypto community. 

It acts as an automated community expert. It ingests data from URLs or manual admin posts, stores that data in a timestamped GitHub-backed knowledge base, and uses Grok AI to answer community questions strictly based on that ingested knowledge.

---

## 🌟 Features

- **Web Ingestion**: Send a URL to the bot, and it will scrape the text, summarize it, and add it to its knowledge base.
- **GitHub Sync**: The knowledge base is stored locally for speed but automatically syncs to a private GitHub repository (`iamabotama/cookiejar-bot`) for backup, auditing, and version control.
- **Grok AI Q&A**: Answers questions natively in Telegram using the xAI Grok API, strictly scoped to CookieNet. It will not speculate on price or discuss other networks.
- **Post Adjustment**: Reply to any message with `@CookieJarBot <instruction>` to have the AI rewrite or improve the post based on community knowledge.
- **Dual Modes**: 
  - `primary`: The main bot that answers questions and handles commands.
  - `listener`: A silent mode for admin/whale channels. Admins can reply to important messages with `/save` to silently push that data to the knowledge base for the primary bot to use.
- **Cookie Boy Easter Egg**: Every time data is successfully ingested, the bot replies with a generated image of Cookie Boy devouring data cookies!

---

## 🚀 Setup & Deployment Guide

You do not need to write any code to get this running. Follow these steps to deploy your bot.

### Step 1: Create the Telegram Bot (BotFather)
1. Open Telegram and search for **@BotFather** (the official bot with a blue checkmark).
2. Send the command `/newbot`.
3. Choose a display name (e.g., `CookieJar`).
4. Choose a username (e.g., `CookieBoxBot` or `CookieJarBot`).
5. BotFather will give you a **Bot Token** (a long string of letters and numbers). Save this.

### Step 2: Get your Grok (xAI) API Key
1. Go to the [xAI Console](https://console.x.ai/).
2. Create an account or log in.
3. Navigate to **API Keys** and generate a new key. Save this.

### Step 3: Get your Telegram User ID (For Admin Access)
To use admin commands like `/ingest` or `/save`, the bot needs to know your Telegram User ID.
1. In Telegram, search for **@userinfobot** and start it.
2. It will reply with your ID (a string of numbers like `123456789`). Save this.

### Step 4: Deploy the Bot

You can run this bot on any server (like a cheap $5/mo DigitalOcean droplet, AWS EC2, or Heroku).

1. **Clone the repository:**
   ```bash
   git clone https://github.com/iamabotama/cookiejar-bot.git
   cd cookiejar-bot
   ```

2. **Install dependencies:**
   *(Requires Python 3.10+)*
   ```bash
   pip install -r requirements.txt
   ```

3. **Set your environment variables:**
   You can set these in your terminal, or use a `.env` file if you install `python-dotenv`.

   ```bash
   export TELEGRAM_BOT_TOKEN="your_botfather_token_here"
   export TELEGRAM_BOT_USERNAME="CookieJarBot"
   export GROK_API_KEY="your_xai_api_key_here"
   export GITHUB_TOKEN="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"
   export GITHUB_REPO="iamabotama/cookiejar-bot"
   export ADMIN_USER_IDS="your_telegram_user_id_here"
   
   # Optional: set to 'listener' to run the secondary silent bot
   export BOT_MODE="primary" 
   ```

4. **Run the bot:**
   ```bash
   python main.py
   ```

*(For production, it is highly recommended to run the bot using `systemd`, `pm2`, or `screen` so it stays running when you close your terminal).*

---

## 📚 Additional Guides

- **[BotFather Setup Guide](docs/botfather-setup.md)** — Step-by-step instructions for registering your bot on Telegram

---

## 🛠️ Commands

### Public Commands (Anyone)
- `/start` — Welcome message
- `/help` — List available commands
- `/ask <question>` — Ask CookieJar a question
- `/stats` — View how many entries are in the knowledge base

### Admin Commands (Primary Mode)
- `/ingest <url>` — Scrape a website and add it to the knowledge base
- `/addpost <text>` — Add manual text to the knowledge base
- `/listentries` — Show all active knowledge entries
- `/liststale` — Show older entries that might need review
- `/archive <id>` — Move an entry to cold storage
- `/syncnow` — Force an immediate push/pull with GitHub
- `/cookiejar` — (Reply to any message) Drop it straight into the knowledge jar; or `/cookiejar <text>` to save text directly

### Admin Commands (Listener Mode)
- `/save` — (Used as a reply) Push the replied-to message into the knowledge base
- `/saveingest <url>` — Silently ingest a URL
- `/cookiejar` — (Reply to any message) Drop it into the knowledge jar; or `/cookiejar <text>` to save text directly

---

## 🗄️ How the Knowledge Base Works

The bot stores all its knowledge in a local file: `knowledge/active.jsonl`. This makes answering questions incredibly fast.

Every 30 minutes, the bot pushes a backup of this file, along with raw text copies of everything it ingested, to the `iamabotama/cookiejar-bot` GitHub repository.

If you ever need to manually edit what the bot knows, you can edit `knowledge/active.jsonl` directly in GitHub. The bot will pull your changes automatically on its next sync!
