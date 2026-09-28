import html

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from keyboards import BTN_CLANS
from database import (
    CLAN_PRICE,
    get_balance,
    update_balance,
    create_clan,
    get_clan,
    get_clan_by_name,
    search_clans,
    count_clans,
    get_clans_page,
    get_top_clans,
    count_clan_members,
    set_user_clan,
    get_user_clan,
)
from utils import fmt
from settings import CURRENCY
from texts import render

router = Router()
# Кнопки меню работают только в личных сообщениях
router.message.filter(F.chat.type == "private")

PER_PAGE = 6


class ClanStates(StatesGroup):
    creating = State()
    searching = State()


# ==========================================
# 🏰 ГЛАВНОЕ МЕНЮ КЛАНОВ
# ==========================================
def clans_kb() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🆕 Создать клан", callback_data="clan_create")
    builder.button(text="📩 Мои приглашения", callback_data="clan_invites")
    builder.button(text="🔍 Поиск клана", callback_data="clan_search")
    builder.button(text="📜 Список кланов", callback_data="clan_list:1")
    builder.button(text="🏆 Топ кланов", callback_data="clan_top")
    builder.adjust(1)
    return builder.as_markup()


def back_kb() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="clan_menu")
    return builder.as_markup()


@router.message(F.text == BTN_CLANS)
async def show_clans(message: types.Message):
    await message.answer(render("clans"), reply_markup=clans_kb())


@router.callback_query(F.data == "clan_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(render("clans"), reply_markup=clans_kb())
    await callback.answer()


# ==========================================
# 🆕 СОЗДАНИЕ КЛАНА
# ==========================================
@router.callback_query(F.data == "clan_create")
async def clan_create(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    if get_user_clan(user_id):
        return await callback.answer("Вы уже состоите в клане!", show_alert=True)

    if get_balance(user_id) < CLAN_PRICE:
        return await callback.answer(
            f"Создание клана стоит {fmt(CLAN_PRICE)} {CURRENCY}. Недостаточно средств!",
            show_alert=True,
        )

    await state.set_state(ClanStates.creating)
    await callback.message.edit_text(
        f"Введите название клана\n\nСтоимость создания: {fmt(CLAN_PRICE)} {CURRENCY}",
        reply_markup=back_kb(),
    )
    await callback.answer()


@router.message(ClanStates.creating)
async def process_clan_name(message: types.Message, state: FSMContext):
    name = (message.text or "").strip()
    user_id = message.from_user.id

    if not name or len(name) > 32:
        return await message.answer("Название должно быть от 1 до 32 символов.", reply_markup=back_kb())

    if get_clan_by_name(name):
        return await message.answer("Клан с таким названием уже существует!", reply_markup=back_kb())

    if get_balance(user_id) < CLAN_PRICE:
        await state.clear()
        return await message.answer(
            f"Недостаточно {CURRENCY}! Нужно {fmt(CLAN_PRICE)} {CURRENCY}.", reply_markup=back_kb()
        )

    update_balance(user_id, -CLAN_PRICE)
    clan_id = create_clan(name, user_id)
    await state.clear()

    if not clan_id:
        update_balance(user_id, CLAN_PRICE)
        return await message.answer(
            "Не удалось создать клан, попробуйте другое название.", reply_markup=back_kb()
        )

    await message.answer(
        f"🏰 Клан <b>{html.escape(name)}</b> создан!\n\n"
        f"Списано: {fmt(CLAN_PRICE)} {CURRENCY}\n"
        f"Вы стали его главой.",
        parse_mode="HTML",
        reply_markup=back_kb(),
    )


# ==========================================
# 📩 МОИ ПРИГЛАШЕНИЯ
# ==========================================
@router.callback_query(F.data == "clan_invites")
async def clan_invites(callback: types.CallbackQuery):
    await callback.message.edit_text("У вас нет приглашений", reply_markup=back_kb())
    await callback.answer()


# ==========================================
# 🔍 ПОИСК КЛАНА
# ==========================================
@router.callback_query(F.data == "clan_search")
async def clan_search(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ClanStates.searching)
    await callback.message.edit_text("Введите название клана для поиска", reply_markup=back_kb())
    await callback.answer()


@router.message(ClanStates.searching)
async def process_clan_search(message: types.Message, state: FSMContext):
    query = (message.text or "").strip()
    await state.clear()

    found = search_clans(query)

    if not found:
        return await message.answer("Клан с таким названием не найден", reply_markup=back_kb())

    builder = InlineKeyboardBuilder()
    for clan in found:
        members = count_clan_members(clan["clan_id"])
        builder.button(
            text=f"{clan['name']} | {fmt(clan['balance'])} {CURRENCY} | {members} 👥",
            callback_data=f"clan_join:{clan['clan_id']}",
        )
    builder.button(text="🔙 Назад", callback_data="clan_menu")
    builder.adjust(1)

    await message.answer("Выберите клан, в который хотите вступить", reply_markup=builder.as_markup())


# ==========================================
# 📜 СПИСОК КЛАНОВ
# ==========================================
def list_kb(page: int) -> types.InlineKeyboardMarkup:
    total = count_clans()
    last_page = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, last_page))

    builder = InlineKeyboardBuilder()
    for clan in get_clans_page(page, PER_PAGE):
        members = count_clan_members(clan["clan_id"])
        builder.button(
            text=f"{clan['name']} | {fmt(clan['balance'])} {CURRENCY} | {members} 👥",
            callback_data=f"clan_join:{clan['clan_id']}",
        )
    builder.adjust(1)

    # Навигация: [1] [<] [текущая] [>] [последняя]
    nav = InlineKeyboardBuilder()
    nav.button(text="1", callback_data="clan_list:1")
    nav.button(text="<", callback_data=f"clan_list:{max(1, page - 1)}")
    nav.button(text=str(page), callback_data="clan_noop")
    nav.button(text=">", callback_data=f"clan_list:{min(last_page, page + 1)}")
    nav.button(text=str(last_page), callback_data=f"clan_list:{last_page}")
    nav.adjust(5)

    builder.attach(nav)
    builder.row(types.InlineKeyboardButton(text="🔙 Назад", callback_data="clan_menu"))
    return builder.as_markup()


@router.callback_query(F.data.startswith("clan_list:"))
async def clan_list(callback: types.CallbackQuery):
    page = int(callback.data.split(":", 1)[1])

    if count_clans() == 0:
        await callback.message.edit_text("Пока не создано ни одного клана", reply_markup=back_kb())
        return await callback.answer()

    await callback.message.edit_text(
        "Выберите клан, в который хотите вступить", reply_markup=list_kb(page)
    )
    await callback.answer()


# ==========================================
# ➕ ВСТУПЛЕНИЕ В КЛАН
# ==========================================
@router.callback_query(F.data.startswith("clan_join:"))
async def clan_join(callback: types.CallbackQuery):
    clan_id = int(callback.data.split(":", 1)[1])
    clan = get_clan(clan_id)

    if not clan:
        return await callback.answer("Клан не найден", show_alert=True)

    user_clan = get_user_clan(callback.from_user.id)
    if user_clan:
        if user_clan["clan_id"] == clan_id:
            return await callback.answer("Вы уже состоите в этом клане", show_alert=True)
        return await callback.answer("Вы уже состоите в клане!", show_alert=True)

    set_user_clan(callback.from_user.id, clan_id)
    await callback.answer(f"Вы вступили в клан {clan['name']}!", show_alert=True)


# ==========================================
# 🏆 ТОП КЛАНОВ
# ==========================================
@router.callback_query(F.data == "clan_top")
async def clan_top(callback: types.CallbackQuery):
    top = get_top_clans(30)

    if not top:
        await callback.message.edit_text("Пока не создано ни одного клана", reply_markup=back_kb())
        return await callback.answer()

    lines = []
    for i, clan in enumerate(top, start=1):
        members = count_clan_members(clan["clan_id"])
        lines.append(f"{i}. {html.escape(clan['name'])} | 👤 {members} | 💰 {clan['total_won']}")

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=back_kb())
    await callback.answer()


@router.callback_query(F.data == "clan_noop")
async def clan_noop(callback: types.CallbackQuery):
    await callback.answer()
