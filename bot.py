# bot.py
# Telegram ассистент: @NewYouDay_bot
# Режим: 09:00 / 12:00 / 16:00 / 19:00 / 22:30 (GMT+3, Europe/Moscow)
#
# Важно для Render:
# 1) В Environment переменная BOT_TOKEN = <токен>
# 2) В requirements.txt нужен python-telegram-bot[job-queue]
# 3) (опционально) подключи Render Disk и смонтируй в /var/data (или оставь без диска — будет файл рядом)
#
# pip package: python-telegram-bot[job-queue]>=20

import json
import logging
import os
import random
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional, Tuple

from zoneinfo import ZoneInfo

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# -----------------------------
# CONFIG
# -----------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in environment variables.")

TZ_NAME_DEFAULT = os.getenv("TZ_NAME", "Europe/Moscow")
TZ_DEFAULT = ZoneInfo(TZ_NAME_DEFAULT)

# Where to store persistent data.
# If you attach Render Disk, mount it to /var/data and it will persist.
DATA_DIR = os.getenv("DATA_DIR", "/var/data")
if not os.path.isdir(DATA_DIR):
    DATA_DIR = os.getenv("DATA_DIR_FALLBACK", ".")

DATA_FILE = os.path.join(DATA_DIR, "newyouday_data.json")

# Daily schedule (Moscow time)
SCHEDULE_TIMES = {
    "morning": "09:00",
    "noon": "12:00",
    "afternoon": "16:00",
    "evening": "19:00",
    "late": "22:30",
}

CATEGORY_ORDER = ["Тело", "Ум", "Восстановление", "Порядок", "Смысл"]

# Expand to 10 tasks each category
TASKS_BY_CATEGORY: Dict[str, List[str]] = {
    "Тело": [
        "💪 12 минут зарядки: 3 круга (приседания 12 / отжимания 8 / планка 30с).",
        "🚶 25 минут прогулки бодрым шагом (без телефона).",
        "🧘 8 минут растяжки: шея/спина/таз — мягко, без боли.",
        "🏃 10 минут лёгкого кардио: шаг на месте/скакалка (по самочувствию).",
        "🥤 Вода: 2 стакана до обеда (просто отметь факт).",
        "🧍 5 минут осанки: подбородок назад, плечи вниз, дыхание ровное.",
        "🚶‍♂️ 15 минут «быстрой ходьбы» (можно по лестнице/коридору).",
        "🧘‍♂️ 6 минут мобилизации: плечи + грудной отдел + тазобедренные.",
        "🧎 7 минут «кор»: планка 3х20с + боковая 2х15с.",
        "🧘 5 минут дыхания + лёгкая растяжка перед сном.",
    ],
    "Ум": [
        "📚 30 минут чтения (любая книга, без перфекционизма).",
        "🧩 10 минут: выпиши 5 задач дня и выбери одну главную.",
        "✍️ 7 минут дневник — что сегодня важно и почему.",
        "🧠 15 минут «глубокой работы»: один файл/одна задача/без вкладок.",
        "🗂️ 10 минут разобрать заметки/входящие (только быстрые решения).",
        "🎧 12 минут обучающего видео/подкаста — и 1 вывод в заметку.",
        "🧾 8 минут: составь мини-план на завтра (3 пункта).",
        "🔎 10 минут: найди одну вещь, которая реально мешает, и убери её.",
        "🧠 5 минут: сформулируй цель дня одной фразой.",
        "📌 12 минут: закрой один «хвост», который давно висит.",
    ],
    "Восстановление": [
        "🧘‍♀️ 5 минут дыхание (вдох 4 — выдох 6).",
        "⏳ 1 час без соцсетей (поставь таймер).",
        "🌿 10 минут тишины: без музыки, без новостей, просто пауза.",
        "😴 Лечь на 20 минут раньше обычного (микро-обещание себе).",
        "🍵 10 минут чай/вода медленно, без экрана.",
        "🫧 7 минут горячий душ/контраст — как перезапуск.",
        "🌙 8 минут: выключи яркий свет и сделай «режим вечера».",
        "🧠 5 минут: выпиши 3 тревоги → рядом 1 действие/или «отпускаю».",
        "🧍 6 минут: расслабь челюсть/плечи + медленное дыхание.",
        "📵 30 минут до сна без телефона (или хотя бы 15).",
    ],
    "Порядок": [
        "🧹 10 минут быстрой уборки: одна зона (стол/полка/раковина).",
        "📩 10 минут: почта/входящие — закрыть 5 мелких хвостов.",
        "🧠 12 минут: привести в порядок рабочее место.",
        "🧺 8 минут: сложить вещи/стирка/корзина — до видимого результата.",
        "🗑️ 6 минут: выбросить мусор/разобрать одну «кучу».",
        "🧾 10 минут: платежи/квитанции/папки — только самое нужное.",
        "📦 10 минут: разбор одной коробки/ящика (без фанатизма).",
        "🧽 7 минут: кухня — поверхность + раковина.",
        "🧴 6 минут: ванная — быстро протереть/порядок.",
        "🧹 5 минут: «микро-порядок» — 10 предметов на место.",
    ],
    "Смысл": [
        "💬 Напиши одному человеку короткое тёплое сообщение (без повода).",
        "🙏 3 минуты: вспомни 3 вещи, за которые благодарен сегодня.",
        "❤️ Сделай один маленький поступок для близких (конкретный).",
        "🎯 Спроси себя: «что сегодня было важнее всего?» — и ответь одной фразой.",
        "🤝 Помоги кому-то на 2 минуты: совет/звонок/ссылка/поддержка.",
        "🌟 Сделай одну вещь «как человек, которым хочешь быть». Маленькую.",
        "🧩 5 минут: сформулируй свой принцип дня (одно предложение).",
        "🕯️ 7 минут: без экрана — посиди и подумай о главном.",
        "📞 5 минут: позвони/напиши человеку, которого давно не слышал.",
        "🫶 3 минуты: похвали себя за одно действие (даже маленькое).",
    ],
}

# Message tone variants
MORNING_OPENERS = [
    "Доброе утро. Давай соберём день спокойно и по делу.",
    "Утро. Никакой суеты — просто маленькие шаги.",
    "Привет. Сегодня сделаем чуть лучше, чем вчера.",
    "Доброе. План на день — коротко, но мощно.",
    "Утро. Выбираем фокус и идём.",
]

CHECKIN_12 = [
    "Как идёт день? Что получилось из утреннего списка?",
    "Чек-ин. Удалось сделать хоть один пункт?",
    "Как дела по плану? Есть маленькая победа?",
    "Середина дня. Давай сверимся без давления.",
]

CHECKIN_16 = [
    "16:00 — короткая сверка. Продвигаемся?",
    "Вторая половина дня. Что уже сделано?",
    "Какой статус? Если тяжело — упростим.",
    "Давай быстро: победа / процесс / стоп — что у тебя сейчас?",
]

EVENING_CLOSE = [
    "Рабочий день закончен. Как ты?",
    "Вечер. Давай аккуратно закроем день.",
    "Финиш дня. Оценим и отпустим.",
    "Вечерний чек. Что было самым важным сегодня?",
]

LATE_REFLECTION = [
    "Перед сном один вопрос на 15 секунд: что сегодня было самым важным?",
    "Микро-рефлексия: какой вывод дня одним предложением?",
    "Тихий вопрос: за что ты сегодня можешь себя уважать?",
]

# -----------------------------
# PERSISTENCE
# -----------------------------
def _safe_load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {"users": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"users": {}}


def _safe_save_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


class Store:
    def __init__(self, path: str):
        self.path = path
        self.data = _safe_load_json(path)

    def save(self) -> None:
        _safe_save_json(self.path, self.data)

    def get_user(self, user_id: int) -> dict:
        users = self.data.setdefault("users", {})
        return users.setdefault(str(user_id), {})

    def set_user(self, user_id: int, user_data: dict) -> None:
        self.data.setdefault("users", {})[str(user_id)] = user_data
        self.save()


STORE = Store(DATA_FILE)

# -----------------------------
# HELPERS
# -----------------------------
def parse_ddmmyyyy(s: str) -> Optional[date]:
    s = s.strip()
    try:
        dt = datetime.strptime(s, "%d.%m.%Y").date()
        return dt
    except Exception:
        return None


def today_in_tz(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


def days_lived(dob: date, tz: ZoneInfo) -> int:
    # "N-й день жизни" — обычно считают включительно:
    # если родился сегодня -> 1
    # поэтому: (today - dob).days + 1
    return (today_in_tz(tz) - dob).days + 1


def pick_task(user: dict, category: str) -> str:
    """
    Pick a task avoiding repeats over recent history (last ~7 picks per category).
    """
    recent = user.setdefault("recent", {}).setdefault(category, [])
    pool = TASKS_BY_CATEGORY[category]

    candidates = [t for t in pool if t not in recent[-7:]]
    if not candidates:
        candidates = pool[:]  # reset if exhausted

    task = random.choice(candidates)
    recent.append(task)
    user.setdefault("recent", {})[category] = recent[-30:]  # cap history
    return task


def get_or_init_settings(user: dict) -> dict:
    settings = user.setdefault("settings", {})
    settings.setdefault("timezone", TZ_NAME_DEFAULT)
    settings.setdefault("mode", "intensive_plus")  # includes 22:30
    settings.setdefault("times", dict(SCHEDULE_TIMES))
    settings.setdefault("weekend_light", False)
    return settings


def tz_for_user(user: dict) -> ZoneInfo:
    tz_name = user.get("settings", {}).get("timezone", TZ_NAME_DEFAULT)
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return TZ_DEFAULT


def format_digest(dob: date, tz: ZoneInfo, tasks: Dict[str, str]) -> str:
    n = days_lived(dob, tz)
    lines = [
        f"Сегодня твой <b>{n}-й</b> день жизни.",
        "",
        "<b>План на день — 5 мини-шагов:</b>",
    ]
    for cat in CATEGORY_ORDER:
        lines.append(f"• <b>{cat}:</b> {tasks[cat]}")
    lines.append("")
    lines.append("Выбери 1–2 пункта, которые реально сделаешь. (Можно просто мысленно.)")
    return "\n".join(lines)


def kb_checkin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Уже сделал(а) 1+", callback_data="ci_done"),
                InlineKeyboardButton("🟡 В процессе", callback_data="ci_progress"),
            ],
            [
                InlineKeyboardButton("🔴 Не начал", callback_data="ci_notyet"),
                InlineKeyboardButton("🎯 Сложно, помоги", callback_data="ci_help"),
            ],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        ]
    )


def kb_evening() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🌟 День ок", callback_data="ev_ok"),
                InlineKeyboardButton("😐 Так себе", callback_data="ev_meh"),
                InlineKeyboardButton("😵 Тяжело", callback_data="ev_hard"),
            ],
            [
                InlineKeyboardButton("🏋️ Тренировка: Да", callback_data="tr_yes"),
                InlineKeyboardButton("🚫 Нет", callback_data="tr_no"),
                InlineKeyboardButton("🤷 Не знаю", callback_data="tr_unsure"),
            ],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        ]
    )


def kb_late() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🙏 Благодарность", callback_data="rf_grat"),
                InlineKeyboardButton("✅ Победа", callback_data="rf_win"),
                InlineKeyboardButton("🧠 Вывод", callback_data="rf_takeaway"),
            ],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        ]
    )


def kb_settings_menu(user: dict) -> InlineKeyboardMarkup:
    settings = get_or_init_settings(user)
    mode = settings.get("mode", "intensive_plus")
    mode_label = {
        "light": "Лайт (утро+вечер)",
        "standard": "Стандарт (3/день)",
        "intensive": "Интенсив (4/день)",
        "intensive_plus": "Интенсив+ (5/день)",
    }.get(mode, mode)

    tz_label = settings.get("timezone", TZ_NAME_DEFAULT)

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"Режим: {mode_label}", callback_data="set_mode")],
            [InlineKeyboardButton(f"Таймзона: {tz_label}", callback_data="set_tz")],
            [InlineKeyboardButton("♻️ Пересоздать расписание", callback_data="reschedule")],
            [InlineKeyboardButton("❌ Закрыть", callback_data="close_settings")],
        ]
    )


def kb_mode_pick() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Лайт (09:00, 19:00)", callback_data="mode_light")],
            [InlineKeyboardButton("Стандарт (09:00, 12:00, 19:00)", callback_data="mode_standard")],
            [InlineKeyboardButton("Интенсив (09:00, 12:00, 16:00, 19:00)", callback_data="mode_intensive")],
            [InlineKeyboardButton("Интенсив+ (09:00, 12:00, 16:00, 19:00, 22:30)", callback_data="mode_intensive_plus")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="settings")],
        ]
    )


# -----------------------------
# JOB SCHEDULING
# -----------------------------
def _job_name(user_id: int, slot: str) -> str:
    return f"user:{user_id}:{slot}"


def remove_user_jobs(app: Application, user_id: int) -> None:
    jq = app.job_queue
    if not jq:
        return
    for slot in ["morning", "noon", "afternoon", "evening", "late"]:
        for j in jq.get_jobs_by_name(_job_name(user_id, slot)):
            j.schedule_removal()


def schedule_user_jobs(app: Application, user_id: int) -> None:
    """
    Create daily jobs for this user according to mode/times/timezone.
    """
    jq = app.job_queue
    if not jq:
        raise RuntimeError("JobQueue is not available. Install python-telegram-bot[job-queue].")

    user = STORE.get_user(user_id)
    settings = get_or_init_settings(user)
    tz = tz_for_user(user)
    times = settings.get("times", dict(SCHEDULE_TIMES))
    mode = settings.get("mode", "intensive_plus")

    # which slots are active by mode
    slots = []
    if mode == "light":
        slots = ["morning", "evening"]
    elif mode == "standard":
        slots = ["morning", "noon", "evening"]
    elif mode == "intensive":
        slots = ["morning", "noon", "afternoon", "evening"]
    else:  # intensive_plus
        slots = ["morning", "noon", "afternoon", "evening", "late"]

    # Remove old jobs first
    remove_user_jobs(app, user_id)

    # Schedule jobs
    for slot in slots:
        hh, mm = map(int, times[slot].split(":"))
        jq.run_daily(
            callback=job_dispatch,
            time=time(hour=hh, minute=mm, tzinfo=tz),
            name=_job_name(user_id, slot),
            data={"user_id": user_id, "slot": slot},
        )

    # Save (so we persist any new defaults)
    STORE.set_user(user_id, user)


async def job_dispatch(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data or {}
    user_id = int(data.get("user_id"))
    slot = data.get("slot", "")

    user = STORE.get_user(user_id)
    tz = tz_for_user(user)
    chat_id = user.get("chat_id")

    # if user not fully onboarded
    dob_s = user.get("dob")
    if not chat_id or not dob_s:
        return

    try:
        dob = datetime.strptime(dob_s, "%Y-%m-%d").date()
    except Exception:
        return

    # Avoid sending duplicates if process restarted and job triggers twice:
    today_key = str(today_in_tz(tz))
    sent = user.setdefault("sent", {}).setdefault(today_key, {})
    if sent.get(slot):
        return

    if slot == "morning":
        await send_morning(context, chat_id, user, dob, tz)
    elif slot in ("noon", "afternoon"):
        await send_checkin(context, chat_id, user, dob, tz, slot=slot)
    elif slot == "evening":
        await send_evening(context, chat_id, user, dob, tz)
    elif slot == "late":
        await send_late(context, chat_id, user, dob, tz)

    sent[slot] = True
    user.setdefault("sent", {})[today_key] = sent
    STORE.set_user(user_id, user)


async def send_morning(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user: dict, dob: date, tz: ZoneInfo) -> None:
    opener = random.choice(MORNING_OPENERS)

    today_key = str(today_in_tz(tz))
    daily = user.setdefault("daily", {}).setdefault(today_key, {})

    # Generate tasks: 1 from each category
    tasks = {}
    for cat in CATEGORY_ORDER:
        tasks[cat] = pick_task(user, cat)

    daily["tasks"] = tasks
    daily.setdefault("status", {"done": 0, "progress": 0, "notyet": 0, "help": 0})

    text = f"{opener}\n\n{format_digest(dob, tz, tasks)}"
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=kb_checkin(),  # reuse as quick actions
    )


async def send_checkin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user: dict, dob: date, tz: ZoneInfo, slot: str) -> None:
    today_key = str(today_in_tz(tz))
    daily = user.setdefault("daily", {}).setdefault(today_key, {})
    tasks = daily.get("tasks")

    if slot == "noon":
        prompt = random.choice(CHECKIN_12)
    else:
        prompt = random.choice(CHECKIN_16)

    # If somehow no tasks (e.g., user started today after morning), generate quick tasks
    if not tasks:
        tasks = {cat: pick_task(user, cat) for cat in CATEGORY_ORDER}
        daily["tasks"] = tasks

    short = "\n".join([f"• <b>{cat}</b>: {tasks[cat]}" for cat in CATEGORY_ORDER])

    text = (
        f"{prompt}\n\n"
        f"<b>Твой список на сегодня:</b>\n{short}\n\n"
        "Выбери статус — я подстроюсь."
    )

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=kb_checkin(),
    )


async def send_evening(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user: dict, dob: date, tz: ZoneInfo) -> None:
    prompt = random.choice(EVENING_CLOSE)
    today_key = str(today_in_tz(tz))
    daily = user.setdefault("daily", {}).setdefault(today_key, {})
    tasks = daily.get("tasks") or {cat: pick_task(user, cat) for cat in CATEGORY_ORDER}

    text = (
        f"{prompt}\n\n"
        "Если хочешь — коротко отметим, как прошло.\n"
        "И да: тренировка/движение сегодня планировались?"
    )
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb_evening())


async def send_late(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user: dict, dob: date, tz: ZoneInfo) -> None:
    prompt = random.choice(LATE_REFLECTION)
    text = f"{prompt}"
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb_late())


# -----------------------------
# HANDLERS
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    user = STORE.get_user(user_id)
    user["chat_id"] = chat_id
    get_or_init_settings(user)

    dob_s = user.get("dob")
    if not dob_s:
        await update.message.reply_text(
            "Привет! Это NewYouDay.\n\n"
            "Отправь дату рождения в формате ДД.ММ.ГГГГ (пример: 22.04.1983)."
        )
        STORE.set_user(user_id, user)
        return

    # If already onboarded: just confirm and (re)schedule
    STORE.set_user(user_id, user)
    schedule_user_jobs(context.application, user_id)

    await update.message.reply_text(
        "Я на связи ✅\n"
        "Расписание: 09:00 / 12:00 / 16:00 / 19:00 / 22:30 (Москва).\n\n"
        "⚙️ Настройки: /settings"
    )


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user = STORE.get_user(user_id)
    await update.message.reply_text("Настройки:", reply_markup=kb_settings_menu(user))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    user = STORE.get_user(user_id)
    user["chat_id"] = chat_id
    get_or_init_settings(user)

    # If DOB not set, treat incoming as DOB
    if not user.get("dob"):
        dob = parse_ddmmyyyy(text)
        if not dob:
            await update.message.reply_text("Не похоже на дату. Формат: ДД.ММ.ГГГГ (пример: 22.04.1983).")
            return

        user["dob"] = dob.isoformat()
        STORE.set_user(user_id, user)

        # schedule jobs immediately
        schedule_user_jobs(context.application, user_id)

        tz = tz_for_user(user)
        n = days_lived(dob, tz)
        await update.message.reply_text(
            f"Запомнил! Сегодня твой {n}-й день жизни.\n\n"
            "Я буду писать: 09:00 / 12:00 / 16:00 / 19:00 / 22:30 (Москва).\n"
            "⚙️ Настройки: /settings"
        )
        return

    # Otherwise: free-form messages – treat as reflection or status.
    # We won't be intrusive; just acknowledge and store last message.
    today_key = str(today_in_tz(tz_for_user(user)))
    daily = user.setdefault("daily", {}).setdefault(today_key, {})
    daily.setdefault("notes", []).append({"ts": datetime.now(tz_for_user(user)).isoformat(), "text": text})
    STORE.set_user(user_id, user)

    await update.message.reply_text("Принял 👍")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    user_id = query.from_user.id
    user = STORE.get_user(user_id)
    get_or_init_settings(user)
    tz = tz_for_user(user)
    today_key = str(today_in_tz(tz))
    daily = user.setdefault("daily", {}).setdefault(today_key, {})
    daily.setdefault("status", {"done": 0, "progress": 0, "notyet": 0, "help": 0})

    cd = query.data or ""

    # Check-in statuses
    if cd == "ci_done":
        daily["status"]["done"] += 1
        STORE.set_user(user_id, user)
        await query.edit_message_text("✅ Круто. Маленькая победа — это главное.")
        return

    if cd == "ci_progress":
        daily["status"]["progress"] += 1
        STORE.set_user(user_id, user)
        await query.edit_message_text("🟡 Отлично. Просто продолжай маленькими шагами.")
        return

    if cd == "ci_notyet":
        daily["status"]["notyet"] += 1
        # Give a tiny step suggestion
        tiny = "Супер-минимум на 3 минуты: сделай один микро-шаг (вода / 10 предметов на место / 10 приседаний)."
        STORE.set_user(user_id, user)
        await query.edit_message_text(f"🔴 Норм. Бывает.\n\n{tiny}")
        return

    if cd == "ci_help":
        daily["status"]["help"] += 1
        help_text = (
            "🎯 Ок, упростим.\n"
            "Выбираем ОДНУ задачу на 5–10 минут — и этого достаточно.\n\n"
            "Подсказка: возьми «Порядок» или «Тело» — они быстрее дают ощущение контроля."
        )
        STORE.set_user(user_id, user)
        await query.edit_message_text(help_text)
        return

    # Evening mood
    if cd in ("ev_ok", "ev_meh", "ev_hard"):
        mood_map = {
            "ev_ok": "🌟 Принял. Отлично, что день прожит.",
            "ev_meh": "😐 Понял. Нормальные дни тоже часть пути.",
            "ev_hard": "😵 Сочувствую. Давай без самобичевания — ты держишься.",
        }
        STORE.set_user(user_id, user)
        await query.edit_message_text(mood_map[cd])
        return

    # Training
    if cd in ("tr_yes", "tr_no", "tr_unsure"):
        if cd == "tr_yes":
            msg = "🏋️ Ок. Мини-выбор: 10 минут — уже победа. Главное начать."
        elif cd == "tr_no":
            msg = "🚫 Принял. Сегодня можно без вины. Важно восстановиться."
        else:
            msg = "🤷 Норм. Если сомневаешься — сделай 5 минут разминки и решишь дальше."
        STORE.set_user(user_id, user)
        await query.edit_message_text(msg)
        return

    # Reflection types
    if cd in ("rf_grat", "rf_win", "rf_takeaway"):
        msg_map = {
            "rf_grat": "🙏 Напиши 1–3 пункта благодарности (можно коротко).",
            "rf_win": "✅ Напиши одну победу дня (даже маленькую).",
            "rf_takeaway": "🧠 Напиши один вывод дня (одно предложение).",
        }
        await query.edit_message_text(msg_map[cd])
        return

    # Settings menu
    if cd == "settings":
        await query.edit_message_text("Настройки:", reply_markup=kb_settings_menu(user))
        return

    if cd == "close_settings":
        await query.edit_message_text("Ок ✅")
        return

    if cd == "set_mode":
        await query.edit_message_text("Выбери режим:", reply_markup=kb_mode_pick())
        return

    if cd.startswith("mode_"):
        mode = cd.replace("mode_", "").strip()
        settings = get_or_init_settings(user)
        settings["mode"] = mode
        user["settings"] = settings
        STORE.set_user(user_id, user)

        # Reschedule now
        schedule_user_jobs(context.application, user_id)

        await query.edit_message_text("Готово ✅ Режим обновлён.", reply_markup=kb_settings_menu(user))
        return

    if cd == "set_tz":
        await query.edit_message_text(
            "Сейчас таймзона фиксирована на Europe/Moscow (GMT+3).\n"
            "Если нужно расширим на выбор.\n\n"
            "⬅️ Назад",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="settings")]]),
        )
        return

    if cd == "reschedule":
        schedule_user_jobs(context.application, user_id)
        await query.edit_message_text("♻️ Пересоздал расписание ✅", reply_markup=kb_settings_menu(user))
        return

    # fallback
    await query.edit_message_text("Ок.")


# -----------------------------
# MAIN
# -----------------------------
def main() -> None:
    logging.basicConfig(level=LOG_LEVEL)
    logger = logging.getLogger(__name__)
    logger.info("Starting NewYouDay bot...")

    app = Application.builder().token(TOKEN).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # Important: ensure no webhook (prevents conflicts)
    # PTB will call deleteWebhook internally in run_polling, but we keep it explicit-ish by relying on PTB.
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
