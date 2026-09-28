import json
import os
import sqlite3
import time
from datetime import datetime, timedelta

from config import START_BALANCE, START_GALLEONS, TOUR_USERS_DAYS, TOUR_CHATS_DAYS

# Абсолютный путь: база всегда лежит рядом с кодом, из какой бы папки
# ни запускали бота. Иначе создалась бы вторая пустая база.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "gram.db")

# Все характеристики Хогвартса: ключ в БД -> название на русском
STATS = {
    "stat_block": "Блок",
    "stat_stamina": "Выносливость",
    "stat_health": "Здоровье",
    "stat_intuition": "Интуиция",
    "stat_power": "Сила",
    "stat_speed": "Скорость",
    "stat_charisma": "Харизма",
}


def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.row_factory = sqlite3.Row
    # WAL — записи не теряются при падении и не блокируют чтение,
    # synchronous=FULL — каждая транзакция сразу ложится на диск
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def migrate():
    """Добавляет колонки, которых нет в старой базе, не трогая данные."""
    columns = {
        "chats": {
            "treasury_on": "INTEGER DEFAULT 0",
            "treasury_balance": "INTEGER DEFAULT 0",
            "treasury_reward": "INTEGER DEFAULT 1000",
        },
    }

    conn = get_db()
    cur = conn.cursor()
    for table, needed in columns.items():
        have = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
        for name, spec in needed.items():
            if name not in have:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")
                print(f"База обновлена: {table}.{name}")
    conn.commit()
    conn.close()


def create_tables():
    conn = get_db()
    conn.execute(f'''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT DEFAULT 'Игрок',
            username TEXT DEFAULT '',
            balance INTEGER DEFAULT {START_BALANCE},
            galleons INTEGER DEFAULT {START_GALLEONS},
            clan_id INTEGER DEFAULT 0,
            stat_block INTEGER DEFAULT 1,
            stat_stamina INTEGER DEFAULT 1,
            stat_health INTEGER DEFAULT 1,
            stat_intuition INTEGER DEFAULT 1,
            stat_power INTEGER DEFAULT 1,
            stat_speed INTEGER DEFAULT 1,
            stat_charisma INTEGER DEFAULT 1,
            is_vip INTEGER DEFAULT 0,
            last_bonus REAL DEFAULT 0,
            reg_date REAL DEFAULT 0,
            tour_wins INTEGER DEFAULT 0,
            total_won INTEGER DEFAULT 0,
            total_bets INTEGER DEFAULT 0,
            total_lost INTEGER DEFAULT 0
        )
    ''')
    # История переводов и дуэлей
    conn.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            kind TEXT,
            amount INTEGER,
            partner_id INTEGER,
            created_at REAL
        )
    ''')
    # Счета на оплату звёздами
    conn.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            payment_id INTEGER PRIMARY KEY,
            user_id INTEGER,
            pack_id TEXT,
            amount INTEGER,
            stars INTEGER,
            is_paid INTEGER DEFAULT 0,
            created_at REAL
        )
    ''')
    # Чаты (для турнира чатов и казны)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT DEFAULT 'Чат',
            link TEXT DEFAULT '',
            tour_wins INTEGER DEFAULT 0,
            total_won INTEGER DEFAULT 0,
            total_bets INTEGER DEFAULT 0,
            total_lost INTEGER DEFAULT 0,
            treasury_on INTEGER DEFAULT 0,
            treasury_balance INTEGER DEFAULT 0,
            treasury_reward INTEGER DEFAULT 1000
        )
    ''')
    # Кланы
    conn.execute('''
        CREATE TABLE IF NOT EXISTS clans (
            clan_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            owner_id INTEGER,
            balance INTEGER DEFAULT 0,
            total_won INTEGER DEFAULT 0,
            created_at REAL
        )
    ''')
    # Ставки рулетки (в базе, чтобы вернуть деньги после перезапуска)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS bets (
            bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            amount INTEGER,
            label TEXT,
            numbers TEXT,
            created_at REAL
        )
    ''')
    # Лог выпавших чисел рулетки
    conn.execute('''
        CREATE TABLE IF NOT EXISTS roulette_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            number INTEGER,
            created_at REAL
        )
    ''')
    # Активные игры "Минное поле"
    conn.execute('''
        CREATE TABLE IF NOT EXISTS mines_games (
            message_id INTEGER,
            chat_id INTEGER,
            user_id INTEGER,
            bet INTEGER,
            mines TEXT,
            opened TEXT,
            is_active INTEGER DEFAULT 1,
            created_at REAL,
            PRIMARY KEY (chat_id, message_id)
        )
    ''')
    # Активные игры "Джокер"
    conn.execute('''
        CREATE TABLE IF NOT EXISTS joker_games (
            message_id INTEGER,
            chat_id INTEGER,
            user_id INTEGER,
            bet INTEGER,
            skulls TEXT,
            picks TEXT,
            is_active INTEGER DEFAULT 1,
            created_at REAL,
            PRIMARY KEY (chat_id, message_id)
        )
    ''')
    # Дуэли
    conn.execute('''
        CREATE TABLE IF NOT EXISTS duels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            opponent_id INTEGER,
            chat_id INTEGER,
            is_win INTEGER,
            reward INTEGER,
            galleons INTEGER,
            created_at REAL
        )
    ''')
    # Баны (храним всю историю, активный — is_active = 1)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS bans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            until REAL DEFAULT 0,
            reason TEXT DEFAULT '',
            admin_id INTEGER,
            is_active INTEGER DEFAULT 1,
            created_at REAL
        )
    ''')
    # Админы и их уровни
    conn.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            level INTEGER DEFAULT 1,
            added_by INTEGER,
            created_at REAL
        )
    ''')
    # Логи выдачи и изъятия монет
    conn.execute('''
        CREATE TABLE IF NOT EXISTS admin_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            target_id INTEGER,
            amount INTEGER,
            created_at REAL
        )
    ''')
    # Кто в каком чате играет — для /top
    conn.execute('''
        CREATE TABLE IF NOT EXISTS chat_members (
            chat_id INTEGER,
            user_id INTEGER,
            last_seen REAL,
            PRIMARY KEY (chat_id, user_id)
        )
    ''')
    # Кто кого привёл: пара чат+участник уникальна, чтобы не платить дважды
    conn.execute('''
        CREATE TABLE IF NOT EXISTS invites (
            chat_id INTEGER,
            member_id INTEGER,
            inviter_id INTEGER,
            created_at REAL,
            PRIMARY KEY (chat_id, member_id)
        )
    ''')
    # Служебные настройки (даты окончания турниров и т.д.)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()
    conn.close()


create_tables()
migrate()


# ==========================================
# ⚙️ НАСТРОЙКИ
# ==========================================
def get_setting(key: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def set_setting(key: str, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()


# ==========================================
# 👤 ПОЛЬЗОВАТЕЛИ
# ==========================================
def init_user(user_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO users (user_id, reg_date) VALUES (?, ?)", (user_id, time.time()))
        conn.commit()
    conn.close()


def get_user(user_id: int) -> dict:
    init_user(user_id)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    data = cur.fetchone()
    conn.close()
    return dict(data)


def update_user_name(user_id: int, name: str, username: str = ""):
    init_user(user_id)
    conn = get_db()
    conn.execute(
        "UPDATE users SET name = ?, username = ? WHERE user_id = ?",
        (name, username or "", user_id),
    )
    conn.commit()
    conn.close()


def get_tag(user_id: int) -> str:
    """@username, если он есть, иначе кликабельное имя."""
    user = get_user(user_id)
    if user["username"]:
        return f"@{user['username']}"
    import html
    return f'<a href="tg://user?id={user_id}">{html.escape(user["name"] or "Игрок")}</a>'


def get_name(user_id: int) -> str:
    return get_user(user_id)["name"] or "Игрок"


# ==========================================
# 💰 БАЛАНС GRAM
# ==========================================
def get_balance(user_id: int) -> int:
    return get_user(user_id)["balance"]


def update_balance(user_id: int, amount: int):
    init_user(user_id)
    conn = get_db()
    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()


# ==========================================
# 🪙 ГАЛЕОНЫ (валюта прокачки)
# ==========================================
def get_galleons(user_id: int) -> int:
    return get_user(user_id)["galleons"]


def update_galleons(user_id: int, amount: int):
    init_user(user_id)
    conn = get_db()
    conn.execute("UPDATE users SET galleons = galleons + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()


# ==========================================
# 🔮 ХАРАКТЕРИСТИКИ ХОГВАРТСА
# ==========================================
def get_stats(user_id: int) -> dict:
    user = get_user(user_id)
    return {key: user[key] for key in STATS}


def get_stats_sum(user_id: int) -> int:
    return sum(get_stats(user_id).values())


def upgrade_price(level: int) -> int:
    """Первая прокачка — 10 галеонов, вторая — 20, третья — 30 и так далее."""
    return level * 10


def upgrade_stat(user_id: int, stat_key: str) -> tuple[bool, int]:
    """Пробует прокачать характеристику. Возвращает (успех, цена)."""
    if stat_key not in STATS:
        return False, 0

    user = get_user(user_id)
    price = upgrade_price(user[stat_key])

    if user["galleons"] < price:
        return False, price

    conn = get_db()
    conn.execute(
        f"UPDATE users SET {stat_key} = {stat_key} + 1, galleons = galleons - ? WHERE user_id = ?",
        (price, user_id),
    )
    conn.commit()
    conn.close()
    return True, price


# ==========================================
# 📜 ИСТОРИЯ
# ==========================================
def add_history(user_id: int, kind: str, amount: int, partner_id: int = 0):
    conn = get_db()
    conn.execute(
        "INSERT INTO history (user_id, kind, amount, partner_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, kind, amount, partner_id, time.time()),
    )
    conn.commit()
    conn.close()


def get_history(user_id: int, limit: int = 15) -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM history WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ==========================================
# 💳 ПЛАТЕЖИ
# ==========================================
def create_payment(payment_id: int, user_id: int, pack_id: str, amount: int, stars: int):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO payments (payment_id, user_id, pack_id, amount, stars, is_paid, created_at)"
        " VALUES (?, ?, ?, ?, ?, 0, ?)",
        (payment_id, user_id, pack_id, amount, stars, time.time()),
    )
    conn.commit()
    conn.close()


def get_payment(payment_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def close_payment(payment_id: int):
    conn = get_db()
    conn.execute("UPDATE payments SET is_paid = 1 WHERE payment_id = ?", (payment_id,))
    conn.commit()
    conn.close()


def set_vip(user_id: int):
    init_user(user_id)
    conn = get_db()
    conn.execute("UPDATE users SET is_vip = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ==========================================
# 🏆 ТОП
# ==========================================
def get_top(limit: int = 10) -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, name, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ==========================================
# 🏆 ТУРНИРЫ
# ==========================================
TOUR_DAYS = {
    "users": TOUR_USERS_DAYS,
    "chats": TOUR_CHATS_DAYS,
}


def _next_end(days: int) -> datetime:
    """Ближайшее 00:00 через указанное количество дней."""
    midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(days=days)


def get_tour_end(kind: str) -> datetime:
    """Дата окончания круга турнира. Если круг закончился — обнуляет счёт и стартует новый."""
    days = TOUR_DAYS.get(kind, 1)
    key = f"tour_end_{kind}"
    raw = get_setting(key)

    if raw is None:
        end = _next_end(days)
        set_setting(key, end.timestamp())
        return end

    end = datetime.fromtimestamp(float(raw))

    if datetime.now() >= end:
        reset_tournament(kind)
        while end <= datetime.now():
            end += timedelta(days=days)
        set_setting(key, end.timestamp())

    return end


def reset_tournament(kind: str):
    """Обнуляет результаты круга (общая статистика total_won остаётся)."""
    table = "users" if kind == "users" else "chats"
    conn = get_db()
    conn.execute(f"UPDATE {table} SET tour_wins = 0")
    conn.commit()
    conn.close()


def add_win(user_id: int, amount: int, chat_id: int = 0):
    """Засчитывает выигрыш игроку и (если игра была в группе) его чату."""
    if amount <= 0:
        return

    init_user(user_id)
    conn = get_db()
    conn.execute(
        "UPDATE users SET tour_wins = tour_wins + ?, total_won = total_won + ? WHERE user_id = ?",
        (amount, amount, user_id),
    )
    conn.commit()
    conn.close()

    if chat_id and chat_id < 0:
        add_chat_win(chat_id, amount)

    # Выигрыш участника идёт в копилку его клана
    clan_id = get_user(user_id)["clan_id"]
    if clan_id:
        add_clan_win(clan_id, amount)


def add_chat_win(chat_id: int, amount: int):
    init_chat(chat_id)
    conn = get_db()
    conn.execute(
        "UPDATE chats SET tour_wins = tour_wins + ?, total_won = total_won + ? WHERE chat_id = ?",
        (amount, amount, chat_id),
    )
    conn.commit()
    conn.close()


def get_tour_wins(user_id: int) -> int:
    get_tour_end("users")
    return get_user(user_id)["tour_wins"]


def get_tour_top_users(limit: int = 10) -> list:
    get_tour_end("users")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, name, tour_wins FROM users WHERE tour_wins > 0 ORDER BY tour_wins DESC LIMIT ?",
        (limit,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_tour_top_chats(limit: int = 10) -> list:
    get_tour_end("chats")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT chat_id, title, link, tour_wins FROM chats WHERE tour_wins > 0 ORDER BY tour_wins DESC LIMIT ?",
        (limit,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ==========================================
# 💬 ЧАТЫ
# ==========================================
def init_chat(chat_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT chat_id FROM chats WHERE chat_id = ?", (chat_id,))
    if cur.fetchone() is None:
        cur.execute("INSERT INTO chats (chat_id) VALUES (?)", (chat_id,))
        conn.commit()
    conn.close()


def update_chat_info(chat_id: int, title: str, username: str = ""):
    """Обновляет название и ссылку чата для турнира чатов."""
    init_chat(chat_id)
    link = f"https://t.me/{username}" if username else ""
    conn = get_db()
    if link:
        conn.execute("UPDATE chats SET title = ?, link = ? WHERE chat_id = ?", (title, link, chat_id))
    else:
        conn.execute("UPDATE chats SET title = ? WHERE chat_id = ?", (title, chat_id))
    conn.commit()
    conn.close()


# ==========================================
# 🏰 КЛАНЫ
# ==========================================
CLAN_PRICE = 25000


def create_clan(name: str, owner_id: int):
    """Создаёт клан. Возвращает id клана или None, если имя занято."""
    init_user(owner_id)
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO clans (name, owner_id, created_at) VALUES (?, ?, ?)",
            (name, owner_id, time.time()),
        )
        clan_id = cur.lastrowid
        cur.execute("UPDATE users SET clan_id = ? WHERE user_id = ?", (clan_id, owner_id))
        conn.commit()
        return clan_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_clan(clan_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clans WHERE clan_id = ?", (clan_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_clan_by_name(name: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clans WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def search_clans(query: str, limit: int = 10) -> list:
    """Ищет кланы по части названия."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM clans WHERE name LIKE ? ORDER BY balance DESC LIMIT ?",
        (f"%{query}%", limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def count_clans() -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM clans")
    total = cur.fetchone()[0]
    conn.close()
    return total


def get_clans_page(page: int = 1, per_page: int = 6) -> list:
    """Страница общего списка кланов (по алфавиту, как в оригинале)."""
    offset = (page - 1) * per_page
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clans ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?", (per_page, offset))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_top_clans(limit: int = 30) -> list:
    """Топ кланов по сумме выигрышей за всё время."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM clans ORDER BY total_won DESC, balance DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def count_clan_members(clan_id: int) -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE clan_id = ?", (clan_id,))
    total = cur.fetchone()[0]
    conn.close()
    return total


def set_user_clan(user_id: int, clan_id: int):
    init_user(user_id)
    conn = get_db()
    conn.execute("UPDATE users SET clan_id = ? WHERE user_id = ?", (clan_id, user_id))
    conn.commit()
    conn.close()


def get_user_clan(user_id: int):
    clan_id = get_user(user_id)["clan_id"]
    return get_clan(clan_id) if clan_id else None


def update_clan_balance(clan_id: int, amount: int):
    conn = get_db()
    conn.execute("UPDATE clans SET balance = balance + ? WHERE clan_id = ?", (amount, clan_id))
    conn.commit()
    conn.close()


def add_clan_win(clan_id: int, amount: int):
    """Засчитывает клану выигрыш участника (для топа кланов)."""
    conn = get_db()
    conn.execute(
        "UPDATE clans SET total_won = total_won + ?, balance = balance + ? WHERE clan_id = ?",
        (amount, amount, clan_id),
    )
    conn.commit()
    conn.close()


# ==========================================
# 🎁 ЕЖЕДНЕВНЫЙ БОНУС
# ==========================================
def get_last_bonus(user_id: int) -> float:
    return get_user(user_id)["last_bonus"]


def set_last_bonus(user_id: int, timestamp: float):
    init_user(user_id)
    conn = get_db()
    conn.execute("UPDATE users SET last_bonus = ? WHERE user_id = ?", (timestamp, user_id))
    conn.commit()
    conn.close()


# ==========================================
# 🎰 СТАВКИ РУЛЕТКИ
# ==========================================
def add_bet(chat_id: int, user_id: int, amount: int, label: str, numbers: list) -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO bets (chat_id, user_id, amount, label, numbers, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (chat_id, user_id, amount, label, json.dumps(numbers), time.time()),
    )
    bet_id = cur.lastrowid
    conn.commit()
    conn.close()
    return bet_id


def add_bets(chat_id: int, user_id: int, rows: list):
    """Пачка ставок одной транзакцией — сотня ставок ставится мгновенно."""
    now = time.time()
    conn = get_db()
    conn.executemany(
        "INSERT INTO bets (chat_id, user_id, amount, label, numbers, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        [(chat_id, user_id, amount, label, json.dumps(numbers), now) for amount, label, numbers in rows],
    )
    conn.commit()
    conn.close()


def get_bets(chat_id: int) -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM bets WHERE chat_id = ? ORDER BY bet_id", (chat_id,))
    rows = []
    for r in cur.fetchall():
        row = dict(r)
        row["numbers"] = json.loads(row["numbers"])
        rows.append(row)
    conn.close()
    return rows


def get_user_bets(chat_id: int, user_id: int) -> list:
    return [b for b in get_bets(chat_id) if b["user_id"] == user_id]


def clear_bets(chat_id: int, user_id: int = None):
    conn = get_db()
    if user_id is None:
        conn.execute("DELETE FROM bets WHERE chat_id = ?", (chat_id,))
    else:
        conn.execute("DELETE FROM bets WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
    conn.commit()
    conn.close()


def get_round_start(chat_id: int):
    """Время первой ставки в текущем раунде чата."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT MIN(created_at) FROM bets WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()[0]
    conn.close()
    return row


def get_stale_chats(max_age: float) -> list:
    """Чаты, где ставки висят дольше max_age секунд."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT chat_id FROM bets GROUP BY chat_id HAVING MIN(created_at) < ?",
        (time.time() - max_age,),
    )
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


# ==========================================
# 📜 ЛОГ РУЛЕТКИ
# ==========================================
def add_roulette_log(chat_id: int, number: int):
    conn = get_db()
    conn.execute(
        "INSERT INTO roulette_log (chat_id, number, created_at) VALUES (?, ?, ?)",
        (chat_id, number, time.time()),
    )
    conn.commit()
    conn.close()


def get_roulette_log(chat_id: int, limit: int = 10) -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT number FROM roulette_log WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
        (chat_id, limit),
    )
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


# ==========================================
# 💣 МИННОЕ ПОЛЕ
# ==========================================
def save_mines_game(chat_id: int, message_id: int, user_id: int, bet: int, mines: list, opened: list):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO mines_games"
        " (chat_id, message_id, user_id, bet, mines, opened, is_active, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        (chat_id, message_id, user_id, bet, json.dumps(mines), json.dumps(opened), time.time()),
    )
    conn.commit()
    conn.close()


def get_mines_game(chat_id: int, message_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM mines_games WHERE chat_id = ? AND message_id = ? AND is_active = 1",
        (chat_id, message_id),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    game = dict(row)
    game["mines"] = json.loads(game["mines"])
    game["opened"] = json.loads(game["opened"])
    return game


def update_mines_opened(chat_id: int, message_id: int, opened: list, mines: list = None):
    conn = get_db()
    if mines is None:
        conn.execute(
            "UPDATE mines_games SET opened = ? WHERE chat_id = ? AND message_id = ?",
            (json.dumps(opened), chat_id, message_id),
        )
    else:
        conn.execute(
            "UPDATE mines_games SET opened = ?, mines = ? WHERE chat_id = ? AND message_id = ?",
            (json.dumps(opened), json.dumps(mines), chat_id, message_id),
        )
    conn.commit()
    conn.close()


def close_mines_game(chat_id: int, message_id: int):
    conn = get_db()
    conn.execute(
        "UPDATE mines_games SET is_active = 0 WHERE chat_id = ? AND message_id = ?",
        (chat_id, message_id),
    )
    conn.commit()
    conn.close()


def get_stale_mines(max_age: float) -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM mines_games WHERE is_active = 1 AND created_at < ?",
        (time.time() - max_age,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_rtp(game: str, default: float = 1.0) -> float:
    """RTP игры — меняется из админ-панели."""
    value = get_setting(f"rtp_{game}")
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


def set_rtp(game: str, value: float):
    set_setting(f"rtp_{game}", value)


# ==========================================
# 🃏 ДЖОКЕР
# ==========================================
def save_joker_game(chat_id: int, message_id: int, user_id: int, bet: int, skulls: list, picks: list):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO joker_games"
        " (chat_id, message_id, user_id, bet, skulls, picks, is_active, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        (chat_id, message_id, user_id, bet, json.dumps(skulls), json.dumps(picks), time.time()),
    )
    conn.commit()
    conn.close()


def get_joker_game(chat_id: int, message_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM joker_games WHERE chat_id = ? AND message_id = ? AND is_active = 1",
        (chat_id, message_id),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    game = dict(row)
    game["skulls"] = json.loads(game["skulls"])
    game["picks"] = json.loads(game["picks"])
    return game


def update_joker_game(chat_id: int, message_id: int, skulls: list, picks: list):
    conn = get_db()
    conn.execute(
        "UPDATE joker_games SET skulls = ?, picks = ? WHERE chat_id = ? AND message_id = ?",
        (json.dumps(skulls), json.dumps(picks), chat_id, message_id),
    )
    conn.commit()
    conn.close()


def close_joker_game(chat_id: int, message_id: int):
    conn = get_db()
    conn.execute(
        "UPDATE joker_games SET is_active = 0 WHERE chat_id = ? AND message_id = ?",
        (chat_id, message_id),
    )
    conn.commit()
    conn.close()


def get_stale_joker(max_age: float) -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM joker_games WHERE is_active = 1 AND created_at < ?",
        (time.time() - max_age,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ==========================================
# ⚔️ ДУЭЛИ
# ==========================================
def add_duel(user_id: int, opponent_id: int, chat_id: int, is_win: bool, reward: int, galleons: int):
    conn = get_db()
    conn.execute(
        "INSERT INTO duels (user_id, opponent_id, chat_id, is_win, reward, galleons, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, opponent_id, chat_id, int(is_win), reward, galleons, time.time()),
    )
    conn.commit()
    conn.close()


def get_duels_since(user_id: int, since: float) -> list:
    """Дуэли игрока за последние сутки — от старых к новым."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT created_at FROM duels WHERE user_id = ? AND created_at > ? ORDER BY created_at",
        (user_id, since),
    )
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


# ==========================================
# 🏦 КАЗНА ЧАТА
# ==========================================
def get_treasury(chat_id: int) -> dict:
    init_chat(chat_id)
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT treasury_on, treasury_balance, treasury_reward FROM chats WHERE chat_id = ?",
        (chat_id,),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row)


def open_treasury(chat_id: int, reward: int = 1000):
    init_chat(chat_id)
    conn = get_db()
    conn.execute(
        "UPDATE chats SET treasury_on = 1, treasury_reward = ? WHERE chat_id = ?",
        (reward, chat_id),
    )
    conn.commit()
    conn.close()


def add_treasury(chat_id: int, amount: int):
    init_chat(chat_id)
    conn = get_db()
    conn.execute(
        "UPDATE chats SET treasury_balance = treasury_balance + ? WHERE chat_id = ?",
        (amount, chat_id),
    )
    conn.commit()
    conn.close()


def set_treasury_reward(chat_id: int, reward: int):
    init_chat(chat_id)
    conn = get_db()
    conn.execute("UPDATE chats SET treasury_reward = ? WHERE chat_id = ?", (reward, chat_id))
    conn.commit()
    conn.close()


def pay_from_treasury(chat_id: int, user_id: int, amount: int) -> bool:
    """Снимает награду из казны и отдаёт игроку. False — в казне не хватило."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE chats SET treasury_balance = treasury_balance - ?"
        " WHERE chat_id = ? AND treasury_balance >= ?",
        (amount, chat_id, amount),
    )
    paid = cur.rowcount > 0
    conn.commit()
    conn.close()

    if paid:
        update_balance(user_id, amount)
    return paid


def register_invite(chat_id: int, member_id: int, inviter_id: int) -> bool:
    """Записывает приглашение. False — за этого человека уже платили."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO invites (chat_id, member_id, inviter_id, created_at)"
        " VALUES (?, ?, ?, ?)",
        (chat_id, member_id, inviter_id, time.time()),
    )
    added = cur.rowcount > 0
    conn.commit()
    conn.close()
    return added
