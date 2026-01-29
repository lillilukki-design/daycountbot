import os
import json
import random
import logging
from datetime import datetime, date, time, timedelta

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("newyouday_bot")

BOT_NAME = "@NewYouDay_bot"

# ----- Storage (Render Disk) -----
DATA_DIR = os.environ.get("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)
USERS_PATH = os.path.join(DATA_DIR, "users.json")

# ----- Content -----
CATEGORY_ORDER = ["Тело", "Ум", "Восстановление", "Порядок", "Смысл"]

TASKS_BY_CATEGORY: dict[str, list[str]] = {
    "Тело": [
        "💪 12 минут зарядки: 3 круга (приседания 12 / отжимания 8 / планка 30с).",
        "🚶 25 минут прогулки бодрым шагом (без телефона).",
        "🧘 8 минут мягкой растяжки: шея/спина/таз (без боли).",
        "🏃 10 минут лёгкого кардио: быстрый шаг/лестница/скакалка.",
        "🚿 Контрастный душ 2–3 минуты (если ок по здоровью).",
        "🥗 Один приём пищи сегодня — без сахара/перекуса «на автомате».",
        "💧 +2 стакана воды до обеда.",
        "🛌 Лечь сегодня на 30 минут раньше.",
        "🏋️ 3 подхода: приседания 15 / отжимания 10 / пресс 15.",
        "🚴 20 минут любая активность: вело/ходьба/домашняя тренировка.",
    ],
    "Ум": [
        "📚 30 минут чтения (любая книга, без перфекционизма).",
        "🧠 10 минут: выпиши 5 задач дня и выбери одну главную.",
        "📝 7 минут дневник: что сегодня важно и почему.",
        "🎧 20 минут обучающего контента (1 тема) + 3 пункта конспекта.",
        "🔍 10 минут: разберись в одной «висящей» мелочи, которая бесит.",
        "🧩 10 минут: одна логическая задачка/судоку/шахматная тактика.",
        "📌 15 минут: набросай план на завтра (3 пункта).",
        "💡 10 минут: придумай 5 идей улучшения любого процесса вокруг тебя.",
        "🗣 5 минут: проговори вслух цель недели одним предложением.",
        "🧾 10 минут: приведи в порядок заметки/закладки (удали лишнее).",
    ],
    "Восстановление": [
        "🌬 5 минут дыхание (вдох 4 — выдох 6).",
        "⏳ 1 час без соцсетей (поставь таймер).",
        "🍃 10 минут тишины: без музыки, без новостей, просто пауза.",
        "☀️ 10 минут дневного света/у окна (если есть возможность).",
        "🫖 15 минут: чай/вода медленно, без экрана.",
        "🧠 5 минут: заметить 3 чувства сейчас и назвать их словами.",
        "🧴 10 минут: уход за собой (лицо/руки) без спешки.",
        "🎵 1 трек: послушай полностью, не переключая и не листая ленту.",
        "🧘 7 минут медитации/скан тела.",
        "🛁 15 минут: тёплый душ как «перезагрузка» без телефона.",
    ],
    "Порядок": [
        "🧹 10 минут быстрой уборки: одна зона (стол/полка/раковина).",
        "📩 10 минут: почта/входящие — закрыть 5 мелких хвостов.",
        "🧽 12 минут: привести в порядок рабочее место.",
        "🗑 10 минут: выбросить/убрать 10 вещей (мусор/лишнее).",
        "🧺 15 минут: разобрать одну стопку/ящик/пакет.",
        "📦 10 минут: подготовить вещи на завтра (одежда/сумка/документы).",
        "🧾 10 минут: закрыть одну «бумажную» мелочь (оплата/квитанция/скан).",
        "🧼 10 минут: кухня — раковина/поверхность/плита (минимум).",
        "🧹 10 минут: пол — быстрый проход в одной комнате.",
        "🔌 8 минут: провода/зарядки/тумба — убрать визуальный шум.",
    ],
    "Смысл": [
        "🤝 Напиши одному человеку короткое тёплое сообщение (без повода).",
        "🙏 3 минуты: вспомни 3 вещи, за которые благодарен сегодня.",
        "❤️ Сделай один маленький поступок для близких (конкретный).",
        "🎯 5 минут: вспомни «зачем» ты делаешь главное дело сейчас.",
        "🧡 10 минут: помоги кому-то — совет/контакт/мини-дело.",
        "📞 Позвони одному человеку (или голосовое 30–60 сек).",
        "📝 5 минут: запиши один принцип, по которому хочешь жить.",
        "🌱 7 минут: сделай добро анонимно (незаметно, но реально).",
        "🧭 5 минут: выбери одну вещь, от которой сегодня откажешься ради цели.",
        "✨ 3 минуты: представь лучший итог дня и сделай 1 шаг к нему.",
    ],
}

FREQ_KEYBOARD = ReplyKeyboardMarkup(
    [["1) Каждый день"], ["2) Круглые десятки (...10, ...20, ...30)"], ["3) Круглые сотни (...100, ...200, ...300)"]],
    resize_keyboard=True,
    one_time_keyboard=True,
)

# ----- Helpers -----
def load_users() -> dict:
    if not os.path.exists(USERS_PATH):
        return {}
    try:
        with open(USERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to load users.json, starting empty")
        return {}

def save_users(users: dict) -> None:
    tmp_path = USERS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, USERS_PATH)

def get_user(users: dict, user_id: int) -> dict:
    return users.get(str(user_id), {})

def set_user(users: dict, user_id: int, data: dict) -> None:
    users[str(user_id)] = data
    save_users(users)

def parse_birthdate(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None

def days_lived(bd: date, today: date) -> int:
    return (today - bd).days + 1

def should_send(freq: str, day_num: int) -> bool:
    if freq == "daily":
        return True
    if freq == "tens":
        return day_num % 10 == 0
    if freq == "hundreds":
        return day_num % 100 == 0
    return True

def pick_task_for_day(user_id: int, category: str, day_num: int) -> str:
    tasks = TASKS_BY_CATEGORY[category]
    # детерминированно, чтобы при рестарте в этот же день было то же самое
    seed = (user_id * 1000003) ^ (hash(category) & 0xFFFFFFFF) ^ (day_num * 97)
    rng = random.Random(seed)
    return rng.choice(tasks)

def build_daily_message(user_id: int, bd: date, today: date) -> str:
    n = days_lived(bd, today)
    lines = [
        f"Сегодня твой *{n}*-й день жизни.",
        "",
        "Сделай одно важное дело. Не десять — одно.",
        "",
        "*Задания дня:*",
    ]
    for cat in CATEGORY_ORDER:
        task = pick_task_for_day(user_id, cat, n)
        lines.append(f"— *{cat}:* {task}")
    return "\n".join(lines)

# ----- Bot logic -----
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users = load_users()
    uid = update.effective_user.id
    u = get_user(users, uid)

    if not u.get("birthdate"):
        await update.message.reply_text(
            f"Привет! Это {BOT_NAME}.\n"
            "Отправь дату рождения в формате ДД.ММ.ГГГГ (пример: 22.04.1983).",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # если есть дата, но нет частоты — спрашиваем один раз
    if not u.get("freq"):
        await update.message.reply_text(
            "Как часто присылать напоминания?",
            reply_markup=FREQ_KEYBOARD,
        )
        return

    await update.message.reply_text(
        "Я тебя помню ✅\n"
        "Хочешь — напиши /status чтобы посмотреть настройки, или /now чтобы получить сообщение прямо сейчас.",
        reply_markup=ReplyKeyboardRemove(),
    )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users = load_users()
    uid = update.effective_user.id
    u = get_user(users, uid)
    if not u.get("birthdate"):
        await update.message.reply_text("Пока нет даты рождения. Отправь ДД.ММ.ГГГГ.")
        return
    freq = u.get("freq", "daily")
    t = u.get("send_time", "09:00")
    await update.message.reply_text(
        f"Настройки:\n"
        f"— Дата рождения: {u['birthdate']}\n"
        f"— Частота: {freq}\n"
        f"— Время: {t}\n\n"
        f"Команды: /now (прислать сейчас), /settime HH:MM, /setfreq, /reset"
    )

async def now_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users = load_users()
    uid = update.effective_user.id
    u = get_user(users, uid)
    if not u.get("birthdate"):
        await update.message.reply_text("Сначала отправь дату рождения (ДД.ММ.ГГГГ).")
        return
    bd = datetime.strptime(u["birthdate"], "%d.%m.%Y").date()
    msg = build_daily_message(uid, bd, date.today())
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

async def setfreq_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Как часто присылать напоминания?", reply_markup=FREQ_KEYBOARD)

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users = load_users()
    uid = update.effective_user.id
    if str(uid) in users:
        users.pop(str(uid), None)
        save_users(users)
    # удалим job если был
    remove_user_jobs(context, uid)
    await update.message.reply_text("Ок, сбросил настройки. Отправь дату рождения (ДД.ММ.ГГГГ).", reply_markup=ReplyKeyboardRemove())

def remove_user_jobs(context: ContextTypes.DEFAULT_TYPE, uid: int) -> None:
    jobs = context.job_queue.get_jobs_by_name(str(uid))
    for j in jobs:
        j.schedule_removal()

def schedule_user(context: ContextTypes.DEFAULT_TYPE, uid: int, u: dict) -> None:
    # чтобы не было дублей
    remove_user_jobs(context, uid)

    send_time_str = u.get("send_time", "09:00")
    hh, mm = map(int, send_time_str.split(":"))
    t = time(hour=hh, minute=mm)

    context.job_queue.run_daily(
        callback=daily_job,
        time=t,
        name=str(uid),
        data={"user_id": uid},
    )

async def daily_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    users = load_users()
    uid = context.job.data["user_id"]
    u = get_user(users, uid)
    if not u.get("birthdate") or not u.get("freq"):
        return

    bd = datetime.strptime(u["birthdate"], "%d.%m.%Y").date()
    today = date.today()
    n = days_lived(bd, today)

    if not should_send(u["freq"], n):
        return

    msg = build_daily_message(uid, bd, today)
    try:
        await context.bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
    except Exception:
        logger.exception("Failed to send daily message to user %s", uid)

async def settime_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Ок. Пришли время в формате HH:MM (например 09:00).", reply_markup=ReplyKeyboardRemove())

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    users = load_users()
    uid = update.effective_user.id
    text = (update.message.text or "").strip()

    u = get_user(users, uid)

    # 1) ввод даты рождения
    if not u.get("birthdate"):
        bd = parse_birthdate(text)
        if not bd:
            await update.message.reply_text("Не понял дату. Формат: ДД.ММ.ГГГГ (пример: 22.04.1983).")
            return
        u["birthdate"] = bd.strftime("%d.%m.%Y")
        set_user(users, uid, u)

        await update.message.reply_text(
            "Запомнил! Теперь выбери, как часто присылать напоминания:",
            reply_markup=FREQ_KEYBOARD,
        )
        return

    # 2) выбор частоты (только если её ещё нет ИЛИ пользователь вызвал /setfreq)
    if text.startswith("1)") or text.startswith("2)") or text.startswith("3)"):
        if text.startswith("1)"):
            u["freq"] = "daily"
        elif text.startswith("2)"):
            u["freq"] = "tens"
        else:
            u["freq"] = "hundreds"

        if not u.get("send_time"):
            u["send_time"] = "09:00"

        set_user(users, uid, u)
        schedule_user(context, uid, u)

        await update.message.reply_text(
            f"Запомнил! Буду напоминать: {text}\n"
            f"Время: {u['send_time']}.\n"
            "Хочешь проверить прямо сейчас — /now",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # 3) установка времени
    if ":" in text and len(text) <= 5:
        try:
            hh, mm = map(int, text.split(":"))
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError
            u["send_time"] = f"{hh:02d}:{mm:02d}"
            set_user(users, uid, u)
            if u.get("freq"):
                schedule_user(context, uid, u)
            await update.message.reply_text(f"Ок, время напоминания: {u['send_time']}.", reply_markup=ReplyKeyboardRemove())
            return
        except ValueError:
            pass

    # fallback
    await update.message.reply_text(
        "Я тебя понял, но команда не распознана.\n"
        "Используй /status, /now, /settime, /setfreq или /reset.",
        reply_markup=ReplyKeyboardRemove(),
    )

async def on_startup(app) -> None:
    # при старте поднимем расписания для всех пользователей
    users = load_users()
    for uid_str, u in users.items():
        try:
            uid = int(uid_str)
            if u.get("birthdate") and u.get("freq"):
                schedule_user(app.bot_data["context"], uid, u)  # запасной вариант
        except Exception:
            # не критично — просто не создадим job
            logger.exception("Failed to schedule user on startup: %s", uid_str)

def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN env var is required")

    app = ApplicationBuilder().token(token).build()

    # hack: дадим доступ к context в on_startup (Render/PTB нюанс)
    # безопасно: только для рескейджулинга
    app.bot_data["context"] = type("Obj", (), {"job_queue": app.job_queue, "bot": app.bot, "bot_data": app.bot_data})()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("now", now_cmd))
    app.add_handler(CommandHandler("setfreq", setfreq_cmd))
    app.add_handler(CommandHandler("settime", settime_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    # ВАЖНО: PTB v20 сам держит event loop, не нужно asyncio.run()
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
