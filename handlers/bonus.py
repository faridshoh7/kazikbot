import time

from aiogram import Router, types, F
from aiogram.filters import Command

from keyboards import BTN_BONUS
from database import get_last_bonus, set_last_bonus, update_balance, get_balance
from utils import fmt
from settings import CURRENCY
from texts import render

router = Router()
# Кнопки меню работают только в личных сообщениях
router.message.filter(F.chat.type == "private")

# Бонус раз в 24 часа
BONUS_AMOUNT = 1000
BONUS_COOLDOWN = 24 * 60 * 60

# Выше этого баланса бонус не выдаётся
BONUS_MAX_BALANCE = 100_000


def time_left(seconds: float) -> str:
    """Оставшееся время в формате ЧЧ:ММ"""
    total_minutes = int(seconds // 60)
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


@router.message(F.text == BTN_BONUS)
@router.message(Command("bonus", ignore_case=True))
async def cmd_bonus(message: types.Message):
    await give_bonus(message)


async def give_bonus(message: types.Message):
    user_id = message.from_user.id
    now = time.time()
    passed = now - get_last_bonus(user_id)

    if passed < BONUS_COOLDOWN:
        return await message.answer(
            f"Следующий бонус будет доступен через {time_left(BONUS_COOLDOWN - passed)}"
        )

    # Бонус — помощь тем, у кого кончились деньги, богатым он не нужен
    if get_balance(user_id) >= BONUS_MAX_BALANCE:
        return await message.answer(
            f"Бонус доступен только при балансе ниже {fmt(BONUS_MAX_BALANCE)} {CURRENCY}"
        )

    update_balance(user_id, BONUS_AMOUNT)
    set_last_bonus(user_id, now)

    await message.answer(
        render(
            "bonus",
            amount=fmt(BONUS_AMOUNT),
            currency=CURRENCY,
            next=time_left(BONUS_COOLDOWN - 60),
        )
    )
