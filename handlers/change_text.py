"""Команда /change — админ меняет любой текст в меню бота."""

import re

from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from texts import SECTIONS, raw_text, set_text, reset_text, default_text
from handlers.admin import level_of, LEVELS

router = Router()


class ChangeStates(StatesGroup):
    typing = State()


def sections_kb() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, (title, _, _) in SECTIONS.items():
        builder.button(text=title, callback_data=f"chg:{key}")
    # По две кнопки в ряд, как в самом меню
    builder.adjust(2)
    return builder.as_markup()


def section_kb(key: str) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Вернуть стандартный", callback_data=f"chgreset:{key}")
    builder.button(text="❌ Отмена", callback_data="chgcancel")
    builder.adjust(1)
    return builder.as_markup()


def section_view(key: str) -> str:
    """Текст раздела так, как его видит игрок — без HTML-тегов."""
    title, holders, _ = SECTIONS[key]

    text = f"<b>{title}</b>\n\nТекущий текст:\n\n{raw_text(key)}\n"

    if holders:
        text += f"\nМожно вставлять: {' '.join(holders)}\n"

    text += "\nОтправьте новый текст сообщением или нажмите «Отмена»."
    return text


async def show_section(message: types.Message, key: str, edit: bool = False):
    """Показывает раздел. Если в тексте битая разметка — шлём без неё."""
    view = section_view(key)
    send = message.edit_text if edit else message.answer

    try:
        await send(view, parse_mode="HTML", reply_markup=section_kb(key), disable_web_page_preview=True)
    except TelegramBadRequest:
        await send(strip_tags(view), reply_markup=section_kb(key), disable_web_page_preview=True)


def strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


# ==========================================
# 📝 СПИСОК РАЗДЕЛОВ
# ==========================================
@router.message(Command("change", ignore_case=True))
async def cmd_change(message: types.Message, state: FSMContext):
    if level_of(message.from_user.id) < LEVELS["change"]:
        return

    await state.clear()
    await message.answer(
        "Выберите раздел, текст которого хотите изменить:", reply_markup=sections_kb()
    )


@router.callback_query(F.data.startswith("chg:"))
async def cb_section(callback: types.CallbackQuery, state: FSMContext):
    if level_of(callback.from_user.id) < LEVELS["change"]:
        return await callback.answer("Недостаточно прав", show_alert=True)

    key = callback.data.split(":", 1)[1]
    if key not in SECTIONS:
        return await callback.answer()

    await state.set_state(ChangeStates.typing)
    await state.update_data(key=key)

    await show_section(callback.message, key, edit=True)
    await callback.answer()


# ==========================================
# ✍️ НОВЫЙ ТЕКСТ
# ==========================================
@router.message(ChangeStates.typing)
async def cb_new_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("key")

    if key not in SECTIONS:
        await state.clear()
        return

    new_text = message.html_text or message.text or ""

    if not new_text.strip():
        return await message.answer("Текст пустой. Отправьте текст или нажмите «Отмена».")

    set_text(key, new_text)
    await state.clear()

    title = SECTIONS[key][0]
    await message.answer(
        f"✅ Текст раздела <b>{title}</b> изменён.\n\nВот как он теперь выглядит:",
        parse_mode="HTML",
    )
    await message.answer(raw_text(key), parse_mode="HTML")
    await message.answer("Изменить ещё раздел:", reply_markup=sections_kb())


# ==========================================
# 🔄 СБРОС И ОТМЕНА
# ==========================================
@router.callback_query(F.data.startswith("chgreset:"))
async def cb_reset(callback: types.CallbackQuery, state: FSMContext):
    if level_of(callback.from_user.id) < LEVELS["change"]:
        return await callback.answer("Недостаточно прав", show_alert=True)

    key = callback.data.split(":", 1)[1]
    if key not in SECTIONS:
        return await callback.answer()

    reset_text(key)
    await state.clear()

    await callback.message.edit_text(
        f"🔄 Текст раздела <b>{SECTIONS[key][0]}</b> возвращён к стандартному.\n\n"
        f"{default_text(key)}",
        parse_mode="HTML",
        reply_markup=sections_kb(),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data == "chgcancel")
async def cb_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите раздел, текст которого хотите изменить:", reply_markup=sections_kb()
    )
    await callback.answer()
