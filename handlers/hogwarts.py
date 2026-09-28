from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from keyboards import BTN_HOGWARTS
from database import STATS, get_user, upgrade_price, upgrade_stat
from utils import fmt
from texts import render

router = Router()
# Кнопки меню работают только в личных сообщениях
router.message.filter(F.chat.type == "private")


def stats_text(user_id: int) -> str:
    user = get_user(user_id)
    lines = [f"{title}: {user[key]}" for key, title in STATS.items()]
    return (
        "<b>Твои характеристики</b>\n\n"
        + "\n".join(lines)
        + "\n\nЗдесь ты можешь их прокачать\n\n"
        + f"Баланс: {fmt(user['galleons'])} 🪙"
    )


def stats_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    user = get_user(user_id)
    builder = InlineKeyboardBuilder()

    for key, title in STATS.items():
        level = user[key]
        builder.button(text=title, callback_data="hog_noop")
        builder.button(text=str(level), callback_data="hog_noop")
        builder.button(text=f"+1 за {upgrade_price(level)} 🪙", callback_data=f"hog_up:{key}")

    # Три кнопки в ряд: название / уровень / кнопка прокачки
    builder.adjust(3)
    return builder.as_markup()


# ==========================================
# 🔮 ГЛАВНЫЙ ЭКРАН ХОГВАРТСА
# ==========================================
@router.message(F.text == BTN_HOGWARTS)
async def show_hogwarts(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="Характеристики", callback_data="hog_stats")

    await message.answer(render("hogwarts"), parse_mode="HTML", reply_markup=builder.as_markup())


# ==========================================
# 📊 ЭКРАН ПРОКАЧКИ
# ==========================================
@router.callback_query(F.data == "hog_stats")
async def open_stats(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await callback.message.edit_text(
        stats_text(user_id),
        parse_mode="HTML",
        reply_markup=stats_keyboard(user_id),
    )
    await callback.answer()


# ==========================================
# ⬆️ ПРОКАЧКА ХАРАКТЕРИСТИКИ
# ==========================================
@router.callback_query(F.data.startswith("hog_up:"))
async def do_upgrade(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    stat_key = callback.data.split(":", 1)[1]

    ok, price = upgrade_stat(user_id, stat_key)

    if not ok:
        return await callback.answer(
            f"Недостаточно галеонов! Нужно {fmt(price)} 🪙", show_alert=True
        )

    await callback.message.edit_text(
        stats_text(user_id),
        parse_mode="HTML",
        reply_markup=stats_keyboard(user_id),
    )
    await callback.answer(f"{STATS[stat_key]} прокачан за {fmt(price)} 🪙")


@router.callback_query(F.data == "hog_noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer()
