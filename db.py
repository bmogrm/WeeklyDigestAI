import sqlite3
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

# База данных SQLite
DB_NAME = "digestBot.db"

def init_db():
    """Инициализация базы данных."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            chat_title TEXT,
            user_id INTEGER,
            user_first_name TEXT,
            user_last_name TEXT,
            message TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

async def save_message(chat_id, chat_title, user_id, user_first_name, user_last_name, message):
    """Сохраняет сообщение в базу данных."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO messages (chat_id, chat_title, user_id, user_first_name, user_last_name, message, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (chat_id, chat_title, user_id, user_first_name, user_last_name, message, datetime.now()))
    conn.commit()
    conn.close()

async def collect_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для сбора сообщений."""

    if len(message) > 1500:
            await update.message.reply_text("Сообщение слишком длинное.")
            return

    chat_id = update.effective_chat.id
    chat_title = update.effective_chat.title
    user_id = update.effective_user.id
    user_first_name = update.effective_user.first_name
    user_last_name = update.effective_user.last_name
    message = update.message.text

    await save_message(chat_id, chat_title, user_id, user_first_name, user_last_name, message)
    logging.info(f"Сохранено сообщение: {user_first_name, user_last_name} -- {message}")