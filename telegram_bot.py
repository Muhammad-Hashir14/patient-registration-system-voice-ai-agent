"""
Free Telegram bot interface for the patient registration agent.
No credit card needed.

Setup:
1. Message @BotFather on Telegram → /newbot → copy the token
2. Set TELEGRAM_BOT_TOKEN in .env
3. Run: python telegram_bot.py
"""
import asyncio
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

API_BASE = "http://localhost:8000"

# Each Telegram user gets their own session
def get_session_id(user_id: int) -> str:
    return f"telegram-{user_id}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to the Patient Registration Assistant!\n"
        "Just start talking — I'll guide you through registration."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    session_id = get_session_id(user_id)
    message = update.message.text

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        resp = requests.post(
            f"{API_BASE}/chat",
            json={"session_id": session_id, "message": message},
            timeout=60,
        )
        data = resp.json()
        reply = data["data"]["message"] if not data.get("error") else f"Error: {data['error']}"
    except Exception as e:
        reply = f"Sorry, I had a technical issue. Please try again. ({e})"

    await update.message.reply_text(reply)


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERROR: Set TELEGRAM_BOT_TOKEN in your .env file")
        print("Get a free token from @BotFather on Telegram")
        exit(1)

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running... Press Ctrl+C to stop")
    app.run_polling()
