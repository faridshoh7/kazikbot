import re
import secrets

from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import (
    get_balance,
    update_balance,
    get_rtp,
    add_history,
    save_mines_game,
    get_mines_game,
    update_mines_opened,
    close_mines_game,
)
from admin_db import add_bet_stat, add_loss, pay_win, get_bank, refund_bet
from utils import fmt, mention, coef_text
from settings import CURRENCY

router = Router()
# Игры работают только в чатах, в личке их нет
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

# Поле 5x5, из них 5 мин
SIZE = 5
CELLS = SIZE * SIZE
MINES_COUNT = 5
SAFE_CELLS = CELLS - MINES_COUNT

# Первые три коэффициента заданы вручную, дальше растут по честной формуле
BASE_COEFS = [1.28, 1.65, 2.1]

rnd = secrets.SystemRandom()


def coef(step: int) -> float:
    """Коэффициент после step удачных открытий."""
    if step <= 0:
        return 0.0

    if step <= len(BASE_COEFS):
        value = BASE_COEFS[step - 1]
    else:
        value = BASE_COEFS[-1]
        for k in range(len(BASE_COEFS), step):
            value *= (CELLS - k) / (SAFE_CELLS - k)

    return round(value, 2)


def field_kb(game: dict, reveal: bool = False) -> types.InlineKeyboardMarkup:
    """Поле кнопок. reveal=True показывает все мины и убирает нижнюю кнопку."""
    builder = InlineKeyboardBuilder()
    mines = set(game["mines"])
    opened = set(game["opened"])

    for i in range(CELLS):
        if reveal:
            text = "💣" if i in mines else " "
            data = "mines_noop"
        elif i in opened:
            text = " "
            data = "mines_noop"
        else:
            text = "❓"
            data = f"mines_open:{game['message_id']}:{i}"
        builder.button(text=text, callback_data=data)

    builder.adjust(*[SIZE] * SIZE)

    if not reveal:
        if opened:
            builder.row(
                types.InlineKeyboardButton(
                    text="💸 Забрать выигрыш",
                    callback_data=f"mines_cash:{game['message_id']}",
                    style="success",
                )
            )
        else:
            builder.row(
                types.InlineKeyboardButton(
                    text="❌",
                    callback_data=f"mines_cash:{game['message_id']}",
                    style="danger",
                )
            )

    return builder.as_markup()


def game_text(game: dict, name: str) -> str:
    who = mention(game["user_id"], name)
    steps = len(game["opened"])

    text = f"{who}, вы начали игру минное поле!\n"

    if steps == 0:
        return text + f"💰Ставка: {fmt(game['bet'])} {CURRENCY}"

    k = coef(steps)
    prize = int(game["bet"] * k)
    return (
        text
        + f"💰Ставка: {fmt(game['bet'])}\n"
        + f"💵Выигрыш: {coef_text(k)} | {fmt(prize)} {CURRENCY}"
    )


# ==========================================
# 💣 СТАРТ ИГРЫ
# ==========================================
@router.message(F.text.regexp(r"(?i)^мины\s+(\d+)$").as_("match"))
async def cmd_mines(message: types.Message, match: re.Match):
    bet = int(match.group(1))
    user_id = message.from_user.id

    if bet <= 0:
        return

    if get_balance(user_id) < bet:
        return await message.answer(
            f"{mention(user_id, message.from_user.first_name)}, недостаточно {CURRENCY}!",
            parse_mode="HTML",
        )

    update_balance(user_id, -bet)
    add_bet_stat(user_id, bet)

    mines = sorted(secrets.SystemRandom().sample(range(CELLS), MINES_COUNT))
    game = {"message_id": 0, "user_id": user_id, "bet": bet, "mines": mines, "opened": []}

    sent = await message.answer(
        game_text(game, message.from_user.first_name), parse_mode="HTML"
    )

    game["message_id"] = sent.message_id
    save_mines_game(message.chat.id, sent.message_id, user_id, bet, mines, [])

    await sent.edit_reply_markup(reply_markup=field_kb(game))


# ==========================================
# 🔓 ОТКРЫТИЕ КЛЕТКИ
# ==========================================
@router.callback_query(F.data.startswith("mines_open:"))
async def cb_open(callback: types.CallbackQuery):
    _, message_id, index = callback.data.split(":")
    chat_id = callback.message.chat.id
    game = get_mines_game(chat_id, int(message_id))

    if not game:
        return await callback.answer("Игра уже завершена", show_alert=True)

    if callback.from_user.id != game["user_id"]:
        return await callback.answer("Это не ваша игра!", show_alert=True)

    index = int(index)
    if index in game["opened"]:
        return await callback.answer()

    name = callback.from_user.first_name
    rtp = get_rtp("mines")
    steps = len(game["opened"])

    hit = index in game["mines"]

    # RTP ниже 1 — часть удачных клеток превращается в мины, выше 1 — наоборот
    if not hit and rtp < 1 and rnd.random() > rtp:
        hit = True
    elif hit and rtp > 1 and rnd.random() < (rtp - 1):
        hit = False

    # Банк не потянет следующую выплату — клетка становится миной
    if not hit and int(game["bet"] * coef(steps + 1)) > get_bank():
        hit = True

    # Держим на поле ровно MINES_COUNT мин, чтобы картинка сходилась с исходом
    if hit and index not in game["mines"]:
        spare = [m for m in game["mines"] if m != index]
        game["mines"] = sorted(spare[1:] + [index])
    elif not hit and index in game["mines"]:
        free = [c for c in range(CELLS) if c not in game["mines"] and c not in game["opened"] and c != index]
        game["mines"] = sorted([m for m in game["mines"] if m != index] + [rnd.choice(free)])

    # Попал на мину — игра окончена
    if hit:
        add_loss(game["user_id"], game["bet"])
        add_history(game["user_id"], "mines", -game["bet"])
        close_mines_game(chat_id, int(message_id))
        await callback.message.edit_text(
            f"{mention(game['user_id'], name)},игра завершена!\n💵Вы проиграли",
            parse_mode="HTML",
            reply_markup=field_kb(game, reveal=True),
        )
        return await callback.answer()

    game["opened"].append(index)
    update_mines_opened(chat_id, int(message_id), game["opened"], game["mines"])

    # Открыл все безопасные клетки — автоматическая выплата
    if len(game["opened"]) >= SAFE_CELLS:
        return await cash_out(callback, game, chat_id, name)

    await callback.message.edit_text(
        game_text(game, name), parse_mode="HTML", reply_markup=field_kb(game)
    )
    await callback.answer()


# ==========================================
# 💸 ЗАБРАТЬ ВЫИГРЫШ
# ==========================================
async def cash_out(callback: types.CallbackQuery, game: dict, chat_id: int, name: str):
    steps = len(game["opened"])
    prize = int(game["bet"] * coef(steps))

    close_mines_game(chat_id, game["message_id"])
    pay_win(game["user_id"], prize, chat_id)
    add_history(game["user_id"], "mines", prize)

    await callback.message.edit_text(
        f"{mention(game['user_id'], name)}, вы забрали выигрыш!\n"
        f"💰Сумма: {fmt(prize)} {CURRENCY}",
        parse_mode="HTML",
        reply_markup=field_kb(game, reveal=True),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mines_cash:"))
async def cb_cash(callback: types.CallbackQuery):
    message_id = int(callback.data.split(":")[1])
    chat_id = callback.message.chat.id
    game = get_mines_game(chat_id, message_id)

    if not game:
        return await callback.answer("Игра уже завершена", show_alert=True)

    if callback.from_user.id != game["user_id"]:
        return await callback.answer("Это не ваша игра!", show_alert=True)

    # Ни одной клетки не открыто — просто отменяем игру и возвращаем ставку
    if not game["opened"]:
        close_mines_game(chat_id, message_id)
        refund_bet(game["user_id"], game["bet"])
        await callback.message.edit_text(
            f"{mention(game['user_id'], callback.from_user.first_name)}, игра отменена!\n"
            f"💰Ставка возвращена: {fmt(game['bet'])} {CURRENCY}",
            parse_mode="HTML",
        )
        return await callback.answer()

    await cash_out(callback, game, chat_id, callback.from_user.first_name)


@router.callback_query(F.data == "mines_noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()
