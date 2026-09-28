import html

from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from keyboards import BTN_TOURNAMENTS
from database import get_tour_top_users, get_tour_top_chats, get_tour_end, get_tour_wins
from utils import fmt
from settings import CURRENCY
from texts import render

router = Router()
# Кнопки меню работают только в личных сообщениях
router.message.filter(F.chat.type == "private")

# Медали для турнира участников: 🥇🥈🥉, дальше просто номер
MEDALS = ["🥇", "🥈", "🥉"]
# Медали для турнира чатов: 🥇🥈🥉, дальше цифры-эмодзи
CHAT_MEDALS = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


def back_kb() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="tour_menu")
    return builder.as_markup()


def menu_kb() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Турнир участников", callback_data="tour_users")
    builder.button(text="Турнир чатов", callback_data="tour_chats")
    builder.adjust(2)
    return builder.as_markup()


# ==========================================
# 🏆 ВЫБОР ТУРНИРА
# ==========================================
@router.message(F.text == BTN_TOURNAMENTS)
async def show_tournaments(message: types.Message):
    await message.answer(render("tournaments"), parse_mode="HTML", reply_markup=menu_kb())


@router.callback_query(F.data == "tour_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(render("tournaments"), parse_mode="HTML", reply_markup=menu_kb())
    await callback.answer()


# ==========================================
# 👥 ТУРНИР УЧАСТНИКОВ
# ==========================================
def users_text(user_id: int) -> str:
    top = get_tour_top_users(10)
    end = get_tour_end("users")

    lines = [f"🏆 <b>Турнир рулетки</b>\n", "<b>Топ-10 игроков:</b>"]

    if not top:
        lines.append("<i>Пока никто не участвует</i>")
    else:
        for i, row in enumerate(top):
            place = MEDALS[i] if i < 3 else f"{i + 1}."
            name = html.escape(row["name"] or "Игрок")
            lines.append(f"{place} {name} - {row['tour_wins']} {CURRENCY}")

    lines.append(f"\n<b>Дата окончания:</b> {end.strftime('%d.%m %H:%M')}")
    lines.append(f"\n<b>Ваша сумма выигрышей:</b> {get_tour_wins(user_id)} {CURRENCY}")

    return "\n".join(lines)


@router.callback_query(F.data == "tour_users")
async def tour_users(callback: types.CallbackQuery):
    await callback.message.edit_text(
        users_text(callback.from_user.id), parse_mode="HTML", reply_markup=back_kb()
    )
    await callback.answer()


# ==========================================
# 💬 ТУРНИР ЧАТОВ
# ==========================================
def chats_text() -> str:
    top = get_tour_top_chats(10)
    end = get_tour_end("chats")

    lines = [f"🏆 <b>Турнир чатов</b>\n", "<b>Топ-10 чатов:</b>"]

    if not top:
        lines.append("<i>Пока никто не участвует</i>")
    else:
        for i, row in enumerate(top):
            place = CHAT_MEDALS[i] if i < len(CHAT_MEDALS) else f"{i + 1}."
            title = html.escape(row["title"] or "Чат")
            if row["link"]:
                title = f'<a href="{row["link"]}">{title}</a>'
            lines.append(f"{place} {title} — {fmt(row['tour_wins'])} {CURRENCY}")

    lines.append(f"\n<b>Дата окончания:</b> {end.strftime('%d.%m %H:%M')}")

    return "\n".join(lines)


@router.callback_query(F.data == "tour_chats")
async def tour_chats(callback: types.CallbackQuery):
    await callback.message.edit_text(
        chats_text(), parse_mode="HTML", reply_markup=back_kb(), disable_web_page_preview=True
    )
    await callback.answer()
