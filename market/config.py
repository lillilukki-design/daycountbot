# -*- coding: utf-8 -*-
"""
Ключи маркетплейсов — версия для Render.

В отличие от версии для ПК (файл ключи_маркетплейсов.txt), здесь всё
берётся из переменных окружения сервиса. Вписываются они в панели
Render: Dashboard -> daycountbot -> Environment -> Add Environment
Variable. Никогда не присылайте эти значения в чат Claude — вводите их
напрямую там, это ровно тот же принцип, что и с локальным файлом ключей.

Нужные переменные:
  OZON_CLIENT_ID, OZON_API_KEY       — Ozon Seller API
  WB_TOKEN                            — Wildberries Statistics API
  YANDEX_MARKET_TOKEN, YANDEX_CAMPAIGN_ID  — Яндекс Маркет Partner API
  MARKET_BOT_TOKEN                    — токен бота для /report и авто-сводки
  MARKET_CHAT_ID                      — куда слать авто-сводку (личный chat_id
                                         или @имя_канала для публичного канала)
  MARKET_DATA_DIR                     — путь на постоянном диске Render для
                                         базы данных (например /var/data/market)
"""
import os

REQUIRED_ENV_VARS = {
    "ozon": ["OZON_CLIENT_ID", "OZON_API_KEY"],
    "wb": ["WB_TOKEN"],
    "yandex": ["YANDEX_MARKET_TOKEN", "YANDEX_CAMPAIGN_ID"],
}

_CONFIG_KEYS = [
    "OZON_CLIENT_ID",
    "OZON_API_KEY",
    "WB_TOKEN",
    "YANDEX_MARKET_TOKEN",
    "YANDEX_CAMPAIGN_ID",
]


def load_config():
    """Читает ключи маркетплейсов из переменных окружения. Отсутствующие
    просто станут пустой строкой — какие именно нужны для конкретной
    площадки, проверяет check_config()."""
    return {key: os.getenv(key, "").strip() for key in _CONFIG_KEYS}


def check_config(config, marketplace):
    """Проверяет, что нужные для площадки переменные заполнены.
    Возвращает список отсутствующих (пустой список = всё в порядке)."""
    needed = REQUIRED_ENV_VARS[marketplace]
    return [key for key in needed if not config.get(key)]
