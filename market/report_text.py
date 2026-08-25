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


def _build_message(period_df, header_line, last_runs=None, top_label="Топ товаров"):
    """Общее ядро сборки текста отчёта — принимает уже отфильтрованный по
    периоду (один день или диапазон дат) кусок таблицы заказов и первую
    строку заголовка. Используется и build_daily_message (один день), и
    build_range_message (диапазон, например с начала месяца)."""
    last_runs = last_runs or {}

    sold = period_df[period_df["status"] != "возврат"].copy()
    returns = period_df[period_df["status"] == "возврат"] if not period_df.empty else period_df
    sold["revenue"] = sold["price"] * sold["quantity"]
    total_revenue = sold["revenue"].sum()

    lines = [header_line, ""]
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
        lines.append("{}:".format(top_label))
        for name, row in top_products.iterrows():
            lines.append("  • {} — {} шт., {}".format(name, int(row["qty"]), _money(row["revenue"])))

    text = "\n".join(lines)
    if len(text) > TELEGRAM_MAX_LEN:
        text = text[: TELEGRAM_MAX_LEN - 50] + "\n\n(отчёт обрезан — слишком длинный)"
    return text


def build_daily_message(df, target_date, last_runs=None):
    """Строит текст сообщения по данным за один день (target_date —
    объект date). df — вся таблица заказов (db.fetch_orders_df()).
    last_runs — результат db.fetch_last_runs(), нужен только чтобы
    подсказать, если 0 заказов у площадки — это ошибка сбора, а не
    реальное отсутствие продаж."""
    day_df = df[df["date"].dt.date == target_date].copy() if not df.empty else df
    header = "📊 Отчёт за {}".format(target_date.strftime("%d.%m.%Y"))
    return _build_message(day_df, header, last_runs=last_runs, top_label="Топ товаров за день")


def build_range_message(df, date_from, date_to, last_runs=None, period_label=None):
    """То же самое, но за диапазон дат (например, с начала месяца по
    сегодня) — используется командой /month. period_label, если задан,
    подставляется в заголовок вместо дат (например, "август 2026")."""
    if not df.empty:
        range_df = df[(df["date"].dt.date >= date_from) & (df["date"].dt.date <= date_to)].copy()
    else:
        range_df = df
    if period_label:
        header = "📊 Отчёт {}".format(period_label)
    else:
        header = "📊 Отчёт с {} по {}".format(
            date_from.strftime("%d.%m.%Y"), date_to.strftime("%d.%m.%Y")
        )
    return _build_message(range_df, header, last_runs=last_runs, top_label="Топ товаров за период")
