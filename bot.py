import os
import re
import json
import random
import sqlite3
import logging
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ----------------------------
# CONFIG
# ----------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in environment variables.")

TZ_DEFAULT = "Europe/Moscow"  # Москва
DATA_DIR = os.environ.get("DATA_DIR", "/var/data")  # Render Disk mount path recommended
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "newyouday.sqlite3")

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("newyouday")

# ----------------------------
# CONTENT (10 per category)
# ----------------------------
CATEGORY_ORDER = ["Тело", "Ум", "Восстановление", "Порядок", "Смысл", "Тренировка"]

TASKS_BY_CATEGORY: dict[str, list[str]] = {
    "Тело": [
        "💪 12 минут зарядки: 3 круга (приседания 12 / отжимания 8 / планка 30с).",
        "🚶 25 минут прогулки бодрым шагом (без телефона).",
        "🧘 8 минут растяжки: шея/спина/таз — мягко, без боли.",
        "🥤 Вода: 2 больших стакана до обеда.",
        "🫁 5 минут дыхания: вдох 4 — выдох 6.",
        "🧍 Осанка: 3 раза за день по 60 секунд «плечи назад, шея длинная».",
        "🍎 Один “чистый” перекус: фрукт/йогурт/горсть орехов.",
        "🧊 Контраст: 30–60 сек прохладной воды в конце душа (по желанию).",
        "🛌 Лечь спать на 20 минут раньше обычного.",
        "🧹 10 минут легкой активности дома: пройтись/размяться/потянуться.",
    ],
    "Ум": [
        "📚 20 минут чтения (любая книга, без перфекционизма).",
        "🧠 10 минут: выпиши 3 задачи дня и выбери одну главную.",
        "📝 7 минут: короткая заметка «что сегодня важно и почему».",
        "🎧 15 минут обучения: видео/подкаст по теме, которая двигает вперёд.",
        "🧩 10 минут: реши 1 небольшую задачку/головоломку/логика.",
        "🗂 12 минут: разобрать одну папку/заметки/закладки.",
        "📌 8 минут: привести в порядок календарь (завтра/неделя).",
        "🔍 10 минут: изучи один инструмент/фичу, которую давно откладывал.",
        "✍️ 10 минут: подготовь черновик одного важного сообщения/письма.",
        "🧭 6 минут: сформулируй «что я хочу получить к концу недели».",
    ],
    "Восстановление": [
        "😮‍💨 5 минут дыхания (вдох 4 — выдох 6), без напряжения.",
        "🧘 7 минут тишины (без музыки, без новостей).",
        "📵 1 час без соцсетей (поставь таймер).",
        "🌿 10 минут на балконе/у окна: свет + спокойный взгляд вдаль.",
        "🫖 Чай-пауза: 7 минут медленно, без параллельных дел.",
        "👣 5 минут босиком дома (если комфортно): почувствуй опору.",
        "🎵 1 трек “для восстановления” и просто послушай (не листай).",
        "🧠 3 минуты: расслабь челюсть/плечи/живот — проверь, где зажим.",
        "🛀 Тёплый душ 8 минут — как перезагрузка.",
        "🌙 За 30 минут до сна — приглуши свет и убери яркие экраны.",
    ],
    "Порядок": [
        "🧽 10 минут быстрой уборки одной зоны (стол/раковина/полка).",
        "📬 10 минут: почта/входящие — закрыть 5 мелких хвостов.",
        "🗑 5 минут: выбросить 10 ненужных вещей/бумаг.",
        "🧾 12 минут: привести в порядок рабочее место.",
        "🧺 10 минут: один цикл — собрать/разобрать вещи по местам.",
        "🧷 8 минут: подготовить одежду/сумку на завтра.",
        "📦 10 минут: разобрать одну коробку/пакет/ящик.",
        "🔌 6 минут: кабели/зарядки — упорядочить одну точку.",
        "🧴 8 минут: ванная/кухня — быстро протереть поверхности.",
        "🗒 10 минут: список покупок/дел — убрать хаос из головы на бумагу.",
    ],
    "Смысл": [
        "🤝 Напиши одному человеку короткое тёплое сообщение (без повода).",
        "🙏 Вспомни 3 вещи, за которые благодарен сегодня (можно мысленно).",
        "❤️ Сделай один маленький поступок для близких (конкретный).",
        "🌟 Поддержи себя: скажи вслух одну фразу «я молодец, потому что…».",
        "🧡 10 минут: сделать что-то “для души” (музыка/фото/идея/творчество).",
        "🎯 5 минут: сформулируй, что сегодня было главным — одним предложением.",
        "🧭 7 минут: подумай, что приближает тебя к твоей версии через год.",
        "🤍 3 минуты: дыхание + мысль «я на своей стороне».",
        "🌤 Маленькая радость: сделай себе приятную мелочь (осознанно).",
        "🫶 Дай добро: похвали кого-то конкретно за дело/качество.",
    ],
    "Тренировка": [
        "🏋️ Гиря: махи 10×10 (10 подходов по 10, отдых 45–60с).",
        "🏋️ Гиря: гоблет-присед 5×10 (контроль спины).",
        "🏋️ Гиря: жим одной рукой 5×6 на каждую (умеренный вес).",
        "🏋️ Гиря: тяга в наклоне 4×10 на каждую руку.",
        "🏋️ Гиря: турецкий подъём 3×1 на каждую (медленно, техника).",
        "🏋️ Гиря: «комплекс» 6 минут EMOM: 10 махов в начале каждой минуты.",
        "💥 Отжимания: 5 подходов до “честного” запаса 2 повтора.",
        "💥 Отжимания + планка: 4 круга (отжимания 10–15 / планка 30–40с).",
        "🦵 Ноги + корпус: 4 круга (присед 15 / выпады 10+10 / планка 30с).",
        "🧱 Спина/кор: 3 круга (лодочка 20с / супермен 10 / планка 30с).",
    ],
}

# ----------------------------
# DB LAYER
# ----------------------------
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                dob TEXT,
                tz TEXT NOT NULL DEFAULT 'Europe/Moscow',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_tasks (
                chat_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                category TEXT NOT NULL,
                task TEXT NOT NULL,
                PRIMARY KEY (chat_id, day, category)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS state (
                chat_id INTEGER PRIMARY KEY,
                awaiting_dob INTEGER NOT NULL DEFAULT 0
            )
            """
        )


def get_user(chat_id: int) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,)).fetchone()
        return dict(row) if row else None


def upsert_user(chat_id: int, dob: str | None = None, tz: str | None = None) -> None:
    now = datetime.utcnow().isoformat()
    existing = get_user(chat_id)
    if existing is None:
        with db() as conn:
            conn.execute(
                "INSERT INTO users(chat_id, dob, tz, created_at, updated_at) VALUES(?,?,?,?,?)",
                (chat_id, dob, tz or TZ_DEFAULT, now, now),
            )
    else:
        new_dob = dob if dob is not None else existing.get("dob")
        new_tz = tz if tz is not None else existing.get("tz") or TZ_DEFAULT
        with db() as conn:
            conn.execute(
                "UPDATE users SET dob=?, tz=?, updated_at=? WHERE chat_id=?",
                (new_dob, new_tz, now, chat_id),
            )


def set_awaiting_dob(chat_id: int, awaiting: bool) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO state(chat_id, awaiting_dob) VALUES(?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET awaiting_dob=excluded.awaiting_dob",
            (chat_id, 1 if awaiting else 0),
        )


def get_awaiting_dob(chat_id: int) -> bool:
    with db() as conn:
        row = conn.execute("SELECT awaiting_dob FROM state WHERE chat_id=?", (chat_id,)).fetchone()
        return bool(row["awaiting_dob"]) if row else False


def day_key(tz_name: str) -> str:
    tz = ZoneInfo(tz_name)
    return datetime.now(tz).date().isoformat()


def ensure_daily_tasks(chat_id: int, tz_name: str) -> dict[str, str]:
    """Return tasks for today; create if missing. Always contains ALL categories from CATEGORY_ORDER."""
    today = day_key(tz_name)

    with db() as conn:
        rows = conn.execute(
            "SELECT category, task FROM daily_tasks WHERE chat_id=? AND day=?",
            (chat_id, today),
        ).fetchall()

    existing = {r["category"]: r["task"] for r in rows}

    # Fill missing categories deterministically for today
    rng = random.Random(f"{chat_id}:{today}")
    tasks: dict[str, str] = {}
    for cat in CATEGORY_ORDER:
        if cat in existing:
            tasks[cat] = existing[cat]
        else:
            options = TASKS_BY_CATEGORY.get(cat, [])
            if not options:
                tasks[cat] = "—"
            else:
                tasks[cat] = rng.choice(options)

    # Persist missing
    with db() as conn:
        for cat, task in tasks.items():
            conn.execute(
                "INSERT OR IGNORE INTO daily_tasks(chat_id, day, category, task) VALUES(?,?,?,?)",
                (chat_id, today, cat, task),
            )

    return tasks


# ----------------------------
# FORMATTING
# ----------------------------
def days_lived(dob_str: str, tz_name: str) -> int:
    tz = ZoneInfo(tz_name)
    dob = datetime.strptime(dob_str, "%d.%m.%Y").date()
    today = datetime.now(tz).date()
    return (today - dob).days + 1


def format_plan(dob: str, tz_name: str, tasks: dict[str, str]) -> str:
    dl = days_lived(dob, tz_name)
    lines = [
        f"📌 <b>План дня</b>",
        f"Сегодня твой <b>{dl}-й</b> день жизни.",
        "",
        "Выбери темп: <b>один шаг за раз</b>. Я рядом как коуч.",
        "",
    ]
    for cat in CATEGORY_ORDER:
        lines.append(f"• <b>{cat}:</b> {tasks.get(cat, '—')}")
    lines.append("")
    lines.append("Если хочешь посмотреть снова — команда: <b>/today</b>")
    return "\n".join(lines)


# ----------------------------
# JOBS (09/12/16/19/22:30)
# ----------------------------
SCHEDULE_TIMES = {
    "morning": time(hour=9, minute=0),
    "noon": time(hour=12, minute=0),
    "afternoon": time(hour=16, minute=0),
    "evening": time(hour=19, minute=0),
    "late": time(hour=22, minute=30),
}


def remove_user_jobs(app: Application, chat_id: int) -> None:
    jq = app.job_queue
    if not jq:
        return
    for name in SCHEDULE_TIMES.keys():
        job_name = f"user:{chat_id}:{name}"
        for job in jq.get_jobs_by_name(job_name):
            job.schedule_removal()


def schedule_user(app: Application, chat_id: int, tz_name: str) -> None:
    jq = app.job_queue
    if not jq:
        raise RuntimeError("JobQueue is not available. Ensure python-telegram-bot[job-queue] is installed.")

    remove_user_jobs(app, chat_id)

    tz = ZoneInfo(tz_name)
    jq.run_daily(job_morning, time=SCHEDULE_TIMES["morning"], timezone=tz, name=f"user:{chat_id}:morning", data={"chat_id": chat_id})
    jq.run_daily(job_noon, time=SCHEDULE_TIMES["noon"], timezone=tz, name=f"user:{chat_id}:noon", data={"chat_id": chat_id})
    jq.run_daily(job_afternoon, time=SCHEDULE_TIMES["afternoon"], timezone=tz, name=f"user:{chat_id}:afternoon", data={"chat_id": chat_id})
    jq.run_daily(job_evening, time=SCHEDULE_TIMES["evening"], timezone=tz, name=f"user:{chat_id}:evening", data={"chat_id": chat_id})
    jq.run_daily(job_late, time=SCHEDULE_TIMES["late"], timezone=tz, name=f"user:{chat_id}:late", data={"chat_id": chat_id})


async def job_morning(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.data["chat_id"]
    user = get_user(chat_id)
    if not user or not user.get("dob"):
        return
    tz_name = user.get("tz") or TZ_DEFAULT
    tasks = ensure_daily_tasks(chat_id, tz_name)
    text = format_plan(user["dob"], tz_name, tasks)

    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Взял в работу", callback_data="ack:morning"),
                InlineKeyboardButton("📌 /today", callback_data="cmd:today"),
            ],
            [
                InlineKeyboardButton("⏳ Напомни в 12:00", callback_data="ack:later"),
            ],
        ]
    )
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def job_noon(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.data["chat_id"]
    user = get_user(chat_id)
    if not user or not user.get("dob"):
        return

    text = (
        "🕛 <b>Чек-ин</b>\n"
        "Как дела с планом дня?\n\n"
        "Выбери честно — это не оценка, это настройка курса."
    )
    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Сделал(а) шаг", callback_data="noon:done"),
            InlineKeyboardButton("🟡 Почти", callback_data="noon:almost"),
            InlineKeyboardButton("🔴 Не вышло", callback_data="noon:notyet"),
        ]]
    )
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def job_afternoon(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.data["chat_id"]
    user = get_user(chat_id)
    if not user or not user.get("dob"):
        return

    text = (
        "🕓 <b>Промежуточная точка</b>\n"
        "Выбери одну маленькую победу, которую сделаешь до 19:00.\n"
        "Даже 10 минут — уже движение."
    )
    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Сделаю 10 минут", callback_data="aft:10"),
            InlineKeyboardButton("✅ Сделаю 25 минут", callback_data="aft:25"),
            InlineKeyboardButton("🤝 Нужен мягкий режим", callback_data="aft:soft"),
        ]]
    )
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def job_evening(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.data["chat_id"]
    user = get_user(chat_id)
    if not user or not user.get("dob"):
        return

    text = (
        "🕖 <b>Вечер</b>\n"
        "День подходит к финалу. Хорошая работа.\n\n"
        "Что выбираешь на вечер?"
    )
    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("🏋️ Тренировка будет", callback_data="eve:workout"),
            InlineKeyboardButton("🚶 Прогулка/разминка", callback_data="eve:walk"),
            InlineKeyboardButton("🌿 Восстановление", callback_data="eve:rest"),
        ]]
    )
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def job_late(context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = context.job.data["chat_id"]
    user = get_user(chat_id)
    if not user or not user.get("dob"):
        return

    text = (
        "🌙 <b>Финиш дня</b>\n"
        "Мысленно отметь 3 хорошие вещи дня — и отпусти остальное.\n"
        "Завтра продолжим спокойно и ровно."
    )
    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Принял(а), выключаюсь", callback_data="late:ok"),
            InlineKeyboardButton("⏳ Ещё 30 минут и спать", callback_data="late:30"),
        ]]
    )
    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=kb)


# ----------------------------
# HANDLERS
# ----------------------------
DOB_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    upsert_user(chat_id)  # ensure exists

    user = get_user(chat_id)
    tz_name = (user.get("tz") if user else None) or TZ_DEFAULT

    # If DOB missing -> ask once
    if not user or not user.get("dob"):
        set_awaiting_dob(chat_id, True)
        await update.message.reply_text(
            "Привет! Я <b>NewYouDay</b> 👋\n\n"
            "Отправь дату рождения в формате <b>ДД.ММ.ГГГГ</b> (пример: 22.04.1983).",
            parse_mode=ParseMode.HTML,
        )
        return

    # already configured: no повтор вопросов
    set_awaiting_dob(chat_id, False)
    schedule_user(context.application, chat_id, tz_name)

    await update.message.reply_text(
        "Я на связи ✅\n"
        "Расписание: 09:00 / 12:00 / 16:00 / 19:00 / 22:30 (Москва).\n\n"
        "Команды:\n"
        "• /today — показать план дня\n"
        "• /settings — настройки",
    )


async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user or not user.get("dob"):
        await update.message.reply_text("Сначала /start и дата рождения 🙂")
        return

    tz_name = user.get("tz") or TZ_DEFAULT
    tasks = ensure_daily_tasks(chat_id, tz_name)
    text = format_plan(user["dob"], tz_name, tasks)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user:
        upsert_user(chat_id)
        user = get_user(chat_id)

    tz_name = user.get("tz") or TZ_DEFAULT
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"🕒 Таймзона: {tz_name}", callback_data="noop")],
            [InlineKeyboardButton("♻️ Пересоздать расписание", callback_data="settings:reschedule")],
            [InlineKeyboardButton("🗓 Сменить дату рождения", callback_data="settings:reset_dob")],
            [InlineKeyboardButton("❌ Закрыть", callback_data="settings:close")],
        ]
    )
    await update.message.reply_text("Настройки:", reply_markup=kb)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if get_awaiting_dob(chat_id):
        if not DOB_RE.match(text):
            await update.message.reply_text("Формат должен быть ДД.ММ.ГГГГ (пример: 22.04.1983). Попробуй ещё раз.")
            return
        try:
            datetime.strptime(text, "%d.%m.%Y")
        except ValueError:
            await update.message.reply_text("Похоже, такой даты не бывает 🙂 Попробуй ещё раз (ДД.ММ.ГГГГ).")
            return

        upsert_user(chat_id, dob=text, tz=TZ_DEFAULT)
        set_awaiting_dob(chat_id, False)

        # schedule + send today's plan immediately
        schedule_user(context.application, chat_id, TZ_DEFAULT)
        tasks = ensure_daily_tasks(chat_id, TZ_DEFAULT)
        plan = format_plan(text, TZ_DEFAULT, tasks)
        await update.message.reply_text("Запомнил ✅", parse_mode=ParseMode.HTML)
        await update.message.reply_text(plan, parse_mode=ParseMode.HTML)
        return

    # default: ignore or friendly response
    await update.message.reply_text("Я тебя понял ✅ Если нужен план дня — /today")


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q:
        return
    await q.answer()

    chat_id = q.message.chat.id
    data = q.data or ""

    # Do NOT delete/edit the morning plan message — keep it visible.
    if data == "cmd:today":
        user = get_user(chat_id)
        if user and user.get("dob"):
            tz_name = user.get("tz") or TZ_DEFAULT
            tasks = ensure_daily_tasks(chat_id, tz_name)
            await context.bot.send_message(chat_id=chat_id, text=format_plan(user["dob"], tz_name, tasks), parse_mode=ParseMode.HTML)
        return

    if data.startswith("ack:"):
        if data == "ack:morning":
            await context.bot.send_message(chat_id=chat_id, text="✅ Отлично. Держим курс. В 12:00 коротко чекну как дела.")
        elif data == "ack:later":
            await context.bot.send_message(chat_id=chat_id, text="⏳ Ок. План у тебя в сообщении выше (и всегда доступен через /today).")
        return

    if data.startswith("noon:"):
        if data == "noon:done":
            msg = "🔥 Круто. Закрепи результат: выбери ещё один маленький пункт и сделай его до 16:00."
        elif data == "noon:almost":
            msg = "🟡 Нормально. Упростим: сделай 10 минут самого важного — этого достаточно."
        else:
            msg = "🔴 Бывает. Давай без самокритики: выбери один самый лёгкий пункт и сделай его сегодня."
        await context.bot.send_message(chat_id=chat_id, text=msg)
        return

    if data.startswith("aft:"):
        if data == "aft:10":
            msg = "✅ Отличный выбор. 10 минут — это реальный прогресс. Начни прямо с таймера."
        elif data == "aft:25":
            msg = "💪 Супер. 25 минут — сильная ставка. Разбей на 2×12 минут, если так легче."
        else:
            msg = "🌿 Мягкий режим принят. Выбери один простой шаг — и сделай его спокойно."
        await context.bot.send_message(chat_id=chat_id, text=msg)
        return

    if data.startswith("eve:"):
        if data == "eve:workout":
            msg = "🏋️ Отлично. Короткая тренировка тоже считается. Начни с разминки 3 минуты."
        elif data == "eve:walk":
            msg = "🚶 Класс. Прогулка — это топ для головы и тела. 15–25 минут будет достаточно."
        else:
            msg = "🌿 Восстановление — это сила, а не слабость. Дай нервной системе выдохнуть."
        await context.bot.send_message(chat_id=chat_id, text=msg)
        return

    if data.startswith("late:"):
        if data == "late:ok":
            msg = "🌙 Принято. Спокойной ночи. Завтра продолжим ровно и уверенно."
        else:
            msg = "⏳ Ок. Поставь таймер на 30 минут — и после него выключайся без переговоров 🙂"
        await context.bot.send_message(chat_id=chat_id, text=msg)
        return

    if data.startswith("settings:"):
        if data == "settings:reschedule":
            user = get_user(chat_id)
            tz_name = (user.get("tz") if user else None) or TZ_DEFAULT
            schedule_user(context.application, chat_id, tz_name)
            await context.bot.send_message(chat_id=chat_id, text="♻️ Пересоздал расписание ✅")
        elif data == "settings:reset_dob":
            upsert_user(chat_id, dob=None)
            set_awaiting_dob(chat_id, True)
            await context.bot.send_message(chat_id=chat_id, text="Ок. Отправь дату рождения в формате ДД.ММ.ГГГГ.")
        else:
            await context.bot.send_message(chat_id=chat_id, text="Ок ✅")
        return


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception: %s", context.error)


# ----------------------------
# STARTUP
# ----------------------------
async def on_startup(app: Application) -> None:
    init_db()

    # Reschedule all users with DOB
    with db() as conn:
        rows = conn.execute("SELECT chat_id, tz, dob FROM users WHERE dob IS NOT NULL AND dob != ''").fetchall()

    for r in rows:
        chat_id = int(r["chat_id"])
        tz_name = r["tz"] or TZ_DEFAULT
        try:
            schedule_user(app, chat_id, tz_name)
            logger.info("Scheduled user %s (%s)", chat_id, tz_name)
        except Exception:
            logger.exception("Failed to schedule user %s", chat_id)


def main() -> None:
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(on_startup)
        .build()
    )

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("today", today_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    logger.info("Starting NewYouDay bot…")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
