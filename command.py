import db
import logging
import sqlite3
import crypto
from md2tgmd import escape
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes
import asyncio

##################################################################################################

import requests as r
from os import getenv
from dotenv import load_dotenv
from telegram.helpers import escape_markdown

load_dotenv()
gpt_url="https://gptunnel.ru/v1/chat/completions"
TOKEN=getenv("GPT_API")

def get_completion(context, prompt, retry=0):
    response = r.post(gpt_url,                      
        headers={
            "Authorization": TOKEN
        },
        json={
            "model": "deepseek-3",
            "max_tokens": 7500,
            "temperature": 0.6,
            "messages": [
                {
                    "role": "system",
                    "content": f"{context}",
                },
                {
                    "role": "user",
                    "content": f"{prompt}",
                },
            ],
        }
    )
    print(response.json())
    if response.status_code == 200:
        return (
            response.json()["choices"][0]["message"]["content"],
            response.json()["usage"]["total_cost"]
        )
    else:
        if retry < 5:
            return get_completion(context, prompt, retry=retry + 1)
        else:
            return (f"Ошибка: {response.status_code} — {response.json()}", None)
        
def get_balance(retry=0):
    response = r.get("https://gptunnel.ru/v1/balance",                      
        headers={
            "Authorization": TOKEN
        }
    )
    if response.status_code == 200:
        return response.json()["balance"]
    else:
        if retry < 5:
            return get_balance(retry=retry + 1)
        else:
            return response.json()
        
##################################################################################################
from telegram.ext import ApplicationBuilder
import os
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
async def generate_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Формирует дайджест за последние 100 сообщений"""
    # 1. Получение сообщений из БД
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT message FROM messages
        WHERE chat_id = ?
        ORDER BY timestamp DESC
        LIMIT 100
    """, (update.effective_chat.id,))
    
    encrypted_messages = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not encrypted_messages:
        await update.message.reply_text("За последнюю неделю сообщений не найдено.")
        return
    
    # 2. Дешифровка сообщений
    messages = [crypto.decrypt_message(encrypted_message) for encrypted_message in encrypted_messages]
    
    # 3. Формирование промпта для GPT
    system_message = (
        "Ты ассистент для создания дайджестов чата. Проанализируй сообщения и создай структурированный дайджест:\n"
        "1. Выдели основные темы и обсуждения\n"
        "2. Кратко суммируй важные моменты\n"
        "3. Сохрани нейтральный тон\n"
        "4. Не добавляй информацию, которой нет в сообщениях\n"
        "5. Используй markdown для форматирования, не используй # для заголовков\n"
        "6. Используй эмодзи для визуала"
    )
    
    user_prompt = "Сообщения:\n" + "\n".join(
        [f"{i+1}. {msg}" for i, msg in enumerate(messages)]
    )

    # 4. Отправка запроса к GPT
    await update.message.reply_text("Генерирую дайджест, подождите немного...")
    logging.info(f"Начало генерации дайджеста для {len(messages)} сообщений")
    
    try:
        # Вызываем синхронную функцию в отдельном потоке
        digest, cost = await asyncio.to_thread(
            get_completion,
            context=system_message,
            prompt=user_prompt
        )
        if cost is None:
            await update.message.reply_text("Произошла ошибка при генерации дайджеста 202:\n")
            return
        logging.info(f"Дайджест сгенерирован успешно. Стоимость: {cost}")
        
        # 5. Отправка результата пользователю
        for chunk in [digest[i:i+4000] for i in range(0, len(digest), 4000)]:
            await update.message.reply_text(
                chunk,
                parse_mode="Markdown"
            )
            
    except Exception as e:
        logging.error(f"Ошибка генерации дайджеста: {str(e)}")
        await update.message.reply_text("Произошла ошибка при генерации дайджеста. Попробуйте позже.")

async def generate_digest_for_chat(chat_id):
    """Формирует дайджест за указанное пользователем время"""
    # 1. Получение сообщений из БД
    conn = sqlite3.connect(db.DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT frequency FROM schedules WHERE chat_id = ?
    """, (chat_id,))
    result = cursor.fetchone()

    if not result:
        await app.bot.send_message(chat_id=chat_id, text="Не удалось определить частоту дайджеста.")
        conn.close()
        return

    frequency = result[0]
    if frequency == "daily":
        delta = timedelta(days=1)
    elif frequency == "every_three_days":
        delta = timedelta(days=3)
    elif frequency == "weekly":
        delta = timedelta(days=7)
    else:
        await app.bot.send_message(chat_id=chat_id, text="Неверно указана частота в настройках.")
        conn.close()
        return
    
    since = datetime.now() - delta
    
    cursor.execute("""
        SELECT message FROM messages
        WHERE timestamp > ?
        AND chat_id = ?
        ORDER BY timestamp
    """, (since, chat_id))
    
    encrypted_messages = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not encrypted_messages:
        # Отправляем сообщение в чат
        await app.bot.send_message(chat_id=chat_id, text="За последнюю неделю сообщений не найдено.")
        db.update_next_run(chat_id)
        return
    
    # 2. Дешифровка сообщений
    messages = [crypto.decrypt_message(encrypted_message) for encrypted_message in encrypted_messages]
    
    # 3. Формирование промпта для GPT
    system_message = (
        "Ты ассистент для создания дайджестов чата. Проанализируй сообщения создай структурированный дайджест:\n"
        "1. Выдели основные темы и обсуждения\n"
        "2. Кратко суммируй важные моменты\n"
        "3. Сохрани нейтральный тон\n"
        "4. Не добавляй информацию, которой нет в сообщениях\n"
        "5. Используй markdown для форматирования, не используй # для заголовков\n"
        "6. Используй эмодзи для визуала"
    )
    
    user_prompt = "Сообщения:\n" + "\n".join(
        [f"{i+1}. {msg}" for i, msg in enumerate(messages)]
    )

    # 4. Отправка запроса к GPT
    await app.bot.send_message(chat_id=chat_id, text="Генерирую дайджест, подождите немного...")
    logging.info(f"Начало генерации дайджеста для {len(messages)} сообщений")
    
    try:
        # Вызываем синхронную функцию в отдельном потоке
        digest, cost = await asyncio.to_thread(
            get_completion,
            context=system_message,
            prompt=user_prompt
        )

        if cost is None:
            await app.bot.send_message("Произошла ошибка при генерации дайджеста 202:\n")
            return
        
        logging.info(f"Дайджест сгенерирован успешно. Стоимость: {cost}")
        
        # 5. Отправка результата пользователю
        for chunk in [digest[i:i+4000] for i in range(0, len(digest), 4000)]:
            await app.bot.send_message(
                chat_id=chat_id,
                text=chunk,
                parse_mode="Markdown"
            )
        # 6. Обновление следующей отправки
        db.update_next_run(chat_id)
            
    except Exception as e:
        logging.error(f"Ошибка генерации дайджеста: {str(e)}")
        await app.bot.send_message(chat_id=chat_id, text="Произошла ошибка при генерации дайджеста. Попробуйте позже.")

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
    await update.message.reply_text(
        f"Частота дайджеста установлена: {frequency}.", 
        reply_markup=ReplyKeyboardRemove()
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "Привет! 👋\n"
            "Этот бот собирает сообщения из чатов, формирует дайджесты и отправляет их по расписанию.\n\n"
            "Добавь меня в чат и выдай права администратора, чтобы я начал работать.\n"
        )

async def bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member_update = update.my_chat_member
    old_status = member_update.old_chat_member.status
    new_status = member_update.new_chat_member.status

    if old_status in ["left", "kicked"] and new_status in ["member", "administrator"]:
        chat_id = member_update.chat.id
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Бот добавлен в чат ✅\n\n"
                "Не забудь выдать права администратора чтобы я мог сохранять сообщения\n"
                "Теперь я буду собирать сообщения и формировать дайджесты.\n"
                "Не забудьте настроить расписание командой /schedule. По умолчанию оно отправляется раз в неделю.\n"
                "Командой /digest, ты можешь получить дайджест за последние 100 сообщений."
            )
        )