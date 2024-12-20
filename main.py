# main.py
import db
import command
import logging
import os
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
import schedule
import time
import threading
import asyncio

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токены и ключи
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHATAI_API_KEY = os.getenv('CHATAI_API_KEY')
CHATAI_API_URL = "https://api.gen-api.ru/api/v1/networks/gpt-4o-mini"
MY_ID = int(os.getenv('MY_ID'))

def run_scheduler() -> None:
    """Цикл запуска задач планировщика."""
    while True:
        schedule.run_pending()
        time.sleep(1)

def schedule_digest() -> None:
    """Проверяет, нужно ли отправлять дайджесты и вызывает их генерацию."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, chat_id, next_run
            FROM schedules
            WHERE next_run <= datetime('now')
        """)
        tasks = cursor.fetchall()

    for user_id, chat_id, next_run in tasks:
        # Асинхронно вызываем генерацию дайджеста
        asyncio.create_task(command.generate_digest_for_chat(chat_id, user_id))
        db.update_next_run(user_id)

schedule.every(5).minutes.do(schedule_digest)

def main() -> None:
    db.init_db()
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Обработчик команд
    app.add_handler(CommandHandler("digest", command.generate_digest))
    app.add_handler(CommandHandler("schedule", command.schedule_menu))
    app.add_handler(MessageHandler(filters.Regex("^(Ежедневно|Раз в три дня|Еженедельно)$"), command.set_digest_frequency))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), db.collect_message))

    logging.info("Бот запущен.")
    app.run_polling()

if __name__ == "__main__":
    # Запускаем планировщик в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    # Запуск бота
    main()
