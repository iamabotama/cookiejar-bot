# 🤖 BotFather Setup Guide — CookieJar Bot

This guide walks you through registering your CookieJar bot on Telegram using **@BotFather**.

---

## Step 1 — Open BotFather

Open Telegram and search for **@BotFather** (it has a blue verified checkmark — it is the official Telegram bot manager). Tap it and press **Start**.

---

## Step 2 — Create a New Bot

Send this command:

```
/newbot
```

---

## Step 3 — Set the Display Name

BotFather will ask:
> *"Alright, a new bot. How are we going to call it? Please choose a name for your bot."*

Type the display name:

```
CookieJar
```

---

## Step 4 — Set the Username

BotFather will ask:
> *"Good. Now let's choose a username for your bot. It must end in `bot`."*

Type:

```
CookieJarBot
```

> If `CookieJarBot` is already taken, try `CookieJar_Bot`, `CookieJarCook`, or `CookieJarCookBot`.
> Whatever username you land on, update `TELEGRAM_BOT_USERNAME` in your `.env` file to match (without the `@`).

---

## Step 5 — Copy Your Bot Token

BotFather will reply with something like:

```
Done! Congratulations on your new bot. You will find it at t.me/CookieJarBot.
Use this token to access the HTTP API:
1234567890:ABCDefGhIJKlmNoPQRsTUVwXyZ
```

**Copy that token.** It goes into your `.env` file as:

```
TELEGRAM_BOT_TOKEN=1234567890:ABCDefGhIJKlmNoPQRsTUVwXyZ
```

> Keep this token secret. Anyone with it can control your bot.

---

## Step 6 — Set the Bot Description (Recommended)

Run:

```
/setdescription
```

Select `@CookieJarBot`, then paste:

```
CookieJar is the official AI assistant for the Cookie Boy ($COOK) community on CookieNet. Ask me anything about $COOK — NOM NOM NOM! 🍪
```

---

## Step 7 — Set the Bot Profile Photo (Recommended)

Run:

```
/setuserpic
```

Select `@CookieJarBot`, then upload the **Cookie Boy logo** (`assets/cookieboy_logo.png` in this repo). This makes the bot instantly recognizable in community channels.

---

## Step 8 — Register Commands in BotFather (Recommended)

Run:

```
/setcommands
```

Select `@CookieJarBot`, then paste this entire block:

```
start - Welcome message
help - Show all commands
ask - Ask CookieJar a question
stats - Knowledge base stats
cookiejar - Drop a reply or text into the knowledge jar
ingest - [Admin] Ingest a website URL
addpost - [Admin] Add a manual post
listentries - [Admin] List active entries
liststale - [Admin] List stale entries
stale - [Admin] Mark entry as stale
archive - [Admin] Archive an entry
syncnow - [Admin] Force GitHub sync
stalecheck - [Admin] Run auto stale check
```

---

## Step 9 — Disable Privacy Mode for Group Channels (Required)

By default, bots in groups only receive messages that begin with `/`. To allow CookieJar to see `@CookieJarBot` mentions and reply-based commands, you must disable privacy mode:

```
/setprivacy
```

Select `@CookieJarBot` → choose **Disable**.

> **Important:** This must be done before adding the bot to any group or channel, or it will not respond to `@mentions`.

---

## Step 10 — Add the Bot to Your Channels

Once the bot is running (see `README.md`), add `@CookieJarBot` to your Telegram channels:

1. Open the channel settings.
2. Go to **Administrators** → **Add Administrator**.
3. Search for `@CookieJarBot` and add it.
4. Grant it permission to **read messages** and **send messages**.

For the **listener bot** (admin/whale channels), repeat with the second bot token and `BOT_MODE=listener`.

---

## Summary Checklist

| Step | Action | Required |
|------|--------|----------|
| 1 | Open @BotFather | Yes |
| 2 | `/newbot` | Yes |
| 3 | Name: `CookieJar` | Yes |
| 4 | Username: `CookieJarBot` | Yes |
| 5 | Copy token to `.env` | Yes |
| 6 | Set description | Recommended |
| 7 | Upload Cookie Boy logo | Recommended |
| 8 | Register commands | Recommended |
| 9 | Disable privacy mode | **Required for groups** |
| 10 | Add bot to channels | Yes |

---

*Next step: See `README.md` for full environment setup and deployment instructions.*
