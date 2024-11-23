# main.py
import logging
from dotenv import load_dotenv
from md2tgmd import escape
import os
import sqlite3
from datetime import datetime, timedelta
import requests  # Для запросов к ChatAI API
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токены
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHATAI_API_KEY = os.getenv('CHATAI_API_KEY')  # Ключ от chatai.edro.su
CHAT_API_TOKEN = os.getenv('CHAT_API_TOKEN')
CHATAI_API_URL = "https://chatai.edro.su/ollama/api/generate"  # URL API ChatAI

# База данных SQLite
DB_NAME = "digestBot.db"

# def escape_markdown_v2(text):
#     special_chars = r"_[]()~`>#+|{}.!-"
#     for char in special_chars:
#         text = text.replace(char, f'\\{char}')
#     return text

def init_db():
    """Инициализация базы данных."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

async def save_message(chat_id, message):
    """Сохраняет сообщение в базу данных."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO messages (chat_id, message, timestamp)
        VALUES (?, ?, ?)
    """, (chat_id, message, datetime.now()))
    conn.commit()
    conn.close()

async def collect_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для сбора сообщений."""
    chat_id = update.effective_chat.id
    message = update.message.text

    await save_message(chat_id, message)
    logging.info(f"Сохранено сообщение: {message}")

async def generate_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Формирует дайджест за последнюю неделю с использованием ChatAI."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    one_week_ago = datetime.now() - timedelta(days=7)
    cursor.execute("""
        SELECT message FROM messages
        WHERE timestamp > ?
        and chat_id = ?
        ORDER BY timestamp
    """, (one_week_ago, update.effective_chat.id))
    messages = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not messages:
        await update.message.reply_text("За последнюю неделю сообщений не найдено.")
        return

    # Формируем запрос к ChatAI
    payload = {"model":"gemma2:9b", "prompt": f"Создай из этих сообщений еженедельный дайджест, за {datetime.now() - timedelta(days=7)} - {datetime.now()}: {messages}", "stream": False}

    try:
        await update.message.reply_text(f"Генерирую дайджест...")
        response = requests.post(CHATAI_API_URL, json=payload, headers={'Authorization': f'Bearer {CHAT_API_TOKEN}'})
        response.raise_for_status()
        data = response.json()["response"]

        # Предполагаем, что в ответе есть ключ 'result' с дайджестом
        
        await update.message.reply_text(f"{escape(data)}", parse_mode="MarkdownV2")
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка запроса к ChatAI: {e}")
        await update.message.reply_text("Ошибка при генерации дайджеста. Попробуйте позже.")

def main():
    """Главная функция."""
    init_db()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Команды
    app.add_handler(CommandHandler("digest", generate_digest))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), collect_message))

    logging.info("Бот запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()
