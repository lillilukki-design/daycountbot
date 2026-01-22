import os
import logging
from datetime import datetime, time

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# =========================
# НАСТРОЙКИ
# =========================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN not found in environment variables")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# =========================
# МОТИВАЦИЯ
# =========================

MOTIVATION_TEXTS = [
    "Каждый день — это шаг вперёд. Даже если он маленький.",
    "Ты уже прошёл больше, чем думаешь.",
    "Стабильность важнее скорости.",
    "Сегодня ты стал опытнее, чем вчера.",
    "Не сравнивай себя с другими — сравнивай с собой вчера.",
    "Твоя жизнь — длинный марафон, а не спринт.",
    "Дисциплина создаёт свободу.",
    "Ты всё ещё в игре. А это главное.",
]


def get_motivation() -> str:
    return MOTIVATION_TEXTS[datetime.now().day % len(MOTIVATION_TEXTS)]


# =========================
# КОМАНДЫ
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет 👋\n\n"
        "Я DayCountBot.\n"
        "Напиши дату рождения в формате:\n"
        "ДД.ММ.ГГГГ\n\n"
        "Например: 22.04.1983"
    )


async def handle_birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    try:
        birthdate = datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text(
            "Неверный формат.\nПример: 22.04.1983"
        )
        return

    context.user_data["birthdate"] = birthdate

    days = (datetime.now().date() - birthdate).days + 1

    await update.message.reply_text(
        f"Запомнил ✅\n\n"
        f"Сегодня твой {days}-й день жизни.\n\n"
        f"{get_motivation()}"
    )


# =========================
# ЕЖЕДНЕВНАЯ РАССЫЛКА
# =========================

async def daily_message(context: ContextTypes.DEFAULT_TYPE):
    for chat_id, data in context.application.user_data.items():
        birthdate = data.get("birthdate")
        if not birthdate:
            continue

        days = (datetime.now().date() - birthdate).days + 1

        text = (
            f"📅 Сегодня твой {days}-й день жизни.\n\n"
            f"{get_motivation()}"
        )

        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
        except Exception as e:
            logging.warning(f"Send error to {chat_id}: {e}")


# =========================
# ЗАПУСК
# =========================

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("reset", start))

    app.add_handler(
        CommandHandler(
            command=None,
            callback=handle_birthdate,
        )
    )

    # каждый день в 09:00 по серверному времени
    app.job_queue.run_daily(
        daily_message,
        time=time(hour=9, minute=0),
    )

    print("✅ DayCountBot started")
    app.run_polling()


if __name__ == "__main__":
    main()
