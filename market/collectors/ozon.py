# -*- coding: utf-8 -*-
"""
Сбор данных о заказах с Ozon Seller API.
Документация: https://docs.ozon.ru/api/seller/

Забираем отправления по обеим схемам продажи — FBO (склад Ozon) и
FBS (свой склад/сборка), потому что заранее не знаем, какую из них
вы используете (можно и обе сразу). Если по одной из схем всегда
будет 0 записей — скорее всего вы просто ей не пользуетесь, это не
ошибка.
"""
import requests

from .common import mock_orders, check_response, msk_day_bounds_utc, to_msk_date

FBO_URL = "https://api-seller.ozon.ru/v3/posting/fbo/list"
FBS_URL = "https://api-seller.ozon.ru/v3/posting/fbs/list"


def _fetch_postings(url, headers, since, to):
    postings = []
    offset = 0
    limit = 100  # у Ozon для этих методов лимит строго от 1 до 100
    while True:
        body = {
            "dir": "ASC",
            "filter": {"since": since, "to": to},
            "limit": limit,
            "offset": offset,
            "with": {"financial_data": True},
        }
        resp = requests.post(url, headers=headers, json=body, timeout=60)
        check_response(resp)
        data = resp.json()
        # У FBS ответ обёрнут в {"result": {...}}, а у FBO — postings
        # лежит прямо в корне ответа, без обёртки "result". Обрабатываем
        # оба варианта одним кодом.
        result = data.get("result", data) if isinstance(data, dict) else {}
        batch = result.get("postings", []) if isinstance(result, dict) else []
        postings.extend(batch)
        # Ozon явно говорит, есть ли ещё страницы — так надёжнее, чем
        # угадывать по количеству полученных записей.
        if not result.get("has_next") or not batch:
            break
        offset += limit
    return postings


def _extract_price(product):
    """У FBO цена приходит вложенным объектом {"amount": "1500", ...},
    а у FBS — просто строкой "1500.0000". Обрабатываем оба варианта."""
    price = product.get("price", 0)
    if isinstance(price, dict):
        price = price.get("amount", 0)
    try:
        return float(price or 0)
    except (TypeError, ValueError):
        return 0.0


def _to_float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _extract_commission_payout(fin_item):
    """Из строки financial_data.products[] достаём комиссию и выплату.
    У FBS комиссия обычно лежит в плоском поле commission_amount, у FBO
    иногда приходит вложенным объектом commission: {"amount": ...} —
    обрабатываем оба варианта, как и с ценой."""
    payout = _to_float(fin_item.get("payout"))
    commission = _to_float(fin_item.get("commission_amount"))
    if commission is None:
        commission_obj = fin_item.get("commission")
        if isinstance(commission_obj, dict):
            commission = _to_float(commission_obj.get("amount"))
    return commission, payout


def collect(config, date_from, date_to, mock=False):
    if mock:
        return mock_orders("ozon", date_from, date_to, seed="ozon")

    headers = {
        "Client-Id": config["OZON_CLIENT_ID"],
        "Api-Key": config["OZON_API_KEY"],
        "Content-Type": "application/json",
    }

    # Ozon принимает since/to строго в UTC, а личный кабинет считает
    # сутки по московскому времени — если просто взять дату и приписать
    # "T00:00:00.000Z", то московская полночь окажется не той же самой
    # точкой времени, что UTC-полночь, и часть заказов у границы суток
    # потеряется или задвоится. Переводим границы дат через МСК.
    since_utc, _ = msk_day_bounds_utc(date_from)
    _, to_utc = msk_day_bounds_utc(date_to)
    since = since_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    to = to_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    fbo_postings = _fetch_postings(FBO_URL, headers, since, to)
    fbs_postings = _fetch_postings(FBS_URL, headers, since, to)
    print("     (по схеме FBO: {} отправлений, по схеме FBS: {} отправлений)".format(
        len(fbo_postings), len(fbs_postings)))

    orders = []
    for scheme, postings in (("fbo", fbo_postings), ("fbs", fbs_postings)):
        for posting in postings:
            order_id = "{}:{}".format(scheme, posting.get("posting_number", ""))
            status = posting.get("status", "")
            # in_process_at приходит в UTC — переводим в московскую дату,
            # чтобы день заказа совпадал с тем, что показывает кабинет Ozon.
            order_date = to_msk_date(posting.get("in_process_at"))

            products = posting.get("products", [])
            financial_products = (posting.get("financial_data") or {}).get("products", [])
            # Финансовые строки обычно идут в том же порядке и в том же
            # количестве, что и товары отправления — сопоставляем по
            # позиции. Если количество вдруг не совпало, лучше оставить
            # комиссию/выплату пустыми, чем приписать их не тому товару.
            fin_rows = financial_products if len(financial_products) == len(products) else []

            for idx, product in enumerate(products):
                commission = payout = None
                if idx < len(fin_rows):
                    commission, payout = _extract_commission_payout(fin_rows[idx])
                orders.append(
                    {
                        "marketplace": "ozon",
                        "order_id": order_id,
                        "date": order_date,
                        "sku": str(product.get("sku", "")),
                        "product_name": product.get("name", ""),
                        "quantity": product.get("quantity", 1),
                        "price": _extract_price(product),
                        "status": status,
                        "commission": commission,
                        "payout": payout,
                    }
                )

    return orders
