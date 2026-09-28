import asyncio
import random
import time

from aiogram import Router, types, F, Bot
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import (
    get_balance,
    update_balance,
    add_bets,
    get_bets,
    get_user_bets,
    clear_bets,
    get_round_start,
    add_roulette_log,
    get_roulette_log,
    add_win,
    get_name,
)
from admin_db import add_bet_stat, add_loss, pay_win, get_bank, refund_bet
from roulette_core import parse_bet_message, parse_target, payout, spin, pick_number, color_emoji
from utils import fmt, mention
from config import GIF_PATH, ROUND_DELAY
from settings import CURRENCY

router = Router()
# Игры работают только в чатах, в личке их нет
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

# Чаты, где прямо сейчас крутится барабан
SPINNING = set()
# Последние ставки игроков для кнопок "Повторить" и "Удвоить"
LAST_BETS = {}

# Сколько ставок принимаем одним сообщением
MAX_BETS = 100

# Предел длины сообщения в Telegram (с запасом)
LIMIT = 3900


def result_kb() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Повторить", callback_data="roul_repeat", style="primary")
    builder.button(text="Удвоить", callback_data="roul_double", style="primary")
    builder.adjust(2)
    return builder.as_markup()


async def send_lines(message: types.Message, lines: list, markup=None):
    """Отправляет список строк, разбивая на несколько сообщений.

    В одно сообщение Telegram пускает 4096 символов, а сотня ставок даёт
    больше восьми тысяч — без разбивки бот просто ничего не отвечает.
    Кнопки вешаются на последнее сообщение.
    """
    chunks, current, size = [], [], 0

    for line in lines:
        if size + len(line) + 1 > LIMIT and current:
            chunks.append(current)
            current, size = [], 0
        current.append(line)
        size += len(line) + 1

    if current:
        chunks.append(current)

    for i, chunk in enumerate(chunks):
        await message.answer(
            "\n".join(chunk),
            parse_mode="HTML",
            reply_markup=markup if i == len(chunks) - 1 else None,
        )


# ==========================================
# 🎰 ПРИЁМ СТАВОК
# ==========================================
async def place_bets(message: types.Message, amount: int, targets: list, user_id: int, name: str):
    """Ставит игроку список ставок и отвечает списком принятых."""
    if len(targets) > MAX_BETS:
        return await message.answer(
            f"{mention(user_id, name)}, за раз можно сделать не больше "
            f"{MAX_BETS} ставок, а у вас {len(targets)}.",
            parse_mode="HTML",
        )

    total = amount * len(targets)

    if get_balance(user_id) < total:
        return await message.answer(
            f"{mention(user_id, name)}, недостаточно {CURRENCY}! "
            f"Нужно {fmt(total)} {CURRENCY}.",
            parse_mode="HTML",
        )

    update_balance(user_id, -total)
    add_bet_stat(user_id, total)

    # Объединяем одинаковые ставки: "100 чет чет чет" → одна ставка 300 на чет
    from collections import OrderedDict
    merged = OrderedDict()
    for label, numbers in targets:
        if label in merged:
            merged[label] = (merged[label][0] + amount, numbers)
        else:
            merged[label] = (amount, numbers)

    merged_bets = [(amt, label, numbers) for label, (amt, numbers) in merged.items()]

    add_bets(message.chat.id, user_id, merged_bets)

    LAST_BETS[(message.chat.id, user_id)] = (amount, targets)

    who = mention(user_id, name)

    lines = [f"Ставка принята: {who} {fmt(amt)} {CURRENCY} на {label}" for amt, label, _ in merged_bets]
    await send_lines(message, lines)


@router.message(F.text.regexp(r"^\d+\s+\S+"))
async def cmd_bet(message: types.Message):
    parsed = parse_bet_message(message.text)
    if not parsed:
        return  # обычное сообщение, а не ставка

    if message.chat.id in SPINNING:
        return

    amount, targets = parsed
    await place_bets(message, amount, targets, message.from_user.id, message.from_user.first_name)


# ==========================================
# 🔁 ПОВТОРИТЬ / УДВОИТЬ
# ==========================================
async def repeat_bets(callback: types.CallbackQuery, multiplier: int):
    key = (callback.message.chat.id, callback.from_user.id)
    last = LAST_BETS.get(key)

    if not last:
        return await callback.answer("Нет предыдущей ставки", show_alert=True)

    amount, targets = last
    amount *= multiplier

    await callback.answer()
    await place_bets(
        callback.message, amount, targets, callback.from_user.id, callback.from_user.first_name
    )


@router.callback_query(F.data == "roul_repeat")
async def cb_repeat(callback: types.CallbackQuery):
    await repeat_bets(callback, 1)


@router.callback_query(F.data == "roul_double")
async def cb_double(callback: types.CallbackQuery):
    await repeat_bets(callback, 2)


# ==========================================
# ❌ ОТМЕНА СТАВОК
# ==========================================
@router.message(F.text.lower().in_({"отмена", "отменить"}))
async def cmd_cancel(message: types.Message):
    user_id = message.from_user.id
    bets = get_user_bets(message.chat.id, user_id)

    if not bets:
        return

    refund = sum(b["amount"] for b in bets)
    refund_bet(user_id, refund)
    clear_bets(message.chat.id, user_id)

    await message.answer(
        f"Ставки отменены {mention(user_id, message.from_user.first_name)}", parse_mode="HTML"
    )


# ==========================================
# 📋 СПИСОК СТАВОК
# ==========================================
@router.message(F.text.lower() == "ставки")
async def cmd_bets(message: types.Message):
    bets = get_bets(message.chat.id)

    if not bets:
        return await message.answer("Ставок нет")

    lines = [
        f"Ставка: {mention(b['user_id'], get_name(b['user_id']))} {fmt(b['amount'])} {CURRENCY} на {b['label']}"
        for b in bets
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")


# ==========================================
# 📜 ЛОГ ЧИСЕЛ
# ==========================================
@router.message(F.text.lower() == "лог")
async def cmd_log(message: types.Message):
    numbers = get_roulette_log(message.chat.id, 10)

    if not numbers:
        return await message.answer("Лог пуст")

    await message.answer("\n".join(f"{n}{color_emoji(n)}" for n in numbers))


# ==========================================
# 🚀 ЗАПУСК РАУНДА
# ==========================================
@router.message(F.text.lower() == "го")
async def cmd_go(message: types.Message, bot: Bot):
    chat_id = message.chat.id

    if chat_id in SPINNING:
        return

    bets = get_bets(chat_id)
    if not bets:
        return await message.answer("Невозможно начать игру без ставок.")

    # Крутить барабан могут только те, кто поставил в этом раунде
    if message.from_user.id not in {bet["user_id"] for bet in bets}:
        return await message.answer(
            f"{mention(message.from_user.id, message.from_user.first_name)}, "
            f"запустить раунд может только тот, кто сделал ставку.",
            parse_mode="HTML",
        )

    started = get_round_start(chat_id) or time.time()
    left = int(ROUND_DELAY - (time.time() - started))

    if left > 0:
        return await message.answer(f"Ошибка. Закончить раунд можно через {left} секунд")

    SPINNING.add(chat_id)
    try:
        await spin_round(message, bot, bets)
    finally:
        SPINNING.discard(chat_id)


async def spin_round(message: types.Message, bot: Bot, bets: list):
    chat_id = message.chat.id

    # Крутим барабан под гифку
    gif_msg = None
    try:
        gif_msg = await bot.send_animation(chat_id, FSInputFile(GIF_PATH))
    except Exception as e:
        print(f"Не удалось отправить гифку: {e}")

    await asyncio.sleep(random.uniform(3.0, 4.0))

    if gif_msg:
        try:
            await bot.delete_message(chat_id, gif_msg.message_id)
        except Exception:
            pass

    # Число выбирается честно, но так, чтобы выплата не пробила банк бота
    number = pick_number(bets, get_bank())
    add_roulette_log(chat_id, number)

    lines = [f"Рулетка: {number}{color_emoji(number)}"]
    wins = []
    last_by_user = {}

    for bet in bets:
        name = get_name(bet["user_id"])
        who = mention(bet["user_id"], name)
        lines.append(f"{who} {fmt(bet['amount'])} {CURRENCY} на {bet['label']}")

        # Запоминаем ставки для кнопок "Повторить" / "Удвоить"
        target = parse_target(bet["label"])
        if target:
            last_by_user.setdefault((chat_id, bet["user_id"]), [bet["amount"], []])[1].append(target)

        if number in bet["numbers"]:
            prize = payout(bet["amount"], bet["numbers"])
            pay_win(bet["user_id"], prize, chat_id)
            wins.append(
                f"{who} ставка {fmt(bet['amount'])} {CURRENCY} выиграл {fmt(prize)} на {bet['label']}"
            )
        else:
            add_loss(bet["user_id"], bet["amount"])

    for key, (amount, targets) in last_by_user.items():
        LAST_BETS[key] = (amount, targets)

    clear_bets(chat_id)

    if wins:
        lines.append("")
        lines.extend(wins)

    await send_lines(message, lines, markup=result_kb())
