# -*- coding: utf-8 -*-
"""
Сбор данных о заказах с Wildberries — API Статистики.
Документация: https://openapi.wildberries.ru (раздел "Статистика").

Основной сбор (collect(), см. ниже) идёт через /supplier/orders — все
оформленные заказы по дате оформления, так же, как считаются Ozon и
Яндекс: это активность покупателей, а не финансовый расчёт WB. Отдельно
есть collect_feed_summary() на /supplier/sales — для сверки, сколько из
этих заказов WB уже провёл как продажу и посчитал к выплате (/wbfeed).

Особенности, которые уже учтены:
- Токен передаётся в заголовке Authorization БЕЗ слова "Bearer".
- API отдаёт лимит примерно 1 запрос в минуту НА МЕТОД (то есть у
  /supplier/sales и /supplier/orders лимиты считаются раздельно).
- dateFrom у ОБОИХ методов фильтрует не по дате продажи/заказа, а по
  ДАТЕ ПОСЛЕДНЕГО ИЗМЕНЕНИЯ записи (lastChangeDate) — это официально
  задокументированное поведение WB. Поэтому дату продажи/заказа мы
  всё равно дополнительно проверяем сами после получения ответа.
- Если WB поменяет формат ответа, сломается только эта функция —
  остальной код (база, отчёт) не пострадает.
"""
import json
import logging
import time
from collections import Counter
from datetime import date, timedelta

import requests

from .common import mock_orders, check_response

log = logging.getLogger("market")

SALES_URL = "https://statistics-api.wildberries.ru/api/v1/supplier/sales"
ORDERS_URL = "https://statistics-api.wildberries.ru/api/v1/supplier/orders"

# Оставлено для обратной совместимости — старое имя константы.
API_URL = SALES_URL

# Установлено на практике (проверено логами 26.08): при dateFrom = начало
# месяца WB [заказы] вернул только 24 записи с датами 15–26 августа — то
# есть дальше 1 августа, как просили, он не заглянул, хотя по документации
# dateFrom фильтрует по lastChangeDate и должен отдавать всё "≥ dateFrom"
# одним ответом (до ~100 000 строк). Само по себе это не объясняется явно
# документированным поведением — либо WB на практике режет ответ по
# какому-то не задокументированному скользящему окну, либо у этого
# токена/аккаунта интеграция реально не видит более раннюю историю.
# Проверить это дёшево: всегда запрашивать WB от максимально далёкой
# разрешённой даты (90 дней хранения) и уже потом самим фильтровать на
# нужный период — если WB всё-таки способен отдать более раннее, это
# сразу же станет видно в логах и в отчёте; если нет — по крайней мере
# перестанем зависеть от того, насколько широкий диапазон запросил вызывающий
# код (для /today и /collect тут раньше не было запаса вообще).
MAX_LOOKBACK_DAYS = 89


def _query_from(date_from):
    """Дата, с которой реально стоит запрашивать WB — всегда настолько
    далеко назад, насколько WB вообще готов отдавать (предел хранения —
    90 дней), даже если вызывающему коду нужен более узкий период. Само
    сужение до нужного периода происходит потом, локальной фильтрацией
    по датам заказов. См. комментарий у MAX_LOOKBACK_DAYS."""
    earliest = date.today() - timedelta(days=MAX_LOOKBACK_DAYS)
    return min(date_from, earliest)


def _wb_get(url, headers, date_from, label):
    """Общий поход в любой из методов WB Статистики с обработкой лимита
    запросов (429) — вынесено в одну функцию, чтобы /supplier/sales и
    /supplier/orders не дублировали одну и ту же логику ожидания."""
    params = {"dateFrom": date_from.strftime("%Y-%m-%d")}

    # У этого метода WB лимит запросов. Если недавно уже дёргали его
    # несколько раз подряд (например, тестировали), сервер отвечает 429
    # и просит подождать — иногда всего минуту, а иногда (после нескольких
    # подряд 429) по многу часов. Ждать больше пары минут внутри скрипта
    # смысла нет — лучше сразу сказать об этом и не блокировать сбор
    # данных с Ozon и Яндекс Маркета.
    MAX_AUTO_WAIT = 90
    resp = None
    for attempt in range(2):
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        if resp.status_code == 429 and attempt == 0:
            wait_seconds = int(resp.headers.get("X-Ratelimit-Retry", 65))
            if wait_seconds <= MAX_AUTO_WAIT:
                log.info("WB (%s) просит подождать из-за лимита запросов, жду %s сек...",
                         label, wait_seconds)
                time.sleep(wait_seconds)
                continue
            else:
                minutes = round(wait_seconds / 60)
                raise RuntimeError(
                    "Wildberries временно ограничил запросы ({}) — просит подождать "
                    "около {} мин. Обычно это проходит само; попробуйте собрать "
                    "данные позже (например, через час).".format(label, minutes)
                )
        break

    check_response(resp)
    raw = resp.json()
    log.info("WB [%s]: сырых записей до фильтра по датам: %d (dateFrom=%s, запрос по %s)",
             label, len(raw), params["dateFrom"], url)
    if raw:
        log.info("WB [%s]: первая запись: %s",
                  label, json.dumps(raw[0], ensure_ascii=False)[:400])
        dates = sorted((r.get("date") or "")[:10] for r in raw)
        by_day = Counter(dates)
        log.info("WB [%s]: диапазон дат в сыром ответе: %s .. %s, записей по дням: %s",
                  label, dates[0], dates[-1], dict(sorted(by_day.items())))
    else:
        log.info("WB [%s]: ответ пустой (0 записей) для dateFrom=%s", label, params["dateFrom"])
    return raw


def collect(config, date_from, date_to, mock=False):
    """Основной сбор для /today, /collect, /month и утреннего авто-отчёта.

    Раньше здесь был /supplier/sales (только подтверждённые и уже
    рассчитанные WB продажи) — из-за этого WB в отчётах считался
    принципиально иначе, чем Ozon и Яндекс: те показывают АКТИВНОСТЬ
    покупателей (все оформленные заказы), а WB показывал скорость
    собственного финансового расчёта, которая может отставать от
    реального выкупа на дни. Сейчас источник — /supplier/orders: все
    заказы по дате оформления, как у остальных площадок. Отменённые
    (isCancel) помечаются как "возврат" и не идут в выручку — так же,
    как реальный возврат считается для остальных площадок.

    Если нужна именно финансовая сверка (сколько WB уже реально провёл
    как продажу и посчитал к выплате) — для этого отдельная функция
    collect_feed_summary() и команда /wbfeed, она осталась на
    /supplier/sales."""
    if mock:
        return mock_orders("wb", date_from, date_to, seed="wb")

    token = config["WB_TOKEN"]
    headers = {"Authorization": token}
    raw_orders = _wb_get(ORDERS_URL, headers, _query_from(date_from), "заказы")

    date_from_s = date_from.strftime("%Y-%m-%d")
    date_to_s = date_to.strftime("%Y-%m-%d")

    orders = []
    for raw in raw_orders:
        order_date = (raw.get("date") or "")[:10]
        if order_date < date_from_s or order_date > date_to_s:
            continue

        is_cancel = bool(raw.get("isCancel"))
        price = raw.get("priceWithDisc")
        if price is None:
            price = raw.get("totalPrice") or 0

        # У WB в этом методе нет отдельного поля с полным названием товара
        # (как у Ozon/Яндекса) — "subject" это категория ("Благовония",
        # "Топы"...), а не конкретная модель. Чтобы в отчёте не сливались в
        # одну строку все разные товары одной категории, добавляем к
        # категории бренд и артикул продавца (то, что сам продавец задавал
        # при загрузке товара на WB) — этого достаточно, чтобы отличить
        # один товар от другого, не выдумывая название, которого WB не даёт.
        subject = raw.get("subject") or ""
        brand = raw.get("brand") or ""
        supplier_article = raw.get("supplierArticle") or ""
        name_parts = [p for p in (subject, brand) if p]
        if supplier_article:
            name_parts.append("арт. {}".format(supplier_article))
        product_name = ", ".join(name_parts) if name_parts else subject

        orders.append(
            {
                "marketplace": "wb",
                "order_id": str(raw.get("srid") or raw.get("odid") or raw.get("gNumber") or ""),
                "date": order_date,
                "sku": str(raw.get("nmId", "")),
                "product_name": product_name,
                "quantity": 1,
                "price": price,
                "status": "возврат" if is_cancel else "заказ",
                # На стадии "заказ оформлен" WB ещё не считает комиссию и
                # выплату — это появляется только после /supplier/sales
                # (см. collect_feed_summary), поэтому здесь честно пусто,
                # а не придуманный ноль.
                "commission": None,
                "payout": None,
            }
        )
    return orders


def collect_feed_summary(config, date_from, date_to):
    """Сводка по 'ленте заказов' WB за период, посчитанная через API —
    аналог бесплатного отчёта в кабинете WB (Создан/Выкуплен/Отказ), но
    без ручной выгрузки Excel. Логика:

    - /supplier/orders даёт ВСЕ заказы за период (сколько бы их ни было
      выкуплено, отменено или ещё не обработано) и явный флаг isCancel
      для отказов/отмен.
    - /supplier/sales даёт только те заказы, которые WB уже полностью
      провёл как продажу (посчитан forPay к выплате). Не все выкупленные
      заказы сразу попадают сюда — расчёт может занять время уже после
      физического выкупа, отсюда и разница с "Выкуплен" в кабинете.

    Заказ, которого нет среди отмен и нет среди рассчитанных продаж,
    считаем "в процессе" (either ещё не выкуплен, либо выкуплен, но WB
    ещё не провёл по нему финансовый расчёт) — это и есть основной
    источник расхождения между /month и кабинетом WB."""
    token = config["WB_TOKEN"]
    headers = {"Authorization": token}

    date_from_s = date_from.strftime("%Y-%m-%d")
    date_to_s = date_to.strftime("%Y-%m-%d")

    def in_range(raw_date):
        d = (raw_date or "")[:10]
        return date_from_s <= d <= date_to_s

    query_from = _query_from(date_from)
    raw_orders = _wb_get(ORDERS_URL, headers, query_from, "заказы")
    raw_sales = _wb_get(SALES_URL, headers, query_from, "продажи")

    orders = [o for o in raw_orders if in_range(o.get("date"))]
    # srid — сквозной идентификатор заказа, общий у /orders и /sales
    # (так их и предлагает сверять сама WB) — по нему сопоставляем, стал
    # ли конкретный заказ уже рассчитанной продажей.
    settled_srids = {s.get("srid") for s in raw_sales if in_range(s.get("date")) and s.get("srid")}

    def price_of(o):
        return float(o.get("priceWithDisc") or o.get("totalPrice") or 0)

    cancelled = [o for o in orders if o.get("isCancel")]
    active_orders = [o for o in orders if not o.get("isCancel")]
    settled = [o for o in active_orders if o.get("srid") in settled_srids]
    pending = [o for o in active_orders if o.get("srid") not in settled_srids]

    def summarize(lst):
        return {"count": len(lst), "sum": round(sum(price_of(o) for o in lst), 2)}

    return {
        "total": summarize(orders),
        "cancelled": summarize(cancelled),
        "settled": summarize(settled),
        "pending": summarize(pending),
    }
