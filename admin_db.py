"""Банк бота, баны, админы, логи и общая статистика."""

import time

from database import (
    get_db,
    init_user,
    get_setting,
    set_setting,
    update_balance,
    add_win,
)


# ==========================================
# 🏦 БАНК БОТА
# ==========================================
def get_bank() -> int:
    value = get_setting("bank")
    try:
        return int(float(value)) if value is not None else 0
    except ValueError:
        return 0


def set_bank(value: int):
    set_setting("bank", int(value))


def add_bank(delta: int):
    set_bank(get_bank() + int(delta))


def can_pay(amount: int) -> bool:
    """Хватит ли банка, чтобы выплатить выигрыш."""
    return get_bank() >= amount


# ==========================================
# 📊 СТАТИСТИКА СТАВОК
# ==========================================
def add_bet_stat(user_id: int, amount: int):
    """Ставка сделана: деньги уходят в банк."""
    init_user(user_id)
    conn = get_db()
    conn.execute("UPDATE users SET total_bets = total_bets + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    add_bank(amount)


def add_loss(user_id: int, amount: int):
    init_user(user_id)
    conn = get_db()
    conn.execute("UPDATE users SET total_lost = total_lost + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()


def pay_win(user_id: int, amount: int, chat_id: int = 0):
    """Выплата выигрыша: деньги выходят из банка."""
    if amount <= 0:
        return
    update_balance(user_id, amount)
    add_bank(-amount)
    add_win(user_id, amount, chat_id)


def refund_bet(user_id: int, amount: int):
    """Возврат ставки: деньги возвращаются игроку из банка."""
    update_balance(user_id, amount)
    add_bank(-amount)
    conn = get_db()
    conn.execute(
        "UPDATE users SET total_bets = MAX(0, total_bets - ?) WHERE user_id = ?", (amount, user_id)
    )
    conn.commit()
    conn.close()


# ==========================================
# 🚫 БАНЫ
# ==========================================
def ban_user(user_id: int, days, reason: str, admin_id: int) -> float:
    """days = None означает бан навсегда. Возвращает время окончания (0 = навсегда)."""
    init_user(user_id)
    until = 0 if days is None else time.time() + days * 86400
    conn = get_db()
    conn.execute("UPDATE bans SET is_active = 0 WHERE user_id = ?", (user_id,))
    conn.execute(
        "INSERT INTO bans (user_id, until, reason, admin_id, is_active, created_at)"
        " VALUES (?, ?, ?, ?, 1, ?)",
        (user_id, until, reason, admin_id, time.time()),
    )
    conn.commit()
    conn.close()
    return until


def unban_user(user_id: int) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE bans SET is_active = 0 WHERE user_id = ? AND is_active = 1", (user_id,))
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def get_ban(user_id: int):
    """Активный бан или None. Истёкший бан снимается автоматически."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM bans WHERE user_id = ? AND is_active = 1", (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    ban = dict(row)
    if ban["until"] and ban["until"] < time.time():
        unban_user(user_id)
        return None
    return ban


def get_all_bans() -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM bans ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ==========================================
# 👮 АДМИНЫ
# ==========================================
def set_admin(user_id: int, level: int, added_by: int):
    init_user(user_id)
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO admins (user_id, level, added_by, created_at) VALUES (?, ?, ?, ?)",
        (user_id, level, added_by, time.time()),
    )
    conn.commit()
    conn.close()


def remove_admin(user_id: int) -> bool:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def get_admin_level(user_id: int) -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT level FROM admins WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0


def get_admins() -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM admins ORDER BY level DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def log_admin(admin_id: int, action: str, target_id: int, amount: int):
    conn = get_db()
    conn.execute(
        "INSERT INTO admin_log (admin_id, action, target_id, amount, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (admin_id, action, target_id, amount, time.time()),
    )
    conn.commit()
    conn.close()


def get_admin_log() -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM admin_log ORDER BY created_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ==========================================
# 🔎 ПОИСК ИГРОКА
# ==========================================
def find_user(query: str):
    """Ищет игрока по ID или @username."""
    query = query.strip().lstrip("@")

    conn = get_db()
    cur = conn.cursor()
    if query.isdigit():
        cur.execute("SELECT * FROM users WHERE user_id = ?", (int(query),))
    else:
        cur.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (query,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


# ==========================================
# 💬 УЧАСТНИКИ ЧАТА
# ==========================================
def touch_member(chat_id: int, user_id: int):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO chat_members (chat_id, user_id, last_seen) VALUES (?, ?, ?)",
        (chat_id, user_id, time.time()),
    )
    conn.commit()
    conn.close()


def get_chat_top(chat_id: int, limit: int = 10) -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT u.user_id, u.name, u.balance FROM users u"
        " JOIN chat_members m ON m.user_id = u.user_id"
        " WHERE m.chat_id = ? ORDER BY u.balance DESC LIMIT ?",
        (chat_id, limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ==========================================
# 📈 ОБЩАЯ СТАТИСТИКА
# ==========================================
def get_all_users() -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, name, username, reg_date FROM users ORDER BY reg_date")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def count_users() -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]
    conn.close()
    return total


def count_chats() -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM chats")
    total = cur.fetchone()[0]
    conn.close()
    return total


def get_totals() -> dict:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT SUM(total_bets), SUM(total_won), SUM(total_lost) FROM users")
    bets, won, lost = cur.fetchone()
    cur.execute("SELECT SUM(amount), SUM(stars) FROM payments WHERE is_paid = 1")
    donated, stars = cur.fetchone()
    conn.close()
    return {
        "bets": bets or 0,
        "won": won or 0,
        "lost": lost or 0,
        "donated": donated or 0,
        "stars": stars or 0,
    }


def get_top_donaters(limit: int = 50) -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT p.user_id, u.name, u.username, SUM(p.amount) AS total, SUM(p.stars) AS stars"
        " FROM payments p LEFT JOIN users u ON u.user_id = p.user_id"
        " WHERE p.is_paid = 1 GROUP BY p.user_id ORDER BY total DESC LIMIT ?",
        (limit,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ==========================================
# 📜 ИСТОРИЯ
# ==========================================
def get_transfers(user_id: int, limit: int = 20) -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM history WHERE user_id = ? AND kind = 'transfer' ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_duel_history(user_id: int, limit: int = 20) -> list:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM duels WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_game_log(user_id: int, limit: int = 100) -> list:
    """Последние ставки игрока во всех играх."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM history WHERE user_id = ? AND kind != 'transfer' ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
