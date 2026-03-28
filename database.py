import os
import psycopg2
import psycopg2.extras
from datetime import date, timedelta
from typing import List, Dict, Optional
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL", "").replace("postgres://", "postgresql://", 1)

CURRENCIES = ["UZS", "USD", "RUB"]
CURRENCY_SYMBOLS = {"UZS": "сум", "USD": "$", "RUB": "₽"}

DEFAULT_EXPENSE_CATEGORIES = [
    ("Еда и продукты", "🍔"), ("Транспорт", "🚗"), ("Коммунальные услуги", "💡"),
    ("Здоровье", "💊"), ("Одежда", "👗"), ("Развлечения", "🎮"),
    ("Связь", "📱"), ("Зарплата сотрудников", "👥"), ("Закупка товаров", "📦"), ("Прочее", "📌"),
]
DEFAULT_INCOME_CATEGORIES = [
    ("Продажи", "💰"), ("Зарплата", "💵"), ("Инвестиции", "📈"), ("Прочий доход", "✨"),
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
                        currency TEXT DEFAULT 'UZS',
                        reminder_hour INTEGER DEFAULT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                    CREATE TABLE IF NOT EXISTS teams (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        owner_id BIGINT NOT NULL REFERENCES users(id),
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                    CREATE TABLE IF NOT EXISTS team_members (
                        team_id INTEGER REFERENCES teams(id),
                        user_id BIGINT REFERENCES users(id),
                        role TEXT DEFAULT 'member',
                        PRIMARY KEY (team_id, user_id)
                    );
                    CREATE TABLE IF NOT EXISTS accounts (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL REFERENCES users(id),
                        name TEXT NOT NULL,
                        balance NUMERIC(15,2) DEFAULT 0,
                        currency TEXT DEFAULT 'UZS',
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
                        currency TEXT DEFAULT 'UZS',
                        category_id INTEGER REFERENCES categories(id),
                        note TEXT DEFAULT '',
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                # migrate: add currency column if missing
                cur.execute("""
                    ALTER TABLE accounts ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'UZS';
                    ALTER TABLE transactions ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'UZS';
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'UZS';
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS reminder_hour INTEGER DEFAULT NULL;
                """)

    # ── Users ──────────────────────────────────────────────────

    def ensure_user(self, user_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO users (id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
                cur.execute("SELECT COUNT(*) AS cnt FROM categories WHERE user_id=%s", (user_id,))
                if cur.fetchone()['cnt'] == 0:
                    for name, emoji in DEFAULT_EXPENSE_CATEGORIES:
                        cur.execute("INSERT INTO categories (user_id,name,emoji,type) VALUES (%s,%s,%s,'expense')", (user_id, name, emoji))
                    for name, emoji in DEFAULT_INCOME_CATEGORIES:
                        cur.execute("INSERT INTO categories (user_id,name,emoji,type) VALUES (%s,%s,%s,'income')", (user_id, name, emoji))

    def get_user(self, user_id: int) -> Optional[Dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE id=%s", (user_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def set_currency(self, user_id: int, currency: str):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET currency=%s WHERE id=%s", (currency, user_id))

    def set_reminder(self, user_id: int, hour: Optional[int]):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET reminder_hour=%s WHERE id=%s", (hour, user_id))

    def get_all_reminder_users(self, hour: int) -> List[Dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE reminder_hour=%s", (hour,))
                return [dict(r) for r in cur.fetchall()]

    # ── Accounts ───────────────────────────────────────────────

    def add_account(self, user_id: int, name: str, balance: float = 0, currency: str = 'UZS') -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO accounts (user_id,name,balance,currency) VALUES (%s,%s,%s,%s) RETURNING id",
                            (user_id, name, balance, currency))
                return cur.fetchone()['id']

    def get_accounts(self, user_id: int) -> List[Dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM accounts WHERE user_id=%s ORDER BY id", (user_id,))
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
                cur.execute("INSERT INTO categories (user_id,name,emoji,type) VALUES (%s,%s,%s,%s) RETURNING id",
                            (user_id, name, emoji, cat_type))
                return cur.fetchone()['id']

    def get_categories(self, user_id: int, cat_type: str) -> List[Dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM categories WHERE user_id=%s AND type=%s ORDER BY name", (user_id, cat_type))
                return [dict(r) for r in cur.fetchall()]

    # ── Transactions ───────────────────────────────────────────

    def add_transaction(self, user_id: int, tr_type: str, account_id: int,
                        amount: float, category_id: Optional[int], note: str, currency: str = 'UZS'):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO transactions (user_id,type,account_id,amount,category_id,note,currency) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (user_id, tr_type, account_id, amount, category_id, note, currency)
                )
                if tr_type == 'income':
                    cur.execute("UPDATE accounts SET balance=balance+%s WHERE id=%s", (amount, account_id))
                elif tr_type == 'expense':
                    cur.execute("UPDATE accounts SET balance=balance-%s WHERE id=%s", (amount, account_id))

    def transfer(self, user_id: int, from_id: int, to_id: int, amount: float) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT balance FROM accounts WHERE id=%s", (from_id,))
                row = cur.fetchone()
                if not row or float(row['balance']) < amount:
                    return False
                cur.execute("UPDATE accounts SET balance=balance-%s WHERE id=%s", (amount, from_id))
                cur.execute("UPDATE accounts SET balance=balance+%s WHERE id=%s", (amount, to_id))
                cur.execute("INSERT INTO transactions (user_id,type,account_id,amount,note) VALUES (%s,'transfer',%s,%s,%s)",
                            (user_id, from_id, amount, f'Перевод на счёт #{to_id}'))
                cur.execute("INSERT INTO transactions (user_id,type,account_id,amount,note) VALUES (%s,'transfer',%s,%s,%s)",
                            (user_id, to_id, amount, f'Перевод со счёта #{from_id}'))
                return True

    def get_stats(self, user_id: int, period: str) -> List[Dict]:
        today = date.today()
        starts = {"today": today, "week": today - timedelta(days=today.weekday()),
                  "month": today.replace(day=1), "year": today.replace(month=1, day=1)}
        start = starts.get(period, today).isoformat()
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT t.type, t.amount, t.currency, t.note,
                           c.name AS cat_name, c.emoji AS cat_emoji
                    FROM transactions t
                    LEFT JOIN categories c ON t.category_id=c.id
                    WHERE t.user_id=%s AND t.type IN ('income','expense') AND t.created_at::date >= %s
                    ORDER BY t.created_at DESC
                """, (user_id, start))
                return [dict(r) for r in cur.fetchall()]

    def get_all_transactions(self, user_id: int) -> List[Dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT t.id, t.type, t.amount, t.currency, t.note, t.created_at,
                           a.name AS account_name,
                           c.name AS cat_name, c.emoji AS cat_emoji
                    FROM transactions t
                    LEFT JOIN accounts a ON t.account_id=a.id
                    LEFT JOIN categories c ON t.category_id=c.id
                    WHERE t.user_id=%s AND t.type IN ('income','expense')
                    ORDER BY t.created_at DESC
                    LIMIT 1000
                """, (user_id,))
                return [dict(r) for r in cur.fetchall()]

    # ── Teams ──────────────────────────────────────────────────

    def create_team(self, owner_id: int, name: str) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO teams (owner_id,name) VALUES (%s,%s) RETURNING id", (owner_id, name))
                team_id = cur.fetchone()['id']
                cur.execute("INSERT INTO team_members (team_id,user_id,role) VALUES (%s,%s,'owner') ON CONFLICT DO NOTHING",
                            (team_id, owner_id))
                return team_id

    def get_team_invite_link(self, team_id: int) -> str:
        return f"team_{team_id}"

    def join_team(self, user_id: int, team_id: int) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM teams WHERE id=%s", (team_id,))
                if not cur.fetchone():
                    return False
                cur.execute("INSERT INTO team_members (team_id,user_id,role) VALUES (%s,%s,'member') ON CONFLICT DO NOTHING",
                            (team_id, user_id))
                return True

    def get_user_teams(self, user_id: int) -> List[Dict]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT t.id, t.name, tm.role,
                           (SELECT COUNT(*) FROM team_members WHERE team_id=t.id) AS member_count
                    FROM teams t JOIN team_members tm ON t.id=tm.team_id
                    WHERE tm.user_id=%s
                """, (user_id,))
                return [dict(r) for r in cur.fetchall()]
