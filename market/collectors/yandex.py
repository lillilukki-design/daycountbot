# -*- coding: utf-8 -*-
"""
Сбор данных о заказах с Яндекс Маркета — Partner API.
Документация: https://yandex.ru/dev/market/partner-api/doc/ru/reference/orders/getOrders

Нужен не только ключ, но и ID кампании (campaignId) — это НЕ Business ID
кабинета, а ID конкретного магазина/схемы продаж (видно в кабинете в
разделе "Интеграции магазинов", колонка Campaign ID). Если у вас
несколько схем (например FBS и FBY) — впишите оба ID через запятую:
YANDEX_CAMPAIGN_ID=86487209,148752308

Важно: заголовок авторизации называется "Api-Key" (а не "Authorization") —
ключ, который выдаётся в кабинете, это не классический OAuth-токен.
"""
from datetime import datetime

import requests

from .common import mock_orders, check_response

API_URL_TEMPLATE = "https://api.partner.market.yandex.ru/v2/campaigns/{campaign_id}/orders"


def _to_iso_date(creation_date):
    """creationDate приходит как 'ДД-ММ-ГГГГ ЧЧ:мм:сс' — переводим в
    обычный 'ГГГГ-ММ-ДД', чтобы дальше по коду даты сравнивались верно."""
    if not creation_date:
        return ""
    try:
        return datetime.strptime(creation_date.split(" ")[0], "%d-%m-%Y").strftime("%Y-%m-%d")
    except ValueError:
        return creation_date[:10]


def _collect_for_campaign(token, campaign_id, date_from, date_to):
    headers = {"Api-Key": token}
    url = API_URL_TEMPLATE.format(campaign_id=campaign_id)

    orders = []
    page_token = None
    while True:
        params = {
            "fromDate": date_from.strftime("%d-%m-%Y"),
            "toDate": date_to.strftime("%d-%m-%Y"),
            "limit": 50,
        }
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(url, headers=headers, params=params, timeout=60)
        check_response(resp)
        data = resp.json()
        page_orders = data.get("orders", [])
        if not page_orders:
            break

        for order in page_orders:
            order_id = str(order.get("id", ""))
            status = order.get("status", "")
            order_date = _to_iso_date(order.get("creationDate", ""))
            for item in order.get("items", []):
                orders.append(
                    {
                        "marketplace": "yandex",
                        "order_id": order_id,
                        "date": order_date,
                        "sku": str(item.get("offerId", "")),
                        "product_name": item.get("offerName", ""),
                        "quantity": item.get("count", 1),
                        "price": float(item.get("price", 0) or 0),
                        "status": status,
                        # Список заказов Яндекс Маркета не отдаёт комиссию
                        # и выплату по строке напрямую (в отличие от WB и
                        # Ozon) — для этого нужен отдельный финансовый
                        # отчёт, что выходит за рамки "быстрой оценки".
                        # Оставляем пустым — в отчёте это будет видно как
                        # "нет данных", а не как ноль.
                        "commission": None,
                        "payout": None,
                    }
                )

        page_token = (data.get("paging") or {}).get("nextPageToken")
        if not page_token:
            break

    return orders


def collect(config, date_from, date_to, mock=False):
    if mock:
        return mock_orders("yandex", date_from, date_to, seed="yandex")

    token = config["YANDEX_MARKET_TOKEN"]
    campaign_ids = [c.strip() for c in config["YANDEX_CAMPAIGN_ID"].split(",") if c.strip()]

    orders = []
    for campaign_id in campaign_ids:
        orders += _collect_for_campaign(token, campaign_id, date_from, date_to)
    return orders
