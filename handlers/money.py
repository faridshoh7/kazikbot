import html
import re
import time

from aiogram import Router, types, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import (
    get_user,
    get_balance,
    update_balance,
    update_user_name,
    add_history,
    get_last_bonus,
    get_name,
)
from admin_db import find_user
from utils import fmt, mention, profile_link
from settings import CURRENCY
from handlers.bonus import BONUS_COOLDOWN, BONUS_MAX_BALANCE

router = Router()


# ==========================================
# 💰 БАЛАНС
# ==========================================
@router.message(F.text.lower().in_({"б", "баланс"}))
async def cmd_balance(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    user = get_user(user_id)

    text = (
        f"{mention(user_id, message.from_user.first_name)}\n"
        f"💰 Баланс: <b>{fmt(user['balance'])}</b> {CURRENCY}"
    )

    # Бонус готов — показываем кнопку, которая ведёт в личку бота.
    # В самой личке кнопка не нужна, там есть меню
    markup = None
    bonus_ready = (
        time.time() - get_last_bonus(user_id) >= BONUS_COOLDOWN
        and user["balance"] < BONUS_MAX_BALANCE
    )

    if message.chat.type != "private" and bonus_ready:
        bot_info = await bot.get_me()
        builder = InlineKeyboardBuilder()
        builder.button(text="🎁Бонус", url=f"https://t.me/{bot_info.username}?start=bonus")
        markup = builder.as_markup()

    await message.answer(text, parse_mode="HTML", reply_markup=markup)


# ==========================================
# 💸 ПЕРЕВОД МОНЕТ
# ==========================================
@router.message(F.text.regexp(r"(?i)^п\s+(\d+)(?:\s+(\d+))?(?:\s+(.+))?$", flags=re.S).as_("match"))
async def cmd_transfer(message: types.Message, match: re.Match, bot: Bot):
    sender = message.from_user
    first, second, note = match.group(1), match.group(2), match.group(3)
    by_id = bool(second)

    # Комментарий к переводу — необязательный
    comment = ""
    if note:
        note = note.strip()[:200]
        if note:
            comment = f"\n💬 {html.escape(note)}"

    # "п id сумма" — получатель указан числом, иначе берём того, кому отвечаем
    if by_id:
        target_id, amount = int(first), int(second)
        target = find_user(str(target_id))
        if not target:
            return await message.answer("Игрок с таким ID не найден")
        target_name = target["name"]
        target_username = target["username"]
    else:
        if not message.reply_to_message:
            return await message.answer(
                "Переведите в ответ на сообщение игрока или укажите ID: <code>п id сумма</code>",
                parse_mode="HTML",
            )
        rival = message.reply_to_message.from_user
        target_id, amount = rival.id, int(first)
        target_name = rival.first_name
        target_username = rival.username or ""
        update_user_name(target_id, rival.first_name, target_username)

    if amount <= 0:
        return

    if target_id == sender.id:
        return await message.answer("Нельзя переводить самому себе")

    if get_balance(sender.id) < amount:
        return await message.answer(
            f"{mention(sender.id, sender.first_name)}, недостаточно {CURRENCY}!", parse_mode="HTML"
        )

    update_balance(sender.id, -amount)
    update_balance(target_id, amount)

    add_history(sender.id, "transfer", -amount, target_id)
    add_history(target_id, "transfer", amount, sender.id)

    who = mention(sender.id, sender.first_name)

    if by_id:
        # Перевод по ID: получателя показываем ссылкой на его профиль
        to_whom = profile_link(target_id, target_name, target_username)

        # и отдельно сообщаем ему самому в личку
        try:
            await bot.send_message(
                target_id,
                f"Вы получили перевод {fmt(amount)} {CURRENCY} от {who}{comment}",
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        to_whom = mention(target_id, target_name)

    await message.answer(
        f"{who} перевел {fmt(amount)} {CURRENCY} для {to_whom}{comment}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


# ==========================================
# 🏆 ТОП ЧАТА
# ==========================================
@router.message(Command("top", ignore_case=True))
async def cmd_top(message: types.Message, command: CommandObject):
    from admin_db import get_chat_top

    if message.chat.type == "private":
        return await message.answer("Топ доступен только в чатах")

    limit = 10
    if command.args and command.args.strip().isdigit():
        limit = max(1, min(50, int(command.args.strip())))

    top = get_chat_top(message.chat.id, limit)

    if not top:
        return await message.answer("В этом чате пока никто не играл")

    lines = [f"🏆 <b>Топ игроков чата:</b>\n"]
    for i, row in enumerate(top, start=1):
        who = mention(row["user_id"], row["name"] or "Игрок")
        lines.append(f"{i}. {who} — {fmt(row['balance'])} {CURRENCY}")

    await message.answer("\n".join(lines), parse_mode="HTML")
