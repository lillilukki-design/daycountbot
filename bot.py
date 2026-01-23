import os
import json
import random
from datetime import datetime, date, time as dtime
from typing import Dict, Any, Optional, Tuple

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("BOT_TOKEN")
DATA_FILE = "users.json"

DAILY_SEND_TIME = dtime(hour=9, minute=0)

FREQ_DAILY = "daily"
FREQ_TENS = "tens"
FREQ_HUNDREDS = "hundreds"

FREQ_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["1) Каждый день"],
        ["2) Круглые десятки (…10, …20, …30)"],
        ["3) Круглые сотни (…100, …200, …300)"],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

# =========================
# MOTIVATION
# =========================
MOTIVATION = [
    "Сегодня хороший день, чтобы сделать один маленький шаг вперёд.",
    "Стабильность важнее скорости.",
    "Не обязательно быстро — важно регулярно.",
    "Сделай одно важное дело. Не десять, а одно.",
    "Дисциплина создаёт свободу.",
    "Собери маленькую победу — она запускает цепочку.",
    "Даже 10 минут могут изменить траекторию дня.",
    "Не сравнивай себя с другими — сравнивай с собой вчера.",
]

def pick_motivation(chat_id: int, days: int) -> str:
    rnd = random.Random(f"mot-{chat_id}-{days}")
    return rnd.choice(MOTIVATION)

# =========================
# TASK CATEGORIES
# =========================
# Порядок категорий: гарантирует разнообразие (не повтор подряд)
CATEGORY_ORDER = ["Тело", "Ум", "Восстановление", "Порядок", "Смысл"]

TASKS_BY_CATEGORY: Dict[str, list[str]] = {
    "Тело": [
        "💪 12 минут зарядки: 3 круга (приседания 12 / отжимания 8 / планка 30с).",
        "🚶 25 минут прогулки бодрым шагом (без телефона).",
        "🧎 8 минут растяжки: шея/спина/таз — мягко, без боли.",
        "🏃 10 минут лёгкой активности: лестница/разминка/прыжки на месте.",
        "🧊 Холодный душ: 30–60 секунд в конце (если по здоровью ок).",
    ],
    "Ум": [
        "📚 30 минут чтения (любая книга, без перфекционизма).",
        "🧠 10 минут: выпиши 5 задач дня и выбери одну главную.",
        "✍️ 7 минут: дневник — что сегодня важно и почему.",
        "🎧 15 минут обучения: подкаст/видео вместо ленты.",
        "📝 10 минут: разбор одной заметки/идеи — доведи до ясного плана.",
    ],
    "Восстановление": [
        "🧘 5 минут: дыхание (вдох 4 — выдох 6).",
        "😴 Сегодня цель: лечь на 30 минут раньше обычного.",
        "📵 1 час без соцсетей (поставь таймер).",
        "🌿 10 минут тишины: без музыки, без новостей, просто пауза.",
        "☕ 15 минут “медленно”: чай/кофе без телефона и суеты.",
    ],
    "Порядок": [
        "🧹 10 минут быстрой уборки: одна зона (стол/полка/раковина).",
        "🧺 10 минут: разбор вещей — выбросить/отдать 3 предмета.",
        "📥 10 минут: почта/входящие — закрыть 5 мелких хвостов.",
        "🧽 12 минут: привести в порядок рабочее место.",
        "📦 10 минут: мини-организация — один ящик/папка/полка.",
    ],
    "Смысл": [
        "🤝 Напиши одному человеку короткое тёплое сообщение (без повода).",
        "🎯 5 минут: сформулируй одну цель на неделю в одном предложении.",
        "🙏 3 минуты: вспомни 3 вещи, за которые благодарен сегодня.",
        "🧭 7 минут: ответь себе — что я делаю сегодня ради будущего себя?",
        "❤️ Сделай один маленький поступок для близких (конкретный).",
    ],
}

def category_and_task_for_today() -> Tuple[str, str]:
    """Единые категория+задание на текущую дату (одинаково для всех пользователей)."""
    day_index = date.today().toordinal()
    category = CATEGORY_ORDER[day_index % len(CATEGORY_ORDER)]
    tasks = TASKS_BY_CATEGORY[category]
    task = tasks[day_index % len(tasks)]
    return category, task

# =========================
# STORAGE
# =========================
def load_users() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_users(users: Dict[str, Any]) -> None:
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def get_user(users: Dict[str, Any], chat_id: int) -> Optional[Dict[str, Any]]:
    return users.get(str(chat_id))

def set_user(users: Dict[str, Any], chat_id: int, payload: Dict[str, Any]) -> None:
    users[str(chat_id)] = payload
    save_users(users)

# =========================
# DOMAIN
# =========================
def parse_birthdate(text: str) -> Optional[date]:
    try:
        return datetime.strptime(text.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None

def days_lived(bday: date) -> int:
    return (date.today() - bday).days

def should_notify(freq: str, days: int) -> bool:
    if freq == FREQ_DAILY:
        return True
    if freq == FREQ_TENS:
        return days % 10 == 0
    if freq == FREQ_HUNDREDS:
        return days % 100 == 0
    return True

def format_days_message(days: int) -> str:
    return f"Сегодня твой {days}-й день жизни."

def human_freq(freq: str) -> str:
    if freq == FREQ_DAILY:
        return "каждый день"
    if freq == FREQ_TENS:
        return "по круглым десяткам (…10, …20, …30)"
    if freq == FREQ_HUNDREDS:
        return "по круглым сотням (…100, …200, …300)"
    return "каждый день"

# =========================
# HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Это DayCountBot.\n"
        "Отправь дату рождения в формате ДД.ММ.ГГГГ (пример: 22.04.1983)."
    )

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users = load_users()
    chat_id = update.effective_chat.id
    u = get_user(users, chat_id)
    if not u:
        await update.message.reply_text("Пока нет настроек. Отправь дату рождения: ДД.ММ.ГГГГ")
        return

    freq = u.get("freq", FREQ_DAILY)
    tasks_enabled = bool(u.get("tasks_enabled", False))
    await update.message.reply_text(
        "Текущие настройки:\n"
        f"• Частота: {human_freq(freq)}\n"
        f"• Задание дня: {'включено' if tasks_enabled else 'выключено'}\n\n"
        "Команды:\n"
        "/tasks_on — включить задания\n"
        "/tasks_off — выключить задания"
    )

async def tasks_on(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users = load_users()
    chat_id = update.effective_chat.id
    u = get_user(users, chat_id)
    if not u or "birthdate" not in u:
        await update.message.reply_text("Сначала отправь дату рождения: ДД.ММ.ГГГГ")
        return

    u["tasks_enabled"] = True
    set_user(users, chat_id, u)
    await update.message.reply_text("Ок. Задание дня включено ✅")

async def tasks_off(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users = load_users()
    chat_id = update.effective_chat.id
    u = get_user(users, chat_id)
    if not u or "birthdate" not in u:
        await update.message.reply_text("Сначала отправь дату рождения: ДД.ММ.ГГГГ")
        return

    u["tasks_enabled"] = False
    set_user(users, chat_id, u)
    await update.message.reply_text("Ок. Задание дня выключено ✅")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users = load_users()
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    # 1) выбор частоты
    if text.startswith("1)") or text.startswith("2)") or text.startswith("3)"):
        u = get_user(users, chat_id)
        if not u or "birthdate" not in u:
            await update.message.reply_text("Сначала отправь дату рождения в формате ДД.ММ.ГГГГ.")
            return

        if text.startswith("1)"):
            freq = FREQ_DAILY
        elif text.startswith("2)"):
            freq = FREQ_TENS
        else:
            freq = FREQ_HUNDREDS

        u["freq"] = freq

        # Задания включаем по умолчанию только для daily
        if freq == FREQ_DAILY and "tasks_enabled" not in u:
            u["tasks_enabled"] = True
        if freq != FREQ_DAILY:
            u["tasks_enabled"] = False

        set_user(users, chat_id, u)
        await update.message.reply_text(f"Запомнил! Буду напоминать: {human_freq(freq)}.")
        return

    # 2) дата рождения
    bday = parse_birthdate(text)
    if not bday:
        await update.message.reply_text("Неверный формат.\nПример: 22.04.1983")
        return

    u = {
        "birthdate": bday.strftime("%Y-%m-%d"),
        "freq": FREQ_DAILY,
        "tasks_enabled": True,
    }
    set_user(users, chat_id, u)

    days = days_lived(bday)
    msg = format_days_message(days)
    mot = pick_motivation(chat_id, days)

    cat, task = category_and_task_for_today()

    await update.message.reply_text(
        f"Запомнил! {msg}\n\n{mot}\n\n"
        f"Задание дня — {cat}:\n{task}"
    )

    await update.message.reply_text(
        "Как часто присылать напоминания?",
        reply_markup=FREQ_KEYBOARD
    )

# =========================
# DAILY JOB
# =========================
async def daily_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    users = load_users()
    cat, task = category_and_task_for_today()

    for chat_id_str, u in users.items():
        try:
            chat_id = int(chat_id_str)
            bday = datetime.strptime(u["birthdate"], "%Y-%m-%d").date()
            freq = u.get("freq", FREQ_DAILY)
            tasks_enabled = bool(u.get("tasks_enabled", False))

            days = days_lived(bday)
            if not should_notify(freq, days):
                continue

            msg = format_days_message(days)
            mot = pick_motivation(chat_id, days)

            text = f"{msg}\n\n{mot}"

            if freq == FREQ_DAILY and tasks_enabled:
                text += f"\n\nЗадание дня — {cat}:\n{task}"

            await context.bot.send_message(chat_id=chat_id, text=text)

        except Exception:
            continue

# =========================
# MAIN
# =========================
def main() -> None:
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is not set in environment variables.")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CommandHandler("tasks_on", tasks_on))
    app.add_handler(CommandHandler("tasks_off", tasks_off))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.job_queue.run_daily(daily_job, time=DAILY_SEND_TIME)

    app.run_polling()

if __name__ == "__main__":
    main()
