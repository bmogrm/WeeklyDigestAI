# main.py
import db
import command
import logging
import os
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ChatMemberHandler
import schedule
import time
import threading
import asyncio
from queue import Queue

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токены и ключи
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHATAI_API_KEY = os.getenv('CHATAI_API_KEY')
CHATAI_API_URL = "https://api.gen-api.ru/api/v1/networks/gpt-4o-mini"

app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
task_queue = Queue()

def schedule_digest():
    """Проверяет, нужно ли отправлять дайджесты и добавляет задачи в очередь."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, chat_id, next_run
            FROM schedules
            WHERE next_run <= datetime('now')
        """)
        tasks = cursor.fetchall()

    for user_id, chat_id, next_run in tasks:
        # Добавляем задачу в очередь
        task_queue.put((command.generate_digest_for_chat, chat_id))
        db.update_next_run(user_id)

def run_scheduler():
    """Цикл запуска задач планировщика."""
    schedule.every(1).minutes.do(schedule_digest)
    while True:
        schedule.run_pending()
        time.sleep(1)

async def process_tasks():
    """Обрабатывает задачи из очереди в основном event loop."""
    while True:
        while not task_queue.empty():
            func, *args = task_queue.get()
            await func(*args)  # Выполняем асинхронную функцию
        await asyncio.sleep(1)  # Небольшая задержка, чтобы не нагружать CPU

async def post_init(application):
    """Функция, вызываемая после инициализации приложения."""
    # Запуск обработчика задач в основном event loop
    application.create_task(process_tasks())

def main() -> None:
    db.init_db()

    # Обработчики
    app.add_handler(CommandHandler("digest", command.generate_digest))
    app.add_handler(CommandHandler("schedule", command.schedule_menu))
    app.add_handler(MessageHandler(filters.Regex("^(Ежедневно|Раз в три дня|Еженедельно)$"), command.set_digest_frequency))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), db.collect_message))
    app.add_handler(CommandHandler("start", command.start))
    app.add_handler(ChatMemberHandler(command.bot_added, ChatMemberHandler.MY_CHAT_MEMBER))

    # Указываем post_init для запуска process_tasks
    app.post_init = post_init

    # Запуск планировщика в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    logging.info("Бот запущен.")
    app.run_polling()

if __name__ == "__main__":
    # Запуск бота
    main()
