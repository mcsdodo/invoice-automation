"""Quick test for Telegram bot credentials."""
import os
import asyncio
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

if not bot_token or not chat_id:
    print("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not found in .env")
    exit(1)

async def main():
    bot = Bot(token=bot_token)
    me = await bot.get_me()
    print(f"Telegram Bot: @{me.username} ({me.first_name})")

    msg = await bot.send_message(chat_id=chat_id, text="Test message from Invoice Automation setup.")
    print(f"Message sent to chat {chat_id}, message_id: {msg.message_id}")

asyncio.run(main())
