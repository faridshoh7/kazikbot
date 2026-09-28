from aiogram import Router, types, F

from keyboards import BTN_COMMANDS
from settings import CURRENCY
from texts import render

router = Router()
# Кнопки меню работают только в личных сообщениях
router.message.filter(F.chat.type == "private")


@router.message(F.text == BTN_COMMANDS)
async def show_commands(message: types.Message):
    text = render("commands", currency=CURRENCY)
    await message.answer(text, parse_mode="HTML")
