# -*- coding: utf-8 -*-
"""
Сбор данных о продажах с Wildberries — API Статистики.
Документация: https://openapi.wildberries.ru (раздел "Статистика").

Особенности, которые уже учтены:
- Токен передаётся в заголовке Authorization БЕЗ слова "Bearer".
- API отдаёт лимит примерно 1 запрос в минуту на метод — здесь дергаем
  всего один раз за запуск, так что это не проблема.
- Если WB поменяет формат ответа, сломается только эта функция —
  остальной код (база, отчёт) не пострадает.
"""
import json
import time

import requests

from .common import mock_orders, check_response

API_URL = "https://statistics-api.wildberries.ru/api/v1/supplier/sales"


def collect(config, date_from, date_to, mock=False):
    if mock:
        return mock_orders("wb", date_from, date_to, seed="wb")

    token = config["WB_TOKEN"]
    headers = {"Authorization": token}
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
        resp = requests.get(API_URL, headers=headers, params=params, timeout=60)
        if resp.status_code == 429 and attempt == 0:
            wait_seconds = int(resp.headers.get("X-Ratelimit-Retry", 65))
            if wait_seconds <= MAX_AUTO_WAIT:
                print("  (WB просит подождать из-за лимита запросов, жду {} сек...)".format(wait_seconds))
                time.sleep(wait_seconds)
                continue
            else:
                minutes = round(wait_seconds / 60)
                raise RuntimeError(
                    "Wildberries временно ограничил запросы — просит подождать "
                    "около {} мин. Обычно это проходит само; попробуйте собрать "
                    "данные позже (например, через час).".format(minutes)
                )
        break

    check_response(resp)
    raw_sales = resp.json()
    print("     (сырых записей от WB до фильтра по датам: {})".format(len(raw_sales)))
    if raw_sales:
        print("     [диагностика WB] первая запись: {}".format(
            json.dumps(raw_sales[0], ensure_ascii=False)[:400]))

    orders = []
    for sale in raw_sales:
        sale_date = (sale.get("date") or "")[:10]
        if sale_date < date_from.strftime("%Y-%m-%d") or sale_date > date_to.strftime("%Y-%m-%d"):
            continue

        sale_id = sale.get("saleID", "")
        is_return = str(sale_id).upper().startswith("R")
        price = sale.get("finishedPrice") or sale.get("priceWithDisc") or 0
        # "forPay" — это уже сумма к перечислению поставщику (после
        # комиссии WB и логистики), сама площадка отдаёт её прямо в этом
        # же ответе — отдельный финансовый отчёт не нужен.
        payout = sale.get("forPay")
        commission = round(price - payout, 2) if payout is not None else None

        orders.append(
            {
                "marketplace": "wb",
                "order_id": str(sale_id or sale.get("srid", "")),
                "date": sale_date,
                "sku": str(sale.get("nmId", "")),
                "product_name": sale.get("subject", ""),
                "quantity": 1,
                "price": price,
                "status": "возврат" if is_return else "продано",
                "commission": commission,
                "payout": payout,
            }
        )
    return orders
