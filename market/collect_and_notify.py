# -*- coding: utf-8 -*-
"""
Ежедневный сбор данных с маркетплейсов и рассылка сводки — версия для
работы внутри Render-бота. В отличие от версии для ПК, это не отдельный
скрипт, который запускают и закрывают, а функция, которую бот вызывает
сам изнутри своего расписания (в 09:00 по Москве) или вручную.

Ошибка на одной площадке не останавливает сбор по остальным — как и в
версии для ПК: пользователю нужны данные хотя бы по тем площадкам,
которые сработали, а не полный отказ из-за одной проблемной.
"""
import asyncio
import logging
from datetime import date, timedelta

from .config import load_config, check_config
from .db import save_orders, log_run, fetch_orders_df, fetch_last_runs
from .collectors import wb, ozon, yandex
from .report_text import build_daily_message, build_range_message

log = logging.getLogger("market")

MARKETPLACES = {
    "ozon": ("Ozon", ozon),
    "yandex": ("Яндекс Маркет", yandex),
    "wb": ("Wildberries", wb),
}


def collect_for_range(date_from, date_to):
    """Собирает данные за диапазон дат (date_from..date_to включительно)
    со всех площадок и складывает их в базу. Для одного дня date_from ==
    date_to — этим пользуется collect_for_date(). Возвращает True, если
    хотя бы одна площадка собралась без ошибки."""
    config = load_config()
    any_ok = False

    for code, (label, module) in MARKETPLACES.items():
        missing = check_config(config, code)
        if missing:
            msg = "не заполнены переменные окружения: {}".format(", ".join(missing))
            log.info("[%s] пропущено — %s", label, msg)
            log_run(code, "skipped", msg)
            continue

        try:
            log.info("[%s] начинаю сбор за %s..%s", label, date_from, date_to)
            orders = module.collect(config, date_from, date_to)
            log.info("[%s] сбор завершён, получено записей: %d", label, len(orders))
            saved = save_orders(orders)
            log.info("[%s] получено записей: %d, сохранено: %d", label, len(orders), saved)
            log_run(code, "ok", "", saved)
            any_ok = True
        except Exception as exc:  # намеренно широкий except — ошибка одной
            # площадки не должна останавливать сбор по остальным
            log.exception("[%s] ошибка сбора: %s", label, exc)
            log_run(code, "error", str(exc))

    return any_ok


def collect_for_date(target_date):
    """Собирает данные за один день (target_date) со всех площадок."""
    return collect_for_range(target_date, target_date)


def build_report_text(target_date):
    """Строит текст сводки за указанный день из уже собранных данных
    (без обращения к API площадок)."""
    df = fetch_orders_df()
    last_runs = fetch_last_runs()
    return build_daily_message(df, target_date, last_runs=last_runs)


def build_report_text_for_range(date_from, date_to, period_label=None):
    """Строит текст сводки за диапазон дат (например, с начала месяца по
    сегодня) из уже собранных данных (без обращения к API площадок)."""
    df = fetch_orders_df()
    last_runs = fetch_last_runs()
    return build_range_message(
        df, date_from, date_to, last_runs=last_runs, period_label=period_label
    )


async def collect_and_notify(bot, chat_id, target_date=None):
    """Собирает данные за вчера (по умолчанию) и присылает сводку в Telegram.
    bot — telegram.Bot соответствующего приложения.

    collect_for_date() делает обычные синхронные HTTP-запросы (requests),
    поэтому запускаем её в отдельном потоке через asyncio.to_thread —
    иначе на время сбора (несколько секунд на 3 площадки) завис бы общий
    event loop, а вместе с ним и второй бот (daycountbot) в этом же
    процессе."""
    target_date = target_date or (date.today() - timedelta(days=1))
    await asyncio.to_thread(collect_for_date, target_date)
    text = build_report_text(target_date)
    await bot.send_message(chat_id=chat_id, text=text)
