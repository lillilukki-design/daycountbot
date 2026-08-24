# -*- coding: utf-8 -*-
"""Общие мелочи для всех коллекторов."""
import random
from datetime import datetime, timedelta, timezone


class ApiError(Exception):
    """Ошибка ответа площадки — с текстом, который она прислала, чтобы
    было понятно, что именно не понравилось серверу, а не только код."""


def check_response(resp):
    """Вместо resp.raise_for_status() — показывает тело ответа сервера,
    там обычно и написана настоящая причина (неверный токен, нет прав,
    неверный формат запроса и т.д.)."""
    if resp.status_code >= 400:
        body = (resp.text or "").strip()
        if len(body) > 600:
            body = body[:600] + "..."
        raise ApiError("HTTP {} {} — ответ сервера: {}".format(resp.status_code, resp.reason, body))


# Личные кабинеты площадок считают "сутки" по московскому времени, а API
# некоторых из них (например Ozon) отдаёт и принимает время в UTC. Москва
# с 2014 года не переходит на летнее/зимнее время, поэтому фиксированное
# смещение UTC+3 надёжнее, чем тянуть базу часовых поясов (на Windows для
# неё нужен отдельный пакет tzdata, который стоит не у всех).
MSK = timezone(timedelta(hours=3))


def to_msk_date(iso_str):
    """Переводит ISO-timestamp (обычно UTC, с 'Z' на конце) в календарную
    дату по московскому времени. Без этого пересчёта заказы у границы
    полуночи попадают не в тот день, чем в личном кабинете площадки."""
    if not iso_str:
        return ""
    text = iso_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return iso_str[:10]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(MSK).strftime("%Y-%m-%d")


def msk_day_bounds_utc(target_date):
    """Начало и конец суток target_date по московскому времени, в UTC —
    для API, которые просят диапазон дат именно в UTC (например Ozon)."""
    start_msk = datetime(target_date.year, target_date.month, target_date.day, tzinfo=MSK)
    end_msk = start_msk + timedelta(days=1)
    return start_msk.astimezone(timezone.utc), end_msk.astimezone(timezone.utc)


SAMPLE_PRODUCTS = [
    ("Термокружка 350мл", "TC-350"),
    ("Чехол для телефона силикон", "CH-SIL-01"),
    ("Наушники беспроводные", "NB-X2"),
    ("Органайзер для кабелей", "ORG-CBL"),
    ("Коврик для мыши XL", "MAT-XL"),
]


def mock_orders(marketplace, date_from, date_to, seed):
    """Генерирует правдоподобные тестовые заказы — нужно только чтобы
    проверить, что вся цепочка (сбор -> база -> отчёт) работает,
    пока нет доступа к реальным ключам."""
    rnd = random.Random(seed)
    orders = []
    days = (date_to - date_from).days + 1
    for day_offset in range(days):
        day = date_from + timedelta(days=day_offset)
        for _ in range(rnd.randint(1, 5)):
            name, sku = rnd.choice(SAMPLE_PRODUCTS)
            orders.append(
                {
                    "marketplace": marketplace,
                    "order_id": "{}-{}-{}".format(marketplace, day.strftime("%Y%m%d"), rnd.randint(1000, 9999)),
                    "date": day.strftime("%Y-%m-%d"),
                    "sku": sku,
                    "product_name": name,
                    "quantity": rnd.randint(1, 3),
                    "price": round(rnd.uniform(400, 3500), 2),
                    "status": rnd.choice(["продано", "продано", "продано", "возврат"]),
                    "commission": None,
                    "payout": None,
                }
            )
    return orders
