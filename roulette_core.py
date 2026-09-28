"""Ядро рулетки: разбор ставок, коэффициенты и генерация числа."""

import hashlib
import os
import re
import secrets
import time

# Красные числа европейской рулетки, остальные (кроме 0) — чёрные
RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
BLACK_NUMBERS = set(range(1, 37)) - RED_NUMBERS

ALL_NUMBERS = list(range(37))

# Слова, которыми можно назвать ставку
ALIASES = {
    "RED": {"красное", "красный", "красн", "кр", "к", "red", "r"},
    "BLACK": {"черное", "чёрное", "черный", "чёрный", "черн", "ч", "black", "b"},
    "EVEN": {"чет", "чёт", "четное", "чётное", "even", "евен", "е"},
    "ODD": {"нечет", "нечёт", "нечетное", "нечётное", "odd", "одд", "н"},
}


def color_emoji(number: int) -> str:
    if number == 0:
        return "🟢"
    return "🔴" if number in RED_NUMBERS else "⚫"


def spin() -> int:
    """Криптостойкий бросок: смешиваем системную энтропию с таймером."""
    seed = os.urandom(32) + str(time.time_ns()).encode() + secrets.token_bytes(16)
    digest = hashlib.blake2b(seed, digest_size=32).digest()

    # Отбрасываем значения, выходящие за кратность 37, чтобы не было перекоса
    limit = (2 ** 64 // 37) * 37
    while True:
        value = int.from_bytes(digest[:8], "big")
        if value < limit:
            return value % 37
        digest = hashlib.blake2b(digest + os.urandom(16), digest_size=32).digest()


def parse_target(token: str):
    """Разбирает одну ставку. Возвращает (метка, список чисел) или None."""
    token = token.strip().lower()

    if not token:
        return None

    for label, words in ALIASES.items():
        if token in words:
            if label == "RED":
                return "RED", sorted(RED_NUMBERS)
            if label == "BLACK":
                return "BLACK", sorted(BLACK_NUMBERS)
            if label == "EVEN":
                return "EVEN", [n for n in range(1, 37) if n % 2 == 0]
            return "ODD", [n for n in range(1, 37) if n % 2 == 1]

    # Диапазон вида 0-36
    match = re.fullmatch(r"(\d{1,2})\s*-\s*(\d{1,2})", token)
    if match:
        a, b = int(match.group(1)), int(match.group(2))
        if a > b:
            a, b = b, a
        if 0 <= a <= 36 and 0 <= b <= 36:
            return f"{a}-{b}", list(range(a, b + 1))
        return None

    # Одно число
    if token.isdigit():
        number = int(token)
        if 0 <= number <= 36:
            return str(number), [number]

    return None


def payout(amount: int, numbers: list) -> int:
    """Выплата = ставка * 36 / количество покрытых чисел.

    RED/BLACK/EVEN/ODD и 1-18/19-36 дают x2, дюжины x3, одно число x36,
    а 0-36 (37 чисел) — 0.97, как в оригинале.
    """
    if not numbers:
        return 0
    return int(amount * 36 / len(numbers))


def parse_bet_message(text: str):
    """Разбирает сообщение вида "100 к чет 0-36 17".

    Возвращает (сумма, [(метка, числа), ...]) или None, если это не ставка.
    """
    parts = text.replace(",", " ").split()
    if len(parts) < 2:
        return None

    amount_raw = parts[0].lower()
    if not amount_raw.isdigit():
        return None

    amount = int(amount_raw)
    if amount <= 0:
        return None

    targets = []
    for token in parts[1:]:
        target = parse_target(token)
        if target is None:
            return None
        targets.append(target)

    if not targets:
        return None

    return amount, targets


def total_payout(bets: list, number: int) -> int:
    """Сколько бот выплатит игрокам, если выпадет это число."""
    return sum(payout(b["amount"], b["numbers"]) for b in bets if number in b["numbers"])


def pick_number(bets: list, bank: int) -> int:
    """Бросок с оглядкой на банк.

    Из 37 чисел берём те, выплату по которым банк потянет, и честно выбираем
    среди них. Если банк не тянет ни одного — выпадает самое дешёвое число.
    """
    if not bets:
        return spin()

    affordable = [n for n in ALL_NUMBERS if total_payout(bets, n) <= bank]

    if not affordable:
        cheapest = min(total_payout(bets, n) for n in ALL_NUMBERS)
        affordable = [n for n in ALL_NUMBERS if total_payout(bets, n) == cheapest]

    if len(affordable) == 37:
        return spin()

    return affordable[secrets.randbelow(len(affordable))]
