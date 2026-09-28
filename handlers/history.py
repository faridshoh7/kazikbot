from datetime import datetime

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from admin_db import get_transfers, get_duel_history
from database import get_name
from utils import fmt

router = Router()

HISTORY_LIMIT = 20


def stamp(ts: float, brackets: str = "[]") -> str:
    return f"{brackets[0]}{datetime.fromtimestamp(ts).strftime('%d.%m.%Y %H:%M')}{brackets[1]}"


def history_kb() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💸Переводы", callback_data="hist_transfers")
    builder.button(text="⚔️Дуэли", callback_data="hist_duels")
    builder.adjust(2)
    return builder.as_markup()


@router.message(Command("история", "history", ignore_case=True))
async def cmd_history(message: types.Message):
    await message.answer("Выберите историю, которую хотите просмотреть", reply_markup=history_kb())


# ==========================================
# 💸 ПЕРЕВОДЫ
# ==========================================
@router.callback_query(F.data == "hist_transfers")
async def cb_transfers(callback: types.CallbackQuery):
    rows = get_transfers(callback.from_user.id, HISTORY_LIMIT)

    if not rows:
        await callback.message.edit_text("Переводов пока нет", reply_markup=history_kb())
        return await callback.answer()

    lines = []
    for row in rows:
        partner = get_name(row["partner_id"]) if row["partner_id"] else "—"
        if row["amount"] >= 0:
            lines.append(f"{stamp(row['created_at'])} ➕ {abs(row['amount'])} ◀️ {partner}")
        else:
            lines.append(f"{stamp(row['created_at'])} ➖ {abs(row['amount'])} ▶️ {partner}")

    await callback.message.edit_text("\n".join(lines), reply_markup=history_kb())
    await callback.answer()


# ==========================================
# ⚔️ ДУЭЛИ
# ==========================================
@router.callback_query(F.data == "hist_duels")
async def cb_duels(callback: types.CallbackQuery):
    rows = get_duel_history(callback.from_user.id, HISTORY_LIMIT)

    if not rows:
        await callback.message.edit_text("Дуэлей пока нет", reply_markup=history_kb())
        return await callback.answer()

    blocks = []
    for row in rows:
        rival = get_name(row["opponent_id"])
        result = "одержали победу" if row["is_win"] else "потерпели поражение"
        blocks.append(
            f"{stamp(row['created_at'], '()')}\n"
            f"Вы напали на {rival} и {result}.\n"
            f"Ваша награда: 🪙{fmt(row['galleons']) if row['is_win'] else 0}"
        )

    await callback.message.edit_text("\n\n".join(blocks), reply_markup=history_kb())
    await callback.answer()
