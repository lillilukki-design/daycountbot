# -*- coding: utf-8 -*-
"""
Хранилище данных маркетплейс-бота — тот же SQLite, что и в версии для
ПК, но путь берётся из переменной окружения MARKET_DATA_DIR, которая
должна указывать на постоянный диск Render (иначе при каждом
передеплое данные будут стираться вместе с временным диском сервиса).
"""
import os
import sqlite3


def _data_dir():
    d = os.getenv("MARKET_DATA_DIR", "").strip()
    return d or "./market_data"


DATA_DIR = _data_dir()
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "market_data.sqlite3")

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marketplace TEXT NOT NULL,
    order_id TEXT NOT NULL,
    date TEXT NOT NULL,
    sku TEXT,
    product_name TEXT,
    quantity INTEGER,
    price REAL,
    status TEXT,
    commission REAL,
    payout REAL,
    collected_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(marketplace, order_id, sku)
);

CREATE TABLE IF NOT EXISTS collection_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marketplace TEXT NOT NULL,
    run_at TEXT DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL,
    message TEXT,
    rows_saved INTEGER DEFAULT 0
);
"""


def _migrate(conn):
    existing = [row[1] for row in conn.execute("PRAGMA table_info(orders)").fetchall()]
    for column in ("commission", "payout"):
        if column not in existing:
            conn.execute("ALTER TABLE orders ADD COLUMN {} REAL".format(column))

    # Раньше WB собирался через /supplier/sales (только подтверждённые и
    # уже рассчитанные продажи) — это давало другую картину, чем Ozon и
    # Яндекс, которые считают все ОФОРМЛЕННЫЕ заказы. Перешли на
    # /supplier/orders, чтобы WB считался так же, как остальные площадки
    # (активность покупателей, а не скорость финансового расчёта WB).
    # У новых записей другой формат order_id (srid вместо saleID), поэтому
    # старые WB-строки не перезапишутся сами — без явной чистки они бы
    # задвоили цифры в отчётах. Выполняется один раз.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS migrations "
        "(name TEXT PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    applied = conn.execute(
        "SELECT 1 FROM migrations WHERE name = ?", ("wb_orders_not_sales",)
    ).fetchone()
    if not applied:
        conn.execute("DELETE FROM orders WHERE marketplace = 'wb'")
        conn.execute("INSERT INTO migrations (name) VALUES (?)", ("wb_orders_not_sales",))

    conn.commit()


def get_connection(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def save_orders(orders, db_path=DB_PATH):
    if not orders:
        return 0
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT OR REPLACE INTO orders
            (marketplace, order_id, date, sku, product_name, quantity, price, status, commission, payout)
        VALUES
            (:marketplace, :order_id, :date, :sku, :product_name, :quantity, :price, :status,
             :commission, :payout)
        """,
        [dict(o, commission=o.get("commission"), payout=o.get("payout")) for o in orders],
    )
    conn.commit()
    saved = cur.rowcount
    conn.close()
    return saved


def log_run(marketplace, status, message="", rows_saved=0, db_path=DB_PATH):
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO collection_log (marketplace, status, message, rows_saved) VALUES (?, ?, ?, ?)",
        (marketplace, status, message, rows_saved),
    )
    conn.commit()
    conn.close()


def fetch_last_runs(db_path=DB_PATH):
    conn = get_connection(db_path)
    rows = conn.execute(
        """
        SELECT marketplace, status, message, run_at
        FROM collection_log
        WHERE id IN (SELECT MAX(id) FROM collection_log GROUP BY marketplace)
        """
    ).fetchall()
    conn.close()
    return {row[0]: {"status": row[1], "message": row[2], "run_at": row[3]} for row in rows}


def fetch_orders_df(db_path=DB_PATH):
    import pandas as pd

    conn = get_connection(db_path)
    df = pd.read_sql_query("SELECT * FROM orders", conn)
    conn.close()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df
