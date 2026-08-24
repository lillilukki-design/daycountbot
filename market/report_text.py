# -*- coding: utf-8 -*-
"""
Текст ежедневной сводки по маркетплейсам — общая логика для авто-отчёта
(рассылка в 09:00 по расписанию) и команды /report (мгновенный ответ из
уже собранных данных). Здесь нет ни обращений к API площадок, ни к
Telegram — только сборка текста из уже готовой таблицы заказов.
"""
MARKETPLACE_LABELS = {"wb": "Wildberries", "ozon": "Ozon", "yandex": "Яндекс Маркет"}

# Порядок вывода площадок — фиксированный, чтобы всегда были видны все
# три, даже если у какой-то из них 0 продаж за день (иначе не отличить
# "правда ноль" от "сбор данных не отработал").
ORDERED_MARKETPLACES = ["ozon", "wb", "yandex"]

TOP_PRODUCTS_LIMIT = 10
TELEGRAM_MAX_LEN = 4096


def _money(value):
    return "{:,.0f} ₽".format(value or 0).replace(",", " ")


def build_daily_message(df, target_date, last_runs=None):
    """Строит текст сообщения по данным за один день (target_date —
    объект date). df — вся таблица заказов (db.fetch_orders_df()).
    last_runs — результат db.fetch_last_runs(), нужен только чтобы
    подсказать, если 0 заказов у площадки — это ошибка сбора, а не
    реальное отсутствие продаж."""
    last_runs = last_runs or {}
    day_str = target_date.strftime("%d.%m.%Y")

    day_df = df[df["date"].dt.date == target_date].copy() if not df.empty else df

    sold = day_df[day_df["status"] != "возврат"].copy()
    returns = day_df[day_df["status"] == "возврат"] if not day_df.empty else day_df
    sold["revenue"] = sold["price"] * sold["quantity"]
    total_revenue = sold["revenue"].sum()

    lines = ["📊 Отчёт за {}".format(day_str), ""]
    lines.append("Суммарная выручка: {}".format(_money(total_revenue)))
    lines.append("Продано позиций: {} шт.".format(int(sold["quantity"].sum()) if not sold.empty else 0))
    if not returns.empty:
        lines.append("Возвратов: {} шт.".format(len(returns)))

    lines.append("")
    lines.append("По площадкам:")
    for mp in ORDERED_MARKETPLACES:
        mp_sold = sold[sold["marketplace"] == mp] if not sold.empty else sold
        rev = mp_sold["revenue"].sum() if not mp_sold.empty else 0
        qty = int(mp_sold["quantity"].sum()) if not mp_sold.empty else 0
        line = "  • {}: {} ({} шт.)".format(MARKETPLACE_LABELS.get(mp, mp), _money(rev), qty)
        if qty == 0:
            last_run = last_runs.get(mp)
            if last_run and last_run.get("status") != "ok":
                line += "  ⚠ сбор данных: {}{}".format(
                    last_run.get("status"),
                    " — " + last_run["message"] if last_run.get("message") else "")
            elif not last_run:
                line += "  ⚠ сбор данных ещё ни разу не запускался"
        lines.append(line)

    top_products = (
        sold.groupby("product_name")
        .agg(qty=("quantity", "sum"), revenue=("revenue", "sum"))
        .sort_values("revenue", ascending=False)
        .head(TOP_PRODUCTS_LIMIT)
    )
    if not top_products.empty:
        lines.append("")
        lines.append("Топ товаров за день:")
        for name, row in top_products.iterrows():
            lines.append("  • {} — {} шт., {}".format(name, int(row["qty"]), _money(row["revenue"])))

    text = "\n".join(lines)
    if len(text) > TELEGRAM_MAX_LEN:
        text = text[: TELEGRAM_MAX_LEN - 50] + "\n\n(отчёт обрезан — слишком длинный)"
    return text
