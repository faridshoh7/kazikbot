from aiogram import Router, types, F
from aiogram.filters import Command

from keyboards import BTN_PROFILE
from database import get_user, get_stats_sum, get_user_clan
from utils import fmt
from settings import CURRENCY
from texts import render

router = Router()


@router.message(F.text == BTN_PROFILE, F.chat.type == "private")
@router.message(Command("профиль", "profile", ignore_case=True))
async def show_profile(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)
    clan_data = get_user_clan(user_id)
    clan = clan_data["name"] if clan_data else "-"

    text = render(
        "profile",
        id=user_id,
        balance=fmt(user["balance"]),
        galleons=fmt(user["galleons"]),
        stats=get_stats_sum(user_id),
        clan=clan,
        currency=CURRENCY,
    )
    await message.answer(text, parse_mode="HTML")
