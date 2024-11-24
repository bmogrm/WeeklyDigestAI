import db
import main
import logging
import sqlite3
import requests
from md2tgmd import escape
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

async def generate_digest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Формирует дайджест за последнюю неделю с использованием ChatAI."""

    if update.effective_user.id != main.MY_ID:
        await update.message.reply_text("Шо ты лысый, плаки-плаки, тебе нельзя :)")
        return
    
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    one_week_ago = datetime.now() - timedelta(days=7)
    cursor.execute("""
        SELECT message, timestamp FROM messages
        WHERE timestamp > ?
        AND chat_id = ?
        ORDER BY timestamp
    """, (one_week_ago, update.effective_chat.id))
    messages = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not messages:
        await update.message.reply_text("За последнюю неделю сообщений не найдено.")
        return

    # Формируем запрос к ChatAI
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    prompt = f"Создай из этих сообщений еженедельный дайджест за период {start_date} - {end_date}, нужна точная информация касательно учебы:\n" + "\n".join(messages)
    payload = {
        "model": "gemma2:9b",
        "prompt": prompt,
        "stream": False
    }

    try:
        await update.message.reply_text(f"Генерирую дайджест...")
        response = requests.post(
            main.CHATAI_API_URL,
            json=payload,
            headers={'Authorization': f'Bearer {main.CHAT_API_TOKEN}'}
        )
        response.raise_for_status()
        data = response.json()
        
        if "response" not in data:
            raise ValueError("Некорректный ответ от API: отсутствует ключ 'response'")
        
        digest = data["response"]
        
        # Разделяем длинные сообщения
        for chunk in [digest[i:i+4000] for i in range(0, len(digest), 4000)]:
            await update.message.reply_text(f"{escape(chunk)}", parse_mode="MarkdownV2")
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка запроса к ChatAI: {e}")
        await update.message.reply_text("Ошибка при генерации дайджеста. Попробуйте позже.")
    except Exception as e:
        logging.error(f"Непредвиденная ошибка: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")