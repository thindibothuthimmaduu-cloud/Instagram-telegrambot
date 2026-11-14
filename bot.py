import os
import re
import asyncio
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing")

app = Flask(__name__)

@app.route("/")
def home():
    return "Instagram Telegram Bot is running!"

@app.route("/health")
def health():
    return "OK", 200


def get_instagram_url(text):
    match = re.search(
        r"https?://(?:www\.)?instagram\.com/[^\s]+",
        text
    )
    if not match:
        return None

    url = match.group(0).rstrip(".,!?)]}")
    host = urlparse(url).hostname

    if host not in ("instagram.com", "www.instagram.com"):
        return None

    return url


def download_media(url, folder):
    options = {
        "outtmpl": str(Path(folder) / "%(autonumber)03d-%(id)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "retries": 2,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])

    extensions = {
        ".mp4", ".mov", ".m4v", ".webm",
        ".jpg", ".jpeg", ".png", ".webp"
    }

    return sorted(
        p for p in Path(folder).iterdir()
        if p.is_file() and p.suffix.lower() in extensions
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome! Send me a public Instagram Reel or Post link."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = get_instagram_url(update.message.text or "")

    if not url:
        await update.message.reply_text(
            "Please send a valid Instagram Reel or Post link."
        )
        return

    status = await update.message.reply_text(
        "Downloading media... Please wait."
    )

    try:
        with tempfile.TemporaryDirectory() as folder:
            files = await asyncio.to_thread(
                download_media, url, folder
            )

            if not files:
                await status.edit_text(
                    "No media found. This post may be private "
                    "or unavailable."
                )
                return

            sent = 0

            for file in files:
                if file.stat().st_size > 49 * 1024 * 1024:
                    continue

                with open(file, "rb") as media:
                    if file.suffix.lower() in (
                        ".mp4", ".mov", ".m4v", ".webm"
                    ):
                        await update.message.reply_video(
                            video=media,
                            supports_streaming=True
                        )
                    else:
                        # Send as document to preserve image quality
                        await update.message.reply_document(
                            document=media,
                            filename=file.name
                        )

                sent += 1

            await status.edit_text(
                f"Completed! {sent} media file(s) sent."
                if sent else
                "No supported files could be sent."
            )

    except Exception as error:
        print("Download error:", repr(error))
        await status.edit_text(
            "Download failed. Instagram may have restricted access."
        )


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send an Instagram Reel or Post link."
    )


def run_bot():
    bot = Application.builder().token(TOKEN).build()

    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)
    )
    bot.add_handler(MessageHandler(filters.COMMAND, unknown))

    bot.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

