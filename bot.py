# bot.py
# Telegram коуч-ассистент: @NewYouDay_bot
# Режим: 09:00 / 12:00 / 16:00 / 19:00 / 22:30 (GMT+3, Europe/Moscow)
#
# Важно для Render:
# 1) В Environment переменная BOT_TOKEN = <токен>
# 2) В requirements.txt нужен python-telegram-bot[job-queue]
# 3) (рекомендовано) подключи Render Disk и смонтируй в /var/data + env DATA_DIR=/var/data
#
# pip package: python-telegram-bot[job-queue]>=20

import json
import logging
import os
import random
from datetime import datetime, date, time
from typing import Dict, List, Optional

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
# If you attach Render Disk, mount it to /var/data and set DATA_DIR=/var/data
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

# Добавили отдельную категорию "Тренировка"
CATEGORY_ORDER = ["Тело", "Тренировка", "Ум", "Восстановление", "Порядок", "Смысл"]

# 10 задач в каждой категории
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
    "Тренировка": [
        "🏋️ Гиря (10 мин): махи 10×10 (каждую минуту 10 махов, спокойно).",
        "🏋️ Гиря (8–12 мин): гоблет-присед 5×8 + отдых 45–60с.",
        "🏋️ Гиря (10 мин): тяга к поясу 4×10/сторона (контроль корпуса).",
        "🏋️ Гиря (10 мин): жим стоя 5×6/сторона (лёгко/средне).",
        "🏋️ Гиря (10 мин): становая 5×8 (ровная спина, без рывков).",
        "💥 Отжимания: 5 подходов «не до отказа» (оставь 2–3 повтора в запасе).",
        "💥 Отжимания + планка: 6 раундов (отжим 6–10 + планка 20–30с).",
        "💥 Лестница отжиманий: 2-4-6-8-6-4-2 (или легче: 1-2-3-4-3-2-1).",
        "🏋️+💥 Мини-комплекс 12 мин: махи 12 / отжимания 8 / отдых 60с × 4 круга.",
        "✅ Самое простое: 3 минуты — 15 махов + 10 отжиманий (или с колен).",
    ],
    "Ум": [
        "📚 30 минут чтения (любая книга, без перфекционизма).",
        "🧩 10 минут: выпиши 5 задач дня и выбери одну главную.",
        "✍️ 7 минут: что сегодня важно и почему (1 абзац для себя).",
        "🧠 15 минут «глубокой работы»: один файл/одна задача/без вкладок.",
        "🗂️ 10 минут: разобрать заметки/входящие (только быстрые решения).",
        "🎧 12 минут обучения — и 1 вывод (в голове или в заметке).",
        "🧾 8 минут: мини-план на завтра (3 пункта).",
        "🔎 10 минут: найди 1 помеху продуктивности и убери её.",
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
        "🌙 8 минут: выключи яркий свет и включи «режим вечера».",
        "🧠 5 минут: выпиши 3 тревоги → рядом 1 действие/или «отпускаю».",
        "🧍 6 минут: расслабь челюсть/плечи + медленное дыхание.",
        "📵 15–30 минут до сна без телефона (как получится).",
    ],
    "Порядок": [
        "🧹 10 минут быстрой уборки: одна зона (стол/полка/раковина).",
        "📩 10 минут: входящие — закрыть 5 мелких хвостов.",
        "🧠 12 минут: привести в порядок рабочее место.",
        "🧺 8 минут: сложить вещи/корзина — до видимого результата.",
        "🗑️ 6 минут: выбросить мусор/разобрать одну «кучу».",
        "🧾 10 минут: папки/платежи — только самое нужное.",
        "📦 10 минут: разбор одного ящика (без фанатизма).",
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
        "🧩 5 минут: сформулируй принцип дня (одно предложение).",
        "🕯️ 7 минут: без экрана — посиди и подумай о главном.",
        "📞 5 минут: позвони/напиши человеку, которого давно не слышал.",
        "🫶 3 минуты: похвали себя за одно действие (даже маленькое).",
    ],
}

# -----------------------------
# COACH TONE / PROMPTS
# -----------------------------
MORNING_OPENERS = [
    "Доброе утро. Давай соберём день спокойно и по делу.",
    "Утро. Никакой суеты — просто маленькие шаги.",
    "Привет. Сегодня сделаем чуть лучше, чем вчера.",
    "Доброе. План на день — коротко, но мощно.",
    "Утро. Выбираем фокус и идём.",
]

CHECKIN_12 = [
    "12:00 — короткий чек-ин. Как ты? Что уже удалось сделать?",
    "Середина дня. Есть 1 маленький шаг, который ты уже сделал?",
    "Как идёт день? Без давления — просто статус.",
    "Чек-ин: что продвинулось с утра?",
]

CHECKIN_16 = [
    "16:00 — сверка курса. Что получается, а что буксует?",
    "Вторая половина дня. Нужна помощь упростить план?",
    "Какой статус? Если тяжело — уменьшим до микро-шага.",
    "Давай быстро: победа / процесс / стоп — что сейчас?",
]

EVENING_CLOSE = [
    "19:00 — хороший момент поставить точку в работе. Как ты?",
    "Вечер. Давай мягко закроем день и переключимся.",
    "Финиш рабочего дня. Что получилось — даже если немного?",
    "Вечерний чек. Какое одно дело сегодня было самым важным?",
]

LATE_REFLECTION = [
    "22:30 — выдох. Ты сделал достаточно на сегодня.",
    "Время выключаться. Пусть голова отдохнёт.",
    "Тихий финал дня: просто отметь — ты в процессе, и это нормально.",
    "Пусть сон восстановит тебя. Завтра продолжим.",
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
        return datetime.strptime(s, "%d.%m.%Y").date()
    except Exception:
        return None


def today_in_tz(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


def days_lived(dob: date, tz: ZoneInfo) -> int:
    return (today_in_tz(tz) - dob).days + 1


def get_or_init_settings(user: dict) -> dict:
    settings = user.setdefault("settings", {})
    settings.setdefault("timezone", TZ_NAME_DEFAULT)
    settings.setdefault("mode", "intensive_plus")  # 09/12/16/19/22:30
    settings.setdefault("times", dict(SCHEDULE_TIMES))
    return settings


def tz_for_user(user: dict) -> ZoneInfo:
    tz_name = user.get("settings", {}).get("timezone", TZ_NAME_DEFAULT)
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return TZ_DEFAULT


def pick_task(user: dict, category: str) -> str:
    """
    Pick a task avoiding repeats over recent history (last ~7 picks per category).
    """
    recent = user.setdefault("recent", {}).setdefault(category, [])
    pool = TASKS_BY_CATEGORY[category]

    candidates = [t for t in pool if t not in recent[-7:]]
    if not candidates:
        candidates = pool[:]

    task = random.choice(candidates)
    recent.append(task)
    user.setdefault("recent", {})[category] = recent[-30:]
    return task


def format_digest(dob: date, tz: ZoneInfo, tasks: Dict[str, str]) -> str:
    n = days_lived(dob, tz)
    lines = [
        f"Сегодня твой <b>{n}-й</b> день жизни.",
        "",
        "<b>План на день — мини-шаги по сферам:</b>",
    ]
    for cat in CATEGORY_ORDER:
        lines.append(f"• <b>{cat}:</b> {tasks[cat]}")
    lines.append("")
    lines.append("Выбирай без перфекционизма: 1–2 пункта — уже победа.")
    return "\n".join(lines)


def kb_checkin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Уже сделал 1+", callback_data="ci_done"),
                InlineKeyboardButton("🟡 В процессе", callback_data="ci_progress"),
            ],
            [
                InlineKeyboardButton("🔴 Ещё нет", callback_data="ci_notyet"),
                InlineKeyboardButton("🎯 Сложно — упрости", callback_data="ci_help"),
            ],
            [InlineKeyboardButton("📌 Показать план дня (/today)", callback_data="show_today")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        ]
    )


def kb_evening() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🌟 Хорошо", callback_data="ev_ok"),
                InlineKeyboardButton("😐 Нормально", callback_data="ev_meh"),
                InlineKeyboardButton("😵 Тяжело", callback_data="ev_hard"),
            ],
            [
                InlineKeyboardButton("🏋️ Тренировка: да", callback_data="tr_yes"),
                InlineKeyboardButton("🚫 нет", callback_data="tr_no"),
                InlineKeyboardButton("🤷 не знаю", callback_data="tr_unsure"),
            ],
            [InlineKeyboardButton("📌 План дня (/today)", callback_data="show_today")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        ]
    )


def kb_late() -> InlineKeyboardMarkup:
    # Никаких просьб "напиши". Только мягкие варианты.
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🙏 Спасибо, день закрыт", callback_data="late_ok"),
                InlineKeyboardButton("😌 Выключаюсь", callback_data="late_off"),
                InlineKeyboardButton("💤 Спать", callback_data="late_sleep"),
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
    jq = app.job_queue
    if not jq:
        raise RuntimeError("JobQueue is not available. Install python-telegram-bot[job-queue].")

    user = STORE.get_user(user_id)
    settings = get_or_init_settings(user)
    tz = tz_for_user(user)
    times = settings.get("times", dict(SCHEDULE_TIMES))
    mode = settings.get("mode", "intensive_plus")

    if mode == "light":
        slots = ["morning", "evening"]
    elif mode == "standard":
        slots = ["morning", "noon", "evening"]
    elif mode == "intensive":
        slots = ["morning", "noon", "afternoon", "evening"]
    else:
        slots = ["morning", "noon", "afternoon", "evening", "late"]

    remove_user_jobs(app, user_id)

    for slot in slots:
        hh, mm = map(int, times[slot].split(":"))
        jq.run_daily(
            callback=job_dispatch,
            time=time(hour=hh, minute=mm, tzinfo=tz),
            name=_job_name(user_id, slot),
            data={"user_id": user_id, "slot": slot},
        )

    STORE.set_user(user_id, user)


async def job_dispatch(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data or {}
    user_id = int(data.get("user_id"))
    slot = data.get("slot", "")

    user = STORE.get_user(user_id)
    tz = tz_for_user(user)
    chat_id = user.get("chat_id")
    dob_s = user.get("dob")

    if not chat_id or not dob_s:
        return

    try:
        dob = datetime.strptime(dob_s, "%Y-%m-%d").date()
    except Exception:
        return

    # Защита от дублей в рамках дня/слота (например, если процесс перезапустился)
    today_key = str(today_in_tz(tz))
    sent = user.setdefault("sent", {}).setdefault(today_key, {})
    if sent.get(slot):
        return

    if slot == "morning":
        await send_morning(context, chat_id, user, dob, tz)
    elif slot in ("noon", "afternoon"):
        await send_checkin(context, chat_id, user, tz, slot=slot)
    elif slot == "evening":
        await send_evening(context, chat_id, tz)
    elif slot == "late":
        await send_late(context, chat_id)

    sent[slot] = True
    user.setdefault("sent", {})[today_key] = sent
    STORE.set_user(user_id, user)


async def send_morning(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user: dict, dob: date, tz: ZoneInfo) -> None:
    opener = random.choice(MORNING_OPENERS)

    today_key = str(today_in_tz(tz))
    daily = user.setdefault("daily", {}).setdefault(today_key, {})

    tasks = {cat: pick_task(user, cat) for cat in CATEGORY_ORDER}
    daily["tasks"] = tasks
    daily.setdefault("status", {"done": 0, "progress": 0, "notyet": 0, "help": 0})

    text = f"{opener}\n\n{format_digest(dob, tz, tasks)}"
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=kb_checkin(),
    )


async def send_checkin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user: dict, tz: ZoneInfo, slot: str) -> None:
    # НЕ повторяем список задач. Только вопросы.
    prompt = random.choice(CHECKIN_12) if slot == "noon" else random.choice(CHECKIN_16)

    text = (
        f"{prompt}\n\n"
        "Выбери статус кнопкой ниже. "
        "Если нужно — я покажу план дня по команде /today."
    )
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb_checkin())


async def send_evening(context: ContextTypes.DEFAULT_TYPE, chat_id: int, tz: ZoneInfo) -> None:
    prompt = random.choice(EVENING_CLOSE)
    text = (
        f"{prompt}\n\n"
        "Если хочешь — отметим настроение и решим про тренировку/движение."
    )
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=kb_evening())


async def send_late(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    prompt = random.choice(LATE_REFLECTION)
    await context.bot.send_message(chat_id=chat_id, text=prompt, reply_markup=kb_late())


# -----------------------------
# COMMANDS
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    user = STORE.get_user(user_id)
    user["chat_id"] = chat_id
    get_or_init_settings(user)

    if not user.get("dob"):
        await update.message.reply_text(
            "Привет! Это NewYouDay — твой коуч-ассистент.\n\n"
            "Отправь дату рождения в формате ДД.ММ.ГГГГ (пример: 22.04.1983)."
        )
        STORE.set_user(user_id, user)
        return

    STORE.set_user(user_id, user)
    schedule_user_jobs(context.application, user_id)

    await update.message.reply_text(
        "Я на связи ✅\n"
        "Расписание: 09:00 / 12:00 / 16:00 / 19:00 / 22:30 (Москва).\n\n"
        "Команды:\n"
        "• /today — показать план дня\n"
        "• /settings — настройки"
    )


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user = STORE.get_user(user_id)
    await update.message.reply_text("Настройки:", reply_markup=kb_settings_menu(user))


async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user = STORE.get_user(user_id)
    tz = tz_for_user(user)

    dob_s = user.get("dob")
    if not dob_s:
        await update.message.reply_text("Сначала отправь дату рождения: ДД.ММ.ГГГГ")
        return

    dob = datetime.strptime(dob_s, "%Y-%m-%d").date()
    today_key = str(today_in_tz(tz))
    daily = user.setdefault("daily", {}).setdefault(today_key, {})

    tasks = daily.get("tasks")
    if not tasks:
        # если почему-то нет — генерим, но только по запросу пользователя
        tasks = {cat: pick_task(user, cat) for cat in CATEGORY_ORDER}
        daily["tasks"] = tasks
        STORE.set_user(user_id, user)

    text = format_digest(dob, tz, tasks)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_checkin())


# -----------------------------
# TEXT HANDLER
# -----------------------------
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    user = STORE.get_user(user_id)
    user["chat_id"] = chat_id
    get_or_init_settings(user)

    if not user.get("dob"):
        dob = parse_ddmmyyyy(text)
        if not dob:
            await update.message.reply_text("Не похоже на дату. Формат: ДД.ММ.ГГГГ (пример: 22.04.1983).")
            return

        user["dob"] = dob.isoformat()
        STORE.set_user(user_id, user)
        schedule_user_jobs(context.application, user_id)

        tz = tz_for_user(user)
        n = days_lived(dob, tz)
        await update.message.reply_text(
            f"Запомнил! Сегодня твой {n}-й день жизни.\n\n"
            "Я буду писать: 09:00 / 12:00 / 16:00 / 19:00 / 22:30 (Москва).\n"
            "Команда: /today — показать план дня\n"
            "Настройки: /settings"
        )
        return

    # Свободный текст: короткое подтверждение без навязывания
    now = datetime.now(tz_for_user(user)).isoformat()
    today_key = str(today_in_tz(tz_for_user(user)))
    daily = user.setdefault("daily", {}).setdefault(today_key, {})
    daily.setdefault("notes", []).append({"ts": now, "text": text})
    STORE.set_user(user_id, user)

    await update.message.reply_text("Принял 👍")


# -----------------------------
# CALLBACKS (ВАЖНО: НЕ редактируем утренний дайджест!)
# -----------------------------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message:
        return

    user_id = query.from_user.id
    user = STORE.get_user(user_id)
    get_or_init_settings(user)
    tz = tz_for_user(user)
    today_key = str(today_in_tz(tz))
    daily = user.setdefault("daily", {}).setdefault(today_key, {})
    daily.setdefault("status", {"done": 0, "progress": 0, "notyet": 0, "help": 0})

    cd = query.data or ""
    await query.answer()  # убираем "часики" на кнопке

    chat_id = query.message.chat_id

    async def reply_short(msg: str) -> None:
        # Отвечаем НОВЫМ сообщением, чтобы план дня не исчезал/не перезаписывался
        await context.bot.send_message(chat_id=chat_id, text=msg)

    # показать план дня
    if cd == "show_today":
        # эквивалент /today, но через кнопку
        dob_s = user.get("dob")
        if not dob_s:
            await reply_short("Сначала отправь дату рождения: ДД.ММ.ГГГГ")
            return
        dob = datetime.strptime(dob_s, "%Y-%m-%d").date()
        tasks = daily.get("tasks")
        if not tasks:
            tasks = {cat: pick_task(user, cat) for cat in CATEGORY_ORDER}
            daily["tasks"] = tasks
            STORE.set_user(user_id, user)
        text = format_digest(dob, tz, tasks)
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML, reply_markup=kb_checkin())
        return

    # Check-in statuses
    if cd == "ci_done":
        daily["status"]["done"] += 1
        STORE.set_user(user_id, user)
        await reply_short("✅ Отлично. Это и есть дисциплина: маленькие шаги каждый день.")
        return

    if cd == "ci_progress":
        daily["status"]["progress"] += 1
        STORE.set_user(user_id, user)
        await reply_short("🟡 Супер. Продолжай. Главное — не бросать, а упрощать при необходимости.")
        return

    if cd == "ci_notyet":
        daily["status"]["notyet"] += 1
        STORE.set_user(user_id, user)
        await reply_short("🔴 Ок. Давай так: выбери один микро-шаг на 3–5 минут — и этого достаточно.")
        return

    if cd == "ci_help":
        daily["status"]["help"] += 1
        STORE.set_user(user_id, user)
        await reply_short(
            "🎯 Упрощаем.\n"
            "Выбираем ОДНУ задачу на 5–10 минут.\n"
            "Если совсем тяжело — сделай вариант из «Тренировка»: 15 махов + 10 отжиманий (или с колен)."
        )
        return

    # Evening mood
    if cd in ("ev_ok", "ev_meh", "ev_hard"):
        mood_map = {
            "ev_ok": "🌟 Класс. Зафиксировали: день вышел хорошим.",
            "ev_meh": "😐 Нормально. Ровные дни тоже строят результат.",
            "ev_hard": "😵 Понимаю. Сегодня — мягко к себе. Завтра продолжим без самокритики.",
        }
        await reply_short(mood_map[cd])
        return

    # Training
    if cd in ("tr_yes", "tr_no", "tr_unsure"):
        if cd == "tr_yes":
            msg = "🏋️ Отлично. Даже 10 минут — это победа. Начни с простого и остановись вовремя."
        elif cd == "tr_no":
            msg = "🚫 Ок. Сегодня можно выбрать восстановление. Это тоже часть прогресса."
        else:
            msg = "🤷 Норм. Сомневаешься — сделай 2 минуты разминки. После неё решение приходит легче."
        await reply_short(msg)
        return

    # Late buttons (без "пиши")
    if cd in ("late_ok", "late_off", "late_sleep"):
        late_map = {
            "late_ok": "🙏 Принято. Пусть вечер будет спокойным. Ты молодец, что держишь курс.",
            "late_off": "😌 Отлично. Выключаем шум — и даём мозгу отдых.",
            "late_sleep": "💤 Спокойной ночи. Завтра продолжим.",
        }
        await reply_short(late_map[cd])
        return

    # Settings menu
    if cd == "settings":
        await query.message.reply_text("Настройки:", reply_markup=kb_settings_menu(user))
        return

    if cd == "close_settings":
        await reply_short("Ок ✅")
        return

    if cd == "set_mode":
        await query.message.reply_text("Выбери режим:", reply_markup=kb_mode_pick())
        return

    if cd.startswith("mode_"):
        mode = cd.replace("mode_", "").strip()
        settings = get_or_init_settings(user)
        settings["mode"] = mode
        user["settings"] = settings
        STORE.set_user(user_id, user)

        schedule_user_jobs(context.application, user_id)

        await reply_short("Готово ✅ Режим обновлён.")
        return

    if cd == "set_tz":
        await reply_short("Сейчас таймзона фиксирована на Europe/Moscow (GMT+3). Если нужно — добавим выбор.")
        return

    if cd == "reschedule":
        schedule_user_jobs(context.application, user_id)
        await reply_short("♻️ Пересоздал расписание ✅")
        return

    await reply_short("Ок.")


# -----------------------------
# MAIN
# -----------------------------
def main() -> None:
    logging.basicConfig(level=LOG_LEVEL)
    logger = logging.getLogger(__name__)
    logger.info("Starting NewYouDay bot...")

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("today", today_cmd))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # drop_pending_updates=True помогает не ловить старые апдейты после рестарта
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
