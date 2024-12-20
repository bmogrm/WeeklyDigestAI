import sqlite3
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional
import crypto

# База данных SQLite
DB_NAME = "digestBot.db"

def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_NAME)

def init_db() -> None:
    """Инициализация базы данных."""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                username TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY,
                chat_title TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                message TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
            user_id INTEGER PRIMARY KEY,
            chat_id INTEGER NOT NULL,
            frequency TEXT DEFAULT 'weekly', -- daily, every_tree_days, weekly
            next_run DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)

def set_schedule(user_id: int, chat_id: int, frequency: str) -> None:
    """Устанавливает расписание для пользователя."""
    with get_connection() as conn:
        conn.cursor().execute("""
            INSERT INTO schedules (user_id, chat_id, frequency, next_run)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                frequency = excluded.frequency,
                next_run = datetime('now')
        """, (user_id, chat_id, frequency))

def get_schedule(user_id: int) -> Optional[tuple]:
    """Получает расписание пользователя."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT frequency, next_run FROM schedules
            WHERE user_id = ?
        """, (user_id,))
        return cursor.fetchone()
    
def update_next_run(user_id: int) -> None:
    """Обновляет время следующего запуска для пользователя."""
    with get_connection() as conn:
        conn.cursor().execute("""
            UPDATE schedules
            SET next_run = CASE frequency
                WHEN 'daily' THEN datetime(next_run, '+1 day')
                WHEN 'every_three_days' THEN datetime(next_run, '+3 day')
                WHEN 'weekly' THEN datetime(next_run, '+7 day')
            END
            WHERE user_id = ?
        """, (user_id,))

def add_user(user_id, first_name, last_name, username) -> None:
    with get_connection() as conn:
        conn.cursor().execute("""
            INSERT OR IGNORE INTO users (id, first_name, last_name, username)
            VALUES (?, ?, ?, ?)
        """, (user_id, first_name, last_name, username))

def add_chat(chat_id, titile) -> None:
    with get_connection() as conn:
        conn.cursor().execute("""
            INSERT OR IGNORE INTO chats (id, chat_title)
            VALUES (?, ?)
        """, (chat_id, titile))

async def save_message(chat_id, chat_title, user_id, 
                       user_first_name, user_last_name, 
                       username, message) -> None:
    """Сохраняет сообщение в базу данных."""
    encrypted_message = crypto.encrypt_message(message)  # Шифруем текст
    add_chat(chat_id, chat_title)  # Убедимся, что чат существует
    add_user(user_id, user_first_name, user_last_name, username)  # Убедимся, что пользователь существует

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages (chat_id, user_id, message, timestamp)
            VALUES (?, ?, ?, ?)
        """, (chat_id, user_id, encrypted_message, datetime.now()))


async def collect_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для сбора сообщений."""
    message = update.message.text

    if len(message) > 1500:
        await update.message.reply_text("Сообщение не было запомнено, слишком длинное сообщение.")
        return

    chat_id = update.effective_chat.id
    chat_title = update.effective_chat.title
    user_id = update.effective_user.id
    user_first_name = update.effective_user.first_name
    user_last_name = update.effective_user.last_name
    username = update.effective_user.username

    await save_message(chat_id, chat_title, user_id, user_first_name, user_last_name, username, message)
    logging.info(f"Сохранено сообщение: {user_first_name, user_last_name} -- {message}")