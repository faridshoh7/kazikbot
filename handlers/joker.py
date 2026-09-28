import re
import secrets

from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import (
    get_balance,
    update_balance,
    get_rtp,
    add_history,
    save_joker_game,
    get_joker_game,
    update_joker_game,
    close_joker_game,
)
from admin_db import add_bet_stat, add_loss, pay_win, get_bank, refund_bet
from utils import fmt, mention, coef_text
from settings import CURRENCY

router = Router()
# Игры работают только в чатах, в личке их нет
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

# В каждом ряду 3 карты, одна из них — череп
COLS = 3
# Больше этого числа рядов не открыть — выигрыш забирается автоматически
MAX_ROWS = 15

rnd = secrets.SystemRandom()

CARD_BACK = "🎴"
CARD_SAFE = "🃏"
CARD_SKULL = "💀"

# Коэффициенты по шагам, дальше растут по честной формуле 3/2
BASE_COEFS = [1.33, 1.81, 2.45, 3.6, 5.1, 8.3]


def coef(step: int) -> float:
    """Коэффициент после step угаданных рядов."""
    if step <= 0:
        return 0.0

    if step <= len(BASE_COEFS):
        value = BASE_COEFS[step - 1]
    else:
        value = BASE_COEFS[-1] * (COLS / (COLS - 1)) ** (step - len(BASE_COEFS))

    return round(value, 2)


def new_skull() -> int:
    return rnd.randrange(COLS)


def field_kb(game: dict, reveal_rows: int = None) -> types.InlineKeyboardMarkup:
    """Открытые ряды сверху, активный ряд закрытых карт снизу.

    reveal_rows задаёт, сколько рядов показать открытыми (при проигрыше — вместе
    с тем рядом, где попался череп); активный ряд при этом не рисуется.
    """
    builder = InlineKeyboardBuilder()
    rows_done = len(game["picks"]) if reveal_rows is None else reveal_rows

    for i in range(rows_done):
        for col in range(COLS):
            text = CARD_SKULL if col == game["skulls"][i] else CARD_SAFE
            builder.button(text=text, callback_data="joker_noop")

    if reveal_rows is None:
        for col in range(COLS):
            builder.button(text=CARD_BACK, callback_data=f"joker_open:{game['message_id']}:{col}")

    builder.adjust(*[COLS] * (rows_done + (0 if reveal_rows is not None else 1)))

    if reveal_rows is None:
        if game["picks"]:
            builder.row(
                types.InlineKeyboardButton(
                    text="💸 Забрать выигрыш",
                    callback_data=f"joker_cash:{game['message_id']}",
                    style="success",
                )
            )
        else:
            builder.row(
                types.InlineKeyboardButton(
                    text="❌",
                    callback_data=f"joker_cash:{game['message_id']}",
                    style="danger",
                )
            )

    return builder.as_markup()


def game_text(game: dict, name: str) -> str:
    who = mention(game["user_id"], name)
    steps = len(game["picks"])

    text = f"{who}, вы начали игру джокер!\n💰Ставка: {fmt(game['bet'])} {CURRENCY}"

    if steps == 0:
        return text

    k = coef(steps)
    prize = int(game["bet"] * k)
    return text + f"\n💵Выигрыш: {coef_text(k)} | {fmt(prize)} {CURRENCY}"


# ==========================================
# 🃏 СТАРТ ИГРЫ
# ==========================================
@router.message(F.text.regexp(r"(?i)^джокер\s+(\d+)$").as_("match"))
async def cmd_joker(message: types.Message, match: re.Match):
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

    game = {
        "message_id": 0,
        "user_id": user_id,
        "bet": bet,
        "skulls": [new_skull()],
        "picks": [],
    }

    sent = await message.answer(game_text(game, message.from_user.first_name), parse_mode="HTML")

    game["message_id"] = sent.message_id
    save_joker_game(message.chat.id, sent.message_id, user_id, bet, game["skulls"], [])

    await sent.edit_reply_markup(reply_markup=field_kb(game))


# ==========================================
# 🔓 ВЫБОР КАРТЫ
# ==========================================
@router.callback_query(F.data.startswith("joker_open:"))
async def cb_open(callback: types.CallbackQuery):
    _, message_id, col = callback.data.split(":")
    chat_id = callback.message.chat.id
    message_id = int(message_id)
    game = get_joker_game(chat_id, message_id)

    if not game:
        return await callback.answer("Игра уже завершена", show_alert=True)

    if callback.from_user.id != game["user_id"]:
        return await callback.answer("Это не ваша игра!", show_alert=True)

    col = int(col)
    row = len(game["picks"])
    name = callback.from_user.first_name

    rtp = get_rtp("joker")
    hit = col == game["skulls"][row]

    # RTP ниже 1 — часть удачных карт становится черепом, выше 1 — наоборот
    if not hit and rtp < 1 and rnd.random() > rtp:
        hit = True
    elif hit and rtp > 1 and rnd.random() < (rtp - 1):
        hit = False

    # Банк не потянет следующую выплату — карта становится черепом
    if not hit and int(game["bet"] * coef(row + 1)) > get_bank():
        hit = True

    # Череп переносим на выбранную карту, чтобы картинка сходилась с исходом
    if hit:
        game["skulls"][row] = col
    elif col == game["skulls"][row]:
        game["skulls"][row] = rnd.choice([c for c in range(COLS) if c != col])

    # Попал на череп — игра окончена
    if hit:
        add_loss(game["user_id"], game["bet"])
        add_history(game["user_id"], "joker", -game["bet"])
        close_joker_game(chat_id, message_id)
        await callback.message.edit_text(
            f"{mention(game['user_id'], name)}, вы проиграли!\n"
            f"💰Ставка: {fmt(game['bet'])} {CURRENCY}",
            parse_mode="HTML",
            reply_markup=field_kb(game, reveal_rows=row + 1),
        )
        return await callback.answer()

    game["picks"].append(col)
    game["skulls"].append(new_skull())
    update_joker_game(chat_id, message_id, game["skulls"], game["picks"])

    # Дальше рядов нет — забираем выигрыш автоматически
    if len(game["picks"]) >= MAX_ROWS:
        return await cash_out(callback, game, chat_id, name)

    await callback.message.edit_text(
        game_text(game, name), parse_mode="HTML", reply_markup=field_kb(game)
    )
    await callback.answer()


# ==========================================
# 💸 ЗАБРАТЬ ВЫИГРЫШ
# ==========================================
async def cash_out(callback: types.CallbackQuery, game: dict, chat_id: int, name: str):
    steps = len(game["picks"])
    prize = int(game["bet"] * coef(steps))

    close_joker_game(chat_id, game["message_id"])
    pay_win(game["user_id"], prize, chat_id)
    add_history(game["user_id"], "joker", prize)

    await callback.message.edit_text(
        f"{mention(game['user_id'], name)}, вы забрали выигрыш!\n"
        f"💰Сумма: {fmt(prize)} {CURRENCY}",
        parse_mode="HTML",
        reply_markup=field_kb(game, reveal_rows=steps),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("joker_cash:"))
async def cb_cash(callback: types.CallbackQuery):
    message_id = int(callback.data.split(":")[1])
    chat_id = callback.message.chat.id
    game = get_joker_game(chat_id, message_id)

    if not game:
        return await callback.answer("Игра уже завершена", show_alert=True)

    if callback.from_user.id != game["user_id"]:
        return await callback.answer("Это не ваша игра!", show_alert=True)

    # Ни одной карты не открыто — отменяем игру и возвращаем ставку
    if not game["picks"]:
        close_joker_game(chat_id, message_id)
        refund_bet(game["user_id"], game["bet"])
        await callback.message.edit_text(
            f"{mention(game['user_id'], callback.from_user.first_name)}, игра отменена!\n"
            f"💰Ставка возвращена: {fmt(game['bet'])} {CURRENCY}",
            parse_mode="HTML",
        )
        return await callback.answer()

    await cash_out(callback, game, chat_id, callback.from_user.first_name)


@router.callback_query(F.data == "joker_noop")
async def cb_noop(callback: types.CallbackQuery):
    await callback.answer()
