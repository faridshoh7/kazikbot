from aiogram import Router, types, F

from keyboards import BTN_GAMES
from texts import render

router = Router()
# Кнопки меню работают только в личных сообщениях
router.message.filter(F.chat.type == "private")


@router.message(F.text == BTN_GAMES)
async def show_games(message: types.Message):
    text = render("games")
    await message.answer(text, parse_mode="HTML")
