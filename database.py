import os
import psycopg2
import psycopg2.extras
from datetime import date, timedelta
from typing import List, Dict, Optional
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL")

DEFAULT_EXPENSE_CATEGORIES = [
    ("Еда и продукты", "🍔"),
    ("Транспорт", "🚗"),
    ("Коммунальные услуги", "💡"),
    ("Здоровье", "💊"),
    ("Одежда", "👗"),
    ("Развлечения", "🎮"),
    ("Связь", "📱"),
    ("Зарплата сотрудников", "👥"),
    ("Закупка товаров", "📦"),
    ("Прочее", "📌"),
]

DEFAULT_INCOME_CATEGORIES = [
    ("Продажи", "💰"),
    ("Зарплата", "💵"),
    ("Инвестиции", "📈"),
    ("Прочий доход", "✨"),
]


class Database:
    def __init__(self):
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id BIGINT PRIMARY KEY,
                        created_at TIMESTAMP DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS accounts (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL REFERENCES users(id),
                        name TEXT NOT NULL,
                        balance NUMERIC(15,2) DEFAULT 0,
                        created_at TIMESTAMP DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS categories (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL REFERENCES users(id),
                        name TEXT NOT NULL,
                        emoji TEXT DEFAULT '📦',
                        type TEXT NOT NULL CHECK(type IN ('income','expense'))
                    );

                    CREATE TABLE IF NOT EXISTS transactions (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL REFERENCES users(id),
                        type TEXT NOT NULL CHECK(type IN ('income','expense','transfer')),
                        account_id INTEGER NOT NULL REFERENCES accounts(id),
                        amount NUMERIC(15,2) NOT NULL,
                        category_id INTEGER REFERENCES categories(id),
                        note TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                """)

    # ── Users ──────────────────────────────────────────────────

    def ensure_user(self, user_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (user_id,)
                )
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM categories WHERE user_id=%s",
                    (user_id,)
                )
                count = cur.fetchone()['cnt']
                if count == 0:
                    for name, emoji in DEFAULT_EXPENSE_CATEGORIES:
                        cur.execute(
                            "INSERT INTO categories (user_id, name, emoji, type) VALUES (%s,%s,%s,'expense')",
                            (user_id, name, emoji)
                        )
                    for name, emoji in DEFAULT_INCOME_CATEGORIES:
                        cur.execute(
                            "INSERT INTO categories (user_id, name, emoji, type) VALUES (%s,%s,%s,'income')",
                            (user_id, name, emoji)
                        )

    # ── Accounts ───────────────────────────────────────────────

    def add_account(self, user_id: int, name: str, balance: float = 0) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO accounts (user_id, name, balance) VALUES (%s,%s,%s) RETURNING id",
                    (user_id, name, balance)
                )
                return cur.fetchone()['id']

    def get_accounts(self, user_id: int) -> List[Dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM accounts WHERE user_id=%s ORDER BY id",
                    (user_id,)
                )
                return [dict(r) for r in cur.fetchall()]

    def get_account(self, account_id: int) -> Optional[Dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM accounts WHERE id=%s", (account_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    # ── Categories ─────────────────────────────────────────────

    def add_category(self, user_id: int, name: str, emoji: str, cat_type: str) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO categories (user_id, name, emoji, type) VALUES (%s,%s,%s,%s) RETURNING id",
                    (user_id, name, emoji, cat_type)
                )
                return cur.fetchone()['id']

    def get_categories(self, user_id: int, cat_type: str) -> List[Dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM categories WHERE user_id=%s AND type=%s ORDER BY name",
                    (user_id, cat_type)
                )
                return [dict(r) for r in cur.fetchall()]

    # ── Transactions ───────────────────────────────────────────

    def add_transaction(
        self, user_id: int, tr_type: str, account_id: int,
        amount: float, category_id: Optional[int], note: str
    ):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO transactions (user_id, type, account_id, amount, category_id, note) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (user_id, tr_type, account_id, amount, category_id, note)
                )
                if tr_type == 'income':
                    cur.execute(
                        "UPDATE accounts SET balance = balance + %s WHERE id=%s",
                        (amount, account_id)
                    )
                elif tr_type == 'expense':
                    cur.execute(
                        "UPDATE accounts SET balance = balance - %s WHERE id=%s",
                        (amount, account_id)
                    )

    def transfer(self, user_id: int, from_id: int, to_id: int, amount: float) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT balance FROM accounts WHERE id=%s", (from_id,))
                row = cur.fetchone()
                if not row or float(row['balance']) < amount:
                    return False
                cur.execute(
                    "UPDATE accounts SET balance = balance - %s WHERE id=%s",
                    (amount, from_id)
                )
                cur.execute(
                    "UPDATE accounts SET balance = balance + %s WHERE id=%s",
                    (amount, to_id)
                )
                cur.execute(
                    "INSERT INTO transactions (user_id, type, account_id, amount, note) "
                    "VALUES (%s,'transfer',%s,%s,%s)",
                    (user_id, from_id, amount, f'Перевод на счёт #{to_id}')
                )
                cur.execute(
                    "INSERT INTO transactions (user_id, type, account_id, amount, note) "
                    "VALUES (%s,'transfer',%s,%s,%s)",
                    (user_id, to_id, amount, f'Перевод со счёта #{from_id}')
                )
                return True

    def get_stats(self, user_id: int, period: str) -> List[Dict]:
        today = date.today()
        if period == 'today':
            start = today.isoformat()
        elif period == 'week':
            start = (today - timedelta(days=today.weekday())).isoformat()
        elif period == 'month':
            start = today.replace(day=1).isoformat()
        elif period == 'year':
            start = today.replace(month=1, day=1).isoformat()
        else:
            start = today.isoformat()

        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT t.type, t.amount, t.note,
                           c.name AS cat_name, c.emoji AS cat_emoji
                    FROM transactions t
                    LEFT JOIN categories c ON t.category_id = c.id
                    WHERE t.user_id = %s
                      AND t.type IN ('income','expense')
                      AND t.created_at::date >= %s
                    ORDER BY t.created_at DESC
                """, (user_id, start))
                return [dict(r) for r in cur.fetchall()]
