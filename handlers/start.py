from aiogram import Router, types, F, Bot
from aiogram.filters import CommandStart, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from keyboards import main_menu, BTN_CHATS, BTN_POLICY, BTN_LANG
from database import init_user
from handlers.bonus import give_bonus
from settings import CURRENCY
from texts import render

router = Router()
# Кнопки меню работают только в личных сообщениях
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def cmd_start(message: types.Message, bot: Bot, command: CommandObject = None):
    init_user(message.from_user.id)

    # Пришёл по кнопке "Бонус" из чата — сразу выдаём бонус
    if command and command.args == "bonus":
        return await give_bonus(message)
    bot_info = await bot.get_me()
    add_url = f"https://t.me/{bot_info.username}?startgroup=true"

    text = render("start", currency=CURRENCY, link=add_url)

    await message.answer(text, parse_mode="HTML", reply_markup=main_menu())


# ==========================================
# 💬 ЧАТЫ
# ==========================================
@router.message(F.text == BTN_CHATS)
async def show_chats(message: types.Message):
    text = render("chats", currency=CURRENCY)
    await message.answer(text, parse_mode="HTML")


# ==========================================
# 📄 ПОЛИТИКА
# ==========================================
@router.message(F.text == BTN_POLICY)
async def show_policy(message: types.Message):
    await message.answer(render("policy"), disable_web_page_preview=True)


# ==========================================
# 🌐 ИЗМЕНИТЬ ЯЗЫК
# ==========================================
@router.message(F.text == BTN_LANG)
async def show_lang(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="Украiнська", callback_data="lang_none")
    builder.button(text="English", callback_data="lang_none")
    builder.button(text="Русский", callback_data="lang_ru")
    builder.adjust(3)

    await message.answer(render("lang"), reply_markup=builder.as_markup())


@router.callback_query(F.data == "lang_ru")
async def set_lang_ru(callback: types.CallbackQuery):
    await callback.answer("Выбран русский язык")


@router.callback_query(F.data == "lang_none")
async def set_lang_none(callback: types.CallbackQuery):
    # Украинский и английский пока не поддерживаются — кнопка молчит
    await callback.answer()
