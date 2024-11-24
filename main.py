# main.py
import db
import command
import logging
import os
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токены
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHATAI_API_KEY = os.getenv('CHATAI_API_KEY')  # Ключ от chatai.edro.su
CHAT_API_TOKEN = os.getenv('CHAT_API_TOKEN')
CHATAI_API_URL = "https://chatai.edro.su/ollama/api/generate"  # URL API ChatAI
MY_ID = int(os.getenv('MY_ID'))

def main() -> None:
    db.init_db()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("digest", command.generate_digest))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), db.collect_message))

    logging.info("Бот запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()
