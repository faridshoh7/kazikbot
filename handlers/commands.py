from aiogram import Router, types, F
from aiogram.filters import Command

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


@router.message(Command("rules", ignore_case=True))
async def show_rules(message: types.Message):
    await message.answer("https://teletype.in/@gram_bot/rules_gram", disable_web_page_preview=True)
