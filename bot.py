from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from zoneinfo import ZoneInfo

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
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

# -----------------------
# ЛОГИ
# -----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("newyouday")

# -----------------------
# КОНФИГ
# -----------------------
BOT_NAME = "@NewYouDay_bot"
DEFAULT_TZ_NAME = "Europe/Moscow"
DEFAULT_TZ = ZoneInfo(DEFAULT_TZ_NAME)

SCHEDULE_TIMES = {
    "morning": time(9, 0, tzinfo=DEFAULT_TZ),
    "noon": time(12, 0, tzinfo=DEFAULT_TZ),
    "afternoon": time(16, 0, tzinfo=DEFAULT_TZ),
    "evening": time(19, 0, tzinfo=DEFAULT_TZ),
    "late": time(22, 30, tzinfo=DEFAULT_TZ),
}

CATEGORY_ORDER = ["Тело", "Ум", "Восстановление", "Порядок", "Смысл", "Тренировка"]

TASKS_BY_CATEGORY: Dict[str, list[str]] = {
    "Тело": [
        "💪 12 минут зарядки: 3 круга (приседания 12 / отжимания 8 / планка 30с).",
        "🚶 25 минут прогулки бодрым шагом (без телефона).",
        "🧘 8 минут мягкой растяжки шея/спина/таз — без боли.",
        "🫧 10 минут дыхания + осанка: выпрями спину, расслабь плечи.",
        "🥤 Вода: 3 стакана до обеда (напомни себе таймером).",
        "🍎 Один полезный выбор: добавь овощи/фрукты в один приём пищи.",
        "🦵 10 минут мобилизации: голеностоп/таз/грудной отдел.",
        "🧍 7 минут прогулки каждый час (микро-перерывы).",
        "😴 Лёгкий режим: 15 минут без экрана перед сном.",
        "🌿 5 минут на свежем воздухе: просто постой и подыши.",
    ],
    "Ум": [
        "📚 30 минут чтения (любая книга, без перфекционизма).",
        "🧠 10 минут: выпиши 3 задачи дня и выбери одну главную.",
        "✍️ 7 минут: короткая заметка «что важно сегодня» (в голове или в заметках).",
        "🎧 15 минут обучения: видео/статья по теме, которую прокачиваешь.",
        "🧩 10 минут: реши одну маленькую задачу (логика/язык/математика).",
        "🗂️ 12 минут: разбор входящих (почта/мессенджеры) по таймеру.",
        "🧭 5 минут: сформулируй цель дня одним предложением.",
        "📝 10 минут: набросай план следующего шага по проекту (1 шаг).",
        "🔍 8 минут: наведи ясность — что тормозит? назови причину.",
        "📌 5 минут: «что я могу упростить сегодня?»",
    ],
    "Восстановление": [
        "🫁 5 минут дыхание: вдох 4 — выдох 6.",
        "⏳ 1 час без соцсетей (поставь таймер).",
        "🌿 10 минут тишины: без музыки/новостей, просто пауза.",
        "☕ 10 минут медленного чая/кофе — осознанно, без прокрутки ленты.",
        "🧊 30 секунд холодной воды в конце душа (если ок по самочувствию).",
        "😌 3 минуты расслабления: лицо/челюсть/плечи.",
        "🪟 Проветри комнату/кабинет на 5 минут.",
        "🧘 6 минут: мягкая разминка + дыхание.",
        "🎵 1 любимая песня — послушай полностью, не отвлекаясь.",
        "🌙 15 минут заранее: начни готовить сон (свет/тишина).",
    ],
    "Порядок": [
        "🧹 10 минут быстрой уборки: одна зона (стол/полка/раковина).",
        "📬 10 минут: почта/входящие — закрыть 5 мелких хвостов.",
        "🧑‍💻 12 минут: приведи в порядок рабочее место.",
        "🧺 10 минут: стирка/разбор вещей по таймеру.",
        "📦 8 минут: выбросить/отдать 5 ненужных вещей.",
        "🗃️ 10 минут: файлы/папки — один маленький порядок.",
        "🧾 10 минут: финансы — 1 действие (счёт/платёж/план).",
        "🧼 7 минут: чистота — одна микрозадача (раковина/зеркало).",
        "🧹 5 минут: «сразу убрать на место» — 10 предметов.",
        "🧾 8 минут: список покупок/дел — обновить и упростить.",
    ],
    "Смысл": [
        "🤝 Напиши одному человеку короткое тёплое сообщение (без повода).",
        "🙏 Вспомни 3 вещи, за которые благодарен сегодня (можно просто подумать).",
        "❤️ Сделай один маленький поступок для близких (конкретный).",
        "🧡 Поддержи кого-то: 1 фраза, 1 действие.",
        "🎯 Сделай одно важное дело. Не десять — одно.",
        "🧩 «Кому я могу помочь сегодня на 5 минут?»",
        "🧭 «Какой мой главный приоритет на этой неделе?» (1 строка).",
        "🌱 Маленький шаг в сторону мечты: 10 минут по таймеру.",
        "🕯️ Вспомни, что даёт тебе энергию — добавь это сегодня на 5 минут.",
        "🏁 «Что я хочу почувствовать в конце дня?» — выбери 1 слово.",
    ],
    "Тренировка": [
        "🏋️ Гиря: 10 минут EMOM — 10 махов в начале каждой минуты (умеренно).",
        "🏋️ Гиря: 5×10 махов, отдых 60–90с (техника важнее темпа).",
        "🏋️ Гиря: 3 круга — махи 15 / присед 12 / планка 30с.",
        "🏋️ Гиря: 10 минут техника — лёгкие махи + дыхание, без героизма.",
        "💥 Отжимания: лестница 3–4–5–4–3 (с паузами 30–60с).",
        "💥 Отжимания: 5×8 (или 5×6), оставь 1–2 повтора в запасе.",
        "💥 Отжимания + пресс: 3 круга — отжимания 8 / скручивания 12 / планка 30с.",
        "🦵 Ноги + гиря: 4 круга — присед 12 / махи 12 / отдых 60с.",
        "🧘 Восстановительная: 12 минут — мобилизация + лёгкая силовая (без боли).",
        "🏃 Мини-кардио: 12 минут — шаг/лёгкий бег интервалы 1 мин/1 мин.",
    ],
}

# -----------------------
# ХРАНЕНИЕ ДАННЫХ
# -----------------------
DATE_RE = re.compile(r"^\s*(\d{2})\.(\d{2})\.(\d{4})\s*$")


def _data_dir() -> Path:
    d = os.getenv("DATA_DIR", "").strip()
    if d:
        return Path(d)
    return Path("./data")


@dataclass
class DataStore:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"users": {}})

    def _read(self) -> Dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"users": {}}

    def _write(self, data: Dict[str, Any]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def get_user(self, chat_id: int) -> Dict[str, Any]:
        root = self._read()
        users = root.setdefault("users", {})
        u = users.get(str(chat_id))
        if not u:
            u = {
                "dob": None,  # "YYYY-MM-DD"
                "tz": DEFAULT_TZ_NAME,
                "plans": {},  # "YYYY-MM-DD": {cat: task, ...}
                "progress": {},  # "YYYY-MM-DD": {k: v}
            }
            users[str(chat_id)] = u
            self._write(root)
        return u

    def set_user(self, chat_id: int, patch: Dict[str, Any]) -> None:
        root = self._read()
        users = root.setdefault("users", {})
        u = users.get(str(chat_id)) or {}
        u.update(patch)
        users[str(chat_id)] = u
        self._write(root)

    def set_plan(self, chat_id: int, day: str, plan: Dict[str, str]) -> None:
        root = self._read()
        users = root.setdefault("users", {})
        u = users.get(str(chat_id)) or {"dob": None, "tz": DEFAULT_TZ_NAME, "plans": {}, "progress": {}}
        plans = u.setdefault("plans", {})
        plans[day] = plan
        users[str(chat_id)] = u
        self._write(root)

    def set_progress(self, chat_id: int, day: str, key: str, value: Any) -> None:
        root = self._read()
        users = root.setdefault("users", {})
        u = users.get(str(chat_id)) or {"dob": None, "tz": DEFAULT_TZ_NAME, "plans": {}, "progress": {}}
        progress = u.setdefault("progress", {})
        dayprog = progress.setdefault(day, {})
        dayprog[key] = value
        users[str(chat_id)] = u
        self._write(root)

    def all_chat_ids(self) -> list[int]:
        root = self._read()
        users = root.get("users", {})
        out = []
        for k in users.keys():
            try:
                out.append(int(k))
            except ValueError:
                continue
        return out


STORE = DataStore(_data_dir() / "newyouday_users.json")

# -----------------------
# ПЛАН ДНЯ
# -----------------------
def _stable_int_seed(chat_id: int, day: date) -> int:
    s = f"{chat_id}:{day.isoformat()}".encode("utf-8")
    h = hashlib.sha256(s).hexdigest()
    return int(h[:16], 16)


def build_plan(chat_id: int, day: date) -> Dict[str, str]:
    seed = _stable_int_seed(chat_id, day)
    plan: Dict[str, str] = {}
    for i, cat in enumerate(CATEGORY_ORDER):
        items = TASKS_BY_CATEGORY.get(cat, [])
        if not items:
            plan[cat] = "—"
            continue
        idx = (seed + i * 9973) % len(items)
        plan[cat] = items[idx]
    return plan


def get_or_create_today_plan(chat_id: int, tz: ZoneInfo) -> Dict[str, str]:
    today = datetime.now(tz).date().isoformat()
    u = STORE.get_user(chat_id)
    plans: Dict[str, Dict[str, str]] = u.get("plans", {}) or {}
    plan = plans.get(today)
    if plan:
        changed = False
        fresh_plan = build_plan(chat_id, datetime.now(tz).date())
        for cat in CATEGORY_ORDER:
            if cat not in plan:
                plan[cat] = fresh_plan[cat]
                changed = True
        if changed:
            STORE.set_plan(chat_id, today, plan)
        return plan

    plan = build_plan(chat_id, datetime.now(tz).date())
    STORE.set_plan(chat_id, today, plan)
    return plan


def format_plan(plan: Dict[str, str]) -> str:
    lines = []
    for cat in CATEGORY_ORDER:
        task = plan.get(cat, "—")
        lines.append(f"<b>{cat}:</b>\n{task}")
    return "\n\n".join(lines)


# -----------------------
# JOBS / SCHEDULER
# -----------------------
def clear_user_jobs(app: Application, chat_id: int) -> None:
    jq = app.job_queue
    if not jq:
        return
    prefix = f"user:{chat_id}:"
    for job in jq.jobs():
        if job.name and job.name.startswith(prefix):
            job.schedule_removal()


def schedule_user(app: Application, chat_id: int) -> None:
    jq = app.job_queue
    if not jq:
        return

    clear_user_jobs(app, chat_id)

    jq.run_daily(job_morning, time=SCHEDULE_TIMES["morning"], name=f"user:{chat_id}:morning", data={"chat_id": chat_id})
    jq.run_daily(job_noon, time=SCHEDULE_TIMES["noon"], name=f"user:{chat_id}:noon", data={"chat_id": chat_id})
    jq.run_daily(job_afternoon, time=SCHEDULE_TIMES["afternoon"], name=f"user:{chat_id}:afternoon", data={"chat_id": chat_id})
    jq.run_daily(job_evening, time=SCHEDULE_TIMES["evening"], name=f"user:{chat_id}:evening", data={"chat_id": chat_id})
    jq.run_daily(job_late, time=SCHEDULE_TIMES["late"], name=f"user:{chat_id}:late", data={"chat_id": chat_id})

    log.info("Scheduled jobs for chat_id=%s", chat_id)


async def schedule_all_users(app: Application) -> None:
    for chat_id in STORE.all_chat_ids():
        schedule_user(app, chat_id)


# -----------------------
# ТЕКСТЫ (КОУЧ)
# -----------------------
def header_text() -> str:
    return (
        "Я на связи ✅\n"
        f"Расписание: 09:00 / 12:00 / 16:00 / 19:00 / 22:30 (Москва).\n\n"
        "Команды:\n"
        "• /today — показать план дня\n"
        "• /settings — настройки\n"
    )


def days_lived(dob_iso: str, tz: ZoneInfo) -> int:
    dob = date.fromisoformat(dob_iso)
    today = datetime.now(tz).date()
    return (today - dob).days + 1


def morning_text(plan: Dict[str, str], dob_iso: str, tz: ZoneInfo) -> str:
    lived = days_lived(dob_iso, tz)
    return (
        "🌅 Доброе утро.\n"
        f"Сегодня твой <b>{lived}-й</b> день жизни.\n\n"
        "Твой план на сегодня — <b>6 коротких шагов</b>. Без перегруза, но по делу.\n"
        "Сохрани это сообщение (или просто знай: план всегда доступен через /today).\n\n"
        f"{format_plan(plan)}\n\n"
        "🎯 Фокус: сделай <b>одно важное</b> и <b>один шаг по телу</b> — остальное бонусом."
    )


def noon_text() -> str:
    return (
        "🕛 Чек-ин.\n"
        "Как идёт день? Что уже сдвинулось — хотя бы на 1%?\n"
        "Выбери вариант — я подстроюсь."
    )


def afternoon_text() -> str:
    return (
        "✅ Маленькая победа важнее идеала.\n"
        "Удалось сделать что-то из плана или продвинуть главное дело?"
    )


def evening_text() -> str:
    return (
        "🌆 Вечерний финиш.\n"
        "Рабочую часть дня закрываем спокойно и с уважением к себе.\n"
        "Тренировка сегодня будет? (даже 10 минут — уже считается)."
    )


def late_text() -> str:
    return (
        "🌙 Мягкое завершение дня.\n"
        "Без отчётов и писанины.\n"
        "Просто на минуту ответь себе (можно молча):\n"
        "• что сегодня было хорошо?\n"
        "• что завтра хочется сделать проще?\n"
        "Спокойной ночи 🤍"
    )


# -----------------------
# КНОПКИ / CALLBACKS
# -----------------------
def kb(*rows: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    keyboard = []
    for row in rows:
        keyboard.append([InlineKeyboardButton(text=t, callback_data=d) for (t, d) in row])
    return InlineKeyboardMarkup(keyboard)


def day_key(tz: ZoneInfo) -> str:
    return datetime.now(tz).date().isoformat()


# -----------------------
# JOB HANDLERS
# -----------------------
async def job_morning(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = int(ctx.job.data["chat_id"])
    u = STORE.get_user(chat_id)
    tz = ZoneInfo(u.get("tz") or DEFAULT_TZ_NAME)

    dob_iso = u.get("dob")
    if not dob_iso:
        return

    plan = get_or_create_today_plan(chat_id, tz)
    await ctx.bot.send_message(
        chat_id=chat_id,
        text=morning_text(plan, dob_iso, tz),
        parse_mode=ParseMode.HTML,
        reply_markup=kb(
            [("✅ Принял", "ack_plan"), ("📌 Показать /today", "show_today")]
        ),
    )


async def job_noon(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = int(ctx.job.data["chat_id"])
    await ctx.bot.send_message(
        chat_id=chat_id,
        text=noon_text(),
        reply_markup=kb(
            [("✅ Уже сделал(а) что-то", "noon_done"), ("⏳ Пока нет", "noon_notyet")],
            [("🔥 Нужен пинок", "noon_push"), ("📌 Напомни план", "show_today")],
        ),
    )


async def job_afternoon(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = int(ctx.job.data["chat_id"])
    await ctx.bot.send_message(
        chat_id=chat_id,
        text=afternoon_text(),
        reply_markup=kb(
            [("✅ Да", "aft_yes"), ("🟡 Частично", "aft_partial"), ("⏳ Ещё нет", "aft_no")],
            [("📌 План /today", "show_today")],
        ),
    )


async def job_evening(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = int(ctx.job.data["chat_id"])
    await ctx.bot.send_message(
        chat_id=chat_id,
        text=evening_text(),
        reply_markup=kb(
            [("🏋️ Да, будет", "eve_workout_yes"), ("🧘 Лёгкая версия", "eve_workout_light"), ("😴 Отдых", "eve_workout_rest")],
        ),
    )


async def job_late(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = int(ctx.job.data["chat_id"])
    await ctx.bot.send_message(
        chat_id=chat_id,
        text=late_text(),
        reply_markup=kb(
            [("🌙 Закрыл день", "late_done"), ("📌 План /today", "show_today")],
        ),
    )


# -----------------------
# COMMANDS
# -----------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    u = STORE.get_user(chat_id)

    schedule_user(context.application, chat_id)

    if not u.get("dob"):
        await update.message.reply_text(
            header_text() + "\nОтправь дату рождения в формате ДД.ММ.ГГГГ (пример: 22.04.1983)."
        )
        return

    await update.message.reply_text(header_text())


async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    u = STORE.get_user(chat_id)
    tz = ZoneInfo(u.get("tz") or DEFAULT_TZ_NAME)

    if not u.get("dob"):
        await update.message.reply_text("Сначала отправь дату рождения в формате ДД.ММ.ГГГГ (пример: 22.04.1983).")
        return

    plan = get_or_create_today_plan(chat_id, tz)
    lived = days_lived(u["dob"], tz)

    await update.message.reply_text(
        f"📌 <b>План на сегодня</b>\n"
        f"Сегодня твой <b>{lived}-й</b> день жизни.\n\n"
        f"{format_plan(plan)}",
        parse_mode=ParseMode.HTML,
        reply_markup=kb([("✅ Ок", "ack_plan")]),
    )


async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    schedule_user(context.application, chat_id)
    await update.message.reply_text(
        "Настройки ✅\n"
        "Режим: Интенсив (5/день)\n"
        f"Таймзона: {DEFAULT_TZ_NAME}\n\n"
        "Я пересоздал расписание на твоём чате.\n"
        "Команда /today покажет план дня."
    )


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    STORE.set_user(chat_id, {"dob": None, "plans": {}, "progress": {}, "tz": DEFAULT_TZ_NAME})
    clear_user_jobs(context.application, chat_id)
    await update.message.reply_text("Сбросил данные. Отправь дату рождения в формате ДД.ММ.ГГГГ (пример: 22.04.1983).")


# -----------------------
# DATE INPUT
# -----------------------
def parse_dob(text: str) -> Optional[str]:
    m = DATE_RE.match(text)
    if not m:
        return None
    dd, mm, yyyy = map(int, m.groups())
    try:
        d = date(yyyy, mm, dd)
    except ValueError:
        return None
    return d.isoformat()


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    u = STORE.get_user(chat_id)

    txt = (update.message.text or "").strip()
    dob_iso = parse_dob(txt)
    if dob_iso:
        STORE.set_user(chat_id, {"dob": dob_iso, "tz": DEFAULT_TZ_NAME})
        schedule_user(context.application, chat_id)

        lived = days_lived(dob_iso, DEFAULT_TZ)
        plan = get_or_create_today_plan(chat_id, DEFAULT_TZ)

        await update.message.reply_text(
            f"Запомнил ✅ Сегодня твой <b>{lived}-й</b> день жизни.\n\n"
            "Идём как коуч и партнёр по дисциплине: спокойно, но регулярно.\n\n"
            "📌 Держи план на сегодня (он не исчезает — /today всегда покажет его снова):\n\n"
            f"{format_plan(plan)}",
            parse_mode=ParseMode.HTML,
            reply_markup=kb([("✅ Принял", "ack_plan"), ("📌 /today", "show_today")]),
        )
        return

    if u.get("dob"):
        await update.message.reply_text("Я рядом ✅ Если нужно — /today покажет план дня.")
    else:
        await update.message.reply_text("Отправь дату рождения в формате ДД.ММ.ГГГГ (пример: 22.04.1983).")


# -----------------------
# CALLBACKS
# -----------------------
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()

    chat_id = q.message.chat_id
    u = STORE.get_user(chat_id)
    tz = ZoneInfo(u.get("tz") or DEFAULT_TZ_NAME)
    dk = day_key(tz)

    data = q.data or ""

    if data == "show_today":
        plan = get_or_create_today_plan(chat_id, tz)
        lived = days_lived(u["dob"], tz) if u.get("dob") else None

        prefix = "📌 <b>План на сегодня</b>\n\n"
        if lived is not None:
            prefix = f"📌 <b>План на сегодня</b>\nСегодня твой <b>{lived}-й</b> день жизни.\n\n"

        await q.message.reply_text(
            prefix + format_plan(plan),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "ack_plan":
        STORE.set_progress(chat_id, dk, "plan_ack", True)
        await q.message.reply_text("✅ Принято. План остаётся доступным — в любой момент /today.")
        return

    if data.startswith("noon_"):
        STORE.set_progress(chat_id, dk, "noon", data)
        if data == "noon_done":
            await q.message.reply_text("🔥 Отлично. Закрепи это ощущение: ты уже двигаешься вперёд.")
        elif data == "noon_notyet":
            await q.message.reply_text("Ок. Тогда мини-шаг: выбери <b>одну</b> задачу и сделай 5 минут. Старт важнее идеала.", parse_mode=ParseMode.HTML)
        else:
            await q.message.reply_text("Пинок по-доброму: 10 минут таймер — и делай самое простое из плана. Поехали.")
        return

    if data.startswith("aft_"):
        STORE.set_progress(chat_id, dk, "afternoon", data)
        if data == "aft_yes":
            await q.message.reply_text("✅ Супер. Маленькая победа = реальный прогресс.")
        elif data == "aft_partial":
            await q.message.reply_text("🟡 Нормально. Частично — это тоже движение.")
        else:
            await q.message.reply_text("⏳ Ок. Тогда вечером сделаем «лёгкую версию» — 10 минут тоже считаются.")
        return

    if data.startswith("eve_workout_"):
        STORE.set_progress(chat_id, dk, "evening_workout", data)
        if data == "eve_workout_yes":
            await q.message.reply_text("🏋️ Отлично. Держи коротко: 10 минут — и ты молодец.")
        elif data == "eve_workout_light":
            await q.message.reply_text("🧘 Лёгкая версия — топ. Сделай 10 минут и остановись.")
        else:
            await q.message.reply_text("😴 Отдых — тоже часть дисциплины. Восстановление важно.")
        return

    if data == "late_done":
        STORE.set_progress(chat_id, dk, "late_done", True)
        await q.message.reply_text("🌙 Закрыто. Ты хорошо справился(лась). Спокойной ночи 🤍")
        return


# -----------------------
# ERROR HANDLER
# -----------------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled exception: %s", context.error)


# -----------------------
# MARKETPLACE-БОТ (маркетплейс-агент: Ozon/WB/Яндекс Маркет)
# -----------------------
# Второй, полностью независимый Telegram-бот в этом же процессе — свой
# токен (MARKET_BOT_TOKEN), свои команды, своя база (market/db.py на том
# же постоянном диске). Если что-то в этой части сломается — на
# daycountbot это никак не влияет, см. run_both() ниже.
from market.collect_and_notify import collect_and_notify, build_report_text, collect_for_date  # noqa: E402

MARKET_DAILY_TIME = time(9, 0, tzinfo=DEFAULT_TZ)


async def market_report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # update.effective_message (а не update.message!) — команда может прийти
    # не только из личного чата/группы, но и постом в канале
    # (update.channel_post). Для канала update.message всегда None, и
    # обращение к нему падало с AttributeError, а ошибка тихо уходила в
    # лог через on_error — снаружи выглядело как "бот не отвечает".
    message = update.effective_message
    target_date = datetime.now(DEFAULT_TZ).date() - timedelta(days=1)
    try:
        text = build_report_text(target_date)
    except Exception as exc:
        log.exception("Ошибка при построении отчёта по /report: %s", exc)
        text = "Не получилось построить отчёт — {}".format(exc)
    await message.reply_text(text)


async def market_collect_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ручной запуск сбора данных прямо сейчас (не ждать авто-отчёт в
    09:00). Полезно, чтобы сразу проверить, что площадка реально
    собирается, а не ждать до завтрашнего утра."""
    message = update.effective_message  # см. комментарий в market_report_cmd
    target_date = datetime.now(DEFAULT_TZ).date() - timedelta(days=1)
    await message.reply_text(
        "Собираю данные за {} по всем площадкам, подожди немного…".format(
            target_date.strftime("%d.%m.%Y")
        )
    )
    try:
        await asyncio.to_thread(collect_for_date, target_date)
    except Exception as exc:
        log.exception("Ошибка при ручном сборе данных (/collect): %s", exc)
        await message.reply_text("Не получилось собрать данные — {}".format(exc))
        return
    text = build_report_text(target_date)
    await message.reply_text(text)


async def market_daily_job(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = os.getenv("MARKET_CHAT_ID", "").strip()
    if not chat_id:
        log.warning("MARKET_CHAT_ID не задан — авто-отчёт по маркетплейсам не отправлен.")
        return
    try:
        await collect_and_notify(ctx.bot, chat_id)
    except Exception:
        log.exception("Ошибка в ежедневном сборе/отправке отчёта по маркетплейсам")


def build_market_app() -> Optional[Application]:
    token = os.getenv("MARKET_BOT_TOKEN", "").strip()
    if not token:
        log.warning(
            "MARKET_BOT_TOKEN не задан — бот отчётов по маркетплейсам не запущен "
            "(daycountbot при этом работает как обычно)."
        )
        return None

    market_app = Application.builder().token(token).build()
    market_app.add_handler(CommandHandler("report", market_report_cmd))
    market_app.add_handler(CommandHandler("collect", market_collect_cmd))
    market_app.add_error_handler(on_error)
    return market_app


# -----------------------
# MAIN
# -----------------------
async def post_init(app: Application) -> None:
    await schedule_all_users(app)
    log.info("Post-init done. Users scheduled: %d", len(STORE.all_chat_ids()))


async def _start_app(app: Application) -> bool:
    """Поднимает одно Application вручную (initialize -> post_init ->
    start_polling -> start) — тот же порядок, что и внутри run_polling(),
    но так можно запустить несколько ботов в одном процессе одновременно.
    Возвращает True при успехе; при ошибке логирует и возвращает False,
    не роняя весь процесс."""
    try:
        await app.initialize()
        if app.post_init:
            await app.post_init(app)
        await app.updater.start_polling(drop_pending_updates=True)
        await app.start()
        return True
    except Exception:
        log.exception("Не удалось запустить бота")
        return False


async def _stop_app(app: Application) -> None:
    try:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
    except Exception:
        log.exception("Ошибка при остановке бота")


async def run_both(app: Application, market_app: Optional[Application]) -> None:
    started: list[Application] = []

    ok = await _start_app(app)
    if not ok:
        # daycountbot — основной бот; если он не поднялся, продолжать нет смысла
        raise RuntimeError("daycountbot не запустился")
    started.append(app)

    if market_app is not None:
        market_ok = await _start_app(market_app)
        if market_ok:
            started.append(market_app)
            market_app.job_queue.run_daily(
                market_daily_job,
                time=MARKET_DAILY_TIME,
                name="market:daily_collect_and_notify",
            )
            log.info("Маркетплейс-бот запущен, авто-отчёт в 09:00 (Москва).")
        else:
            log.warning(
                "Маркетплейс-бот не запустился — daycountbot продолжает работать как обычно."
            )

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_stop(*_args: object) -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # На некоторых платформах обработчики сигналов через event loop
            # недоступны — тогда просто не ловим сигнал, процесс завершится
            # штатно по обычному завершению/SIGKILL.
            pass

    log.info("Запущено ботов: %d", len(started))
    await stop_event.wait()

    log.info("Останавливаюсь...")
    for a in started:
        await _stop_app(a)


def main() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("ENV BOT_TOKEN is required")

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("today", today_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    app.add_error_handler(on_error)

    market_app = build_market_app()

    log.info("%s starting…", BOT_NAME)
    asyncio.run(run_both(app, market_app))


if __name__ == "__main__":
    main()
