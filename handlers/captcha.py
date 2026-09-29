"""Капча перед бонусом: код с картинки, кнопки «Новый код» и «Отменить»."""

from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import captcha_core
from keyboards import MENU_BUTTONS

router = Router()
# Капчу спрашиваем только в личных сообщениях
router.message.filter(F.chat.type == "private")

ASK_TEXT = "Введите код с картинки:"
WRONG_TEXT = f"Неверный код. Попробуйте ещё раз:\n\n{ASK_TEXT}"


class CaptchaStates(StatesGroup):
    waiting = State()


def captcha_kb() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Новый код", callback_data="captcha:new")
    builder.button(text="❌ Отменить", callback_data="captcha:cancel")
    builder.adjust(2)
    return builder.as_markup()


def code_photo(code: str) -> types.BufferedInputFile:
    return types.BufferedInputFile(captcha_core.draw_code(code).read(), filename="captcha.png")


async def hide_buttons(bot, chat_id: int, message_id: int | None):
    """Снимает кнопки со старой капчи, чтобы не было двух живых кодов."""
    if not message_id:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
    except TelegramBadRequest:
        pass


async def ask_captcha(message: types.Message, state: FSMContext, caption: str = ASK_TEXT):
    """Отправляет новую капчу и ждёт код в ответ."""
    data = await state.get_data()
    await hide_buttons(message.bot, message.chat.id, data.get("captcha_message"))

    code = captcha_core.new_code()
    sent = await message.answer_photo(code_photo(code), caption=caption, reply_markup=captcha_kb())

    await state.set_state(CaptchaStates.waiting)
    await state.update_data(captcha_code=code, captcha_message=sent.message_id)


# ==========================================
# 🔄 НОВЫЙ КОД
# ==========================================
@router.callback_query(F.data == "captcha:new")
async def new_code(call: types.CallbackQuery, state: FSMContext):
    if await state.get_state() != CaptchaStates.waiting.state:
        return await call.answer()

    code = captcha_core.new_code()
    await call.message.edit_media(
        types.InputMediaPhoto(media=code_photo(code), caption=ASK_TEXT),
        reply_markup=captcha_kb(),
    )

    # Активной становится та капча, на которой нажали кнопку
    await state.update_data(captcha_code=code, captcha_message=call.message.message_id)
    await call.answer()


# ==========================================
# ❌ ОТМЕНА
# ==========================================
@router.callback_query(F.data == "captcha:cancel")
async def cancel_captcha(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await call.answer()


# ==========================================
# ✅ ПРОВЕРКА КОДА
# ==========================================
# Кнопки меню и команды пропускаем дальше — иначе из капчи не выйти
@router.message(CaptchaStates.waiting, F.text, ~F.text.startswith("/"), ~F.text.in_(MENU_BUTTONS))
async def check_code(message: types.Message, state: FSMContext):
    data = await state.get_data()
    answer = message.text.strip()

    # Регистр не проверяем: на телефоне его слишком легко потерять
    if answer.lower() != str(data.get("captcha_code", "")).lower():
        return await ask_captcha(message, state, WRONG_TEXT)

    await state.clear()
    await hide_buttons(message.bot, message.chat.id, data.get("captcha_message"))

    # Импорт здесь: бонус сам просит капчу, а через импорт сверху вышло бы кольцо
    from handlers.bonus import give_bonus

    await give_bonus(message)
