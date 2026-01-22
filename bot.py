import os
import json
from datetime import datetime, date
import pytz

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from apscheduler.schedulers.asyncio import AsyncIOScheduler


# ==============================
# НАСТРОЙКИ
# ==============================

TOKEN = os.getenv("BOT_TOKEN")  # токен будет в Render Environment
DATA_FILE = "users.json"
TIMEZONE = pytz.timezone("Europe/Moscow")


# ==============================
# ХРАНЕНИЕ ДАННЫХ
# ==============================

def load_users():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_users(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


users = load_users()


# ==============================
# ЛОГИКА
# ==============================

def days_lived(birthdate: date) -> int:
    return (date.today() - birthdate).days


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 👋\n"
        "Я DayCountBot.\n\n"
        "Отправь дату рождения в формате:\n"
        "ДД.ММ.ГГГГ\n\n"
        "Пример: 22.04.1983"
    )


async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    try:
        birth = datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text(
            "Неверный формат.\n"
            "Пример: 22.04.1983"
        )
        return

    chat_id = str(update.effective_chat.id)

    users[chat_id] = {
        "birthdate": birth.isoformat()
    }

    save_users(users)

    lived = days_lived(birth)

    await update.message.reply_text(
        f"Запомнил ✅\n\n"
        f"Сегодня твой **{lived}-й день жизни**."
    )


# ==============================
# ЕЖЕДНЕВНАЯ РАССЫЛКА
# ==============================

async def daily_message(app):
    for chat_id, data in users.items():
        birth = date.fromisoformat(data["birthdate"])
        lived = days_lived(birth)

        text = (
            f"🌅 Доброе утро!\n\n"
            f"Сегодня твой **{lived}-й день жизни**.\n\n"
            f"Каждый день — это маленькая жизнь."
        )

        try:
            await app.bot.send_message(chat_id=int(chat_id), text=text)
        except Exception as e:
            print("Ошибка отправки:", e)


# ==============================
# ЗАПУСК
# ==============================

async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_date))

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        daily_message,
        trigger="cron",
        hour=9,
        minute=0,
        args=[app],
    )
    scheduler.start()

    print("✅ DayCountBot запущен")

    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
