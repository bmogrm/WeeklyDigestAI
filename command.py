import db
import main
import logging
import sqlite3
import requests
import time
import crypto
import sys
from md2tgmd import escape
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

def generate_response_with_gpt(messages):
    """
    Отправляет запрос к API GPT-4o-mini через gen-api.ru и возвращает результат.
    :param messages: Список сообщений в формате [{"role": "user", "content": [{"type": "text", "text": "Ваш текст"}]}]
    :return: Результат обработки (строка или None в случае ошибки)
    """

    logging.info(f"GEN_API_TOKEN={main.CHATAI_API_KEY}")
    if not main.CHATAI_API_KEY:
        raise ValueError("Токен API отсутствует. Проверьте .env файл или переменные окружения.")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {main.CHATAI_API_KEY}"
    }

    # Формируем тело запроса
    input_data = {
        "callback_url": None,  # Не используем callback
        "messages": messages
    }

    try:
        # Шаг 1: Отправляем запрос на выполнение задачи
        response = requests.post(main.CHATAI_API_URL, json=input_data, headers=headers)
        response.raise_for_status()  # Проверяем на наличие HTTP ошибок
        task_data = response.json()
        
        if "request_id" not in task_data:
            logging.error("Не удалось получить request_id: Некорректный ответ.")
            return None
        
        request_id = task_data["request_id"]
        logging.info(f"Создана задача с request_id: {request_id}")
        
        # Шаг 2: Ожидаем завершения задачи (Long-Pooling)
        while True:
            time.sleep(2)  # Пауза перед каждым запросом
            status_response = requests.get(f"{main.CHATAI_API_URL}/{request_id}", headers=headers)
            status_response.raise_for_status()
            status_data = status_response.json()
            
            if status_data["status"] == "success":
                logging.info(f"Задача {request_id} выполнена.")
                return status_data["output"]  # Возвращаем результат
            elif status_data["status"] == "error":
                logging.error(f"Ошибка в задаче {request_id}: {status_data}")
                return None
            
            logging.info(f"Задача {request_id} ещё выполняется...")

    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка подключения к API: {e}")
        return None

async def generate_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Формирует дайджест за последнюю неделю с использованием GPT-4o-mini."""
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    one_week_ago = datetime.now() - timedelta(days=7)
    cursor.execute("""
        SELECT message FROM messages
        WHERE timestamp > ?
        AND chat_id = ?
        ORDER BY timestamp
    """, (one_week_ago, update.effective_chat.id))
    encrypted_messages = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not encrypted_messages:
        await update.message.reply_text("За последнюю неделю сообщений не найдено.")
        return
    
    messages = [crypto.decrypt_message(encrypted_message) for encrypted_message in encrypted_messages]

    # Формируем запрос для GPT-4o-mini
    formatted_messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": message}]
        } for message in messages
    ]

    await update.message.reply_text("Генерирую дайджест, подождите немного...")
    logging.info(f"Сообщение={formatted_messages}")
    # Отправляем запрос к GPT-4o-mini
    digest = generate_response_with_gpt(formatted_messages)
    if digest:
        # Делим длинный текст на части, если необходимо
        for chunk in [digest[i:i + 4000] for i in range(0, len(digest), 4000)]:
            await update.message.reply_text(chunk)
    else:
        await update.message.reply_text("Произошла ошибка при генерации дайджеста. Попробуйте позже.")


async def generate_digest_for_chat(chat_id: int, user_id: int) -> None:
    """Генерирует и отправляет дайджест в указанный чат."""
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    one_week_ago = datetime.now() - timedelta(days=7)
    cursor.execute("""
        SELECT message FROM messages
        WHERE timestamp > ? AND chat_id = ?
        ORDER BY timestamp
    """, (one_week_ago, chat_id))
    messages = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not messages:
        return

    prompt = f"Создай дайджест:\n" + "\n".join(messages)
    payload = {
        "model": "gemma2:9b",
        "prompt": prompt,
        "stream": False
    }

    try:
        response = requests.post(
            main.CHATAI_API_URL,
            json=payload,
            headers={'Authorization': f'Bearer {main.CHAT_API_TOKEN}'}
        )
        response.raise_for_status()
        data = response.json()
        digest = data["response"]

        # Отправка сообщения
        await main.app.bot.send_message(chat_id=chat_id, text=digest)
    except Exception as e:
        logging.error(f"Ошибка при отправке дайджеста для {chat_id}: {e}")


async def schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает меню для выбора частоты дайджеста."""
    keyboard = [
        [KeyboardButton("Ежедневно"), KeyboardButton("Раз в три дня")],
        [KeyboardButton("Еженедельно")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    await update.message.reply_text("Выберите частоту дайджеста:", reply_markup=reply_markup)

async def set_digest_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Устанавливает частоту дайджеста."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    frequency = update.message.text.strip().lower()

    logging.info(f"Получено сообщение: {frequency}")

    # Карта для преобразования текста в ключи БД
    frequency_map = {
        "ежедневно": "daily",
        "раз в три дня": "every_three_days",
        "еженедельно": "weekly"
    }

    if frequency not in frequency_map:
        await update.message.reply_text("Некорректный выбор. Попробуйте снова.")
        return

    db.set_schedule(user_id, chat_id, frequency_map[frequency])
    await update.message.reply_text(f"Частота дайджеста установлена: {frequency}.")