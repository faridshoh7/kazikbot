"""Возврат зависших ставок: если раунд не закончили, деньги возвращаются игроку."""

import asyncio

from aiogram import Bot

from database import (
    get_stale_chats,
    get_bets,
    clear_bets,
    get_stale_mines,
    close_mines_game,
    get_stale_joker,
    close_joker_game,
    get_tag,
)
from admin_db import refund_bet
from utils import fmt
from config import BET_TIMEOUT
from settings import CURRENCY

CHECK_EVERY = 30


async def refund_task(bot: Bot):
    """Раз в полминуты проверяет зависшие ставки во всех играх."""
    while True:
        await asyncio.sleep(CHECK_EVERY)
        try:
            await refund_roulette(bot)
            await refund_mines(bot)
            await refund_joker(bot)
        except Exception as e:
            print(f"Ошибка возврата ставок: {e}")


async def notify(bot: Bot, chat_id: int, user_id: int, amount: int, game: str):
    try:
        await bot.send_message(
            chat_id,
            f"{get_tag(user_id)}, ставка {fmt(amount)} {CURRENCY} за игру {game} возвращена",
            parse_mode="HTML",
        )
    except Exception as e:
        print(f"Не удалось сообщить о возврате: {e}")


async def refund_roulette(bot: Bot):
    for chat_id in get_stale_chats(BET_TIMEOUT):
        bets = get_bets(chat_id)
        clear_bets(chat_id)

        # Суммируем ставки каждого игрока, чтобы не спамить по одной
        totals = {}
        for bet in bets:
            totals[bet["user_id"]] = totals.get(bet["user_id"], 0) + bet["amount"]

        for user_id, amount in totals.items():
            refund_bet(user_id, amount)
            await notify(bot, chat_id, user_id, amount, "рулетка")


async def refund_mines(bot: Bot):
    for game in get_stale_mines(BET_TIMEOUT):
        close_mines_game(game["chat_id"], game["message_id"])
        refund_bet(game["user_id"], game["bet"])
        await notify(bot, game["chat_id"], game["user_id"], game["bet"], "минное поле")


async def refund_joker(bot: Bot):
    for game in get_stale_joker(BET_TIMEOUT):
        close_joker_game(game["chat_id"], game["message_id"])
        refund_bet(game["user_id"], game["bet"])
        await notify(bot, game["chat_id"], game["user_id"], game["bet"], "джокер")
