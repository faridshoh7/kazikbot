import asyncio
import re
import time

from aiogram import Bot, Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import (
    get_balance,
    update_balance,
    update_user_name,
    get_treasury,
    open_treasury,
    add_treasury,
    set_treasury_reward,
    pay_from_treasury,
    register_invite,
)
from admin_db import add_bank
from utils import fmt, mention, profile_link
from settings import CURRENCY

router = Router()
# Казна работает только в группах
router.message.filter(F.chat.type.in_({"group", "supergroup"}))
router.chat_member.filter(F.chat.type.in_({"group", "supergroup"}))

# Сколько стоит подключить казну
TREASURY_PRICE = 10_000

# Границы награды за приглашение
REWARD_MIN = 1000
REWARD_MAX = 2000

ABOUT = (
    'Функция "Казна" позволяет вам настроить автоматические вознаграждения для '
    "пользователей, которые добавляют новых участников в ваш чат.\n"
    "Вы устанавливаете количество монет, которые бот будет выплачивать за каждого "
    "нового участника, а также пополняете казну для обеспечения этих выплат."
)


async def is_chat_admin(message: types.Message) -> bool:
    try:
        member = await message.chat.get_member(message.from_user.id)
        return member.status in ("creator", "administrator")
    except Exception:
        return False


def status_text(chat_id: int) -> str:
    data = get_treasury(chat_id)
    return (
        f"💰Баланс казны: {fmt(data['treasury_balance'])} {CURRENCY}\n"
        f"👤Награда: {fmt(data['treasury_reward'])} {CURRENCY}"
    )


# ==========================================
# 🏦 КАЗНА — СОСТОЯНИЕ И ПОДКЛЮЧЕНИЕ
# ==========================================
@router.message(F.text.lower() == "казна")
async def cmd_treasury(message: types.Message):
    data = get_treasury(message.chat.id)

    if data["treasury_on"]:
        return await message.answer(status_text(message.chat.id))

    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"Подключить казну {fmt(TREASURY_PRICE)} {CURRENCY} 💰",
        callback_data="treasury_open",
    )

    await message.answer(ABOUT, reply_markup=builder.as_markup())


@router.callback_query(F.data == "treasury_open")
async def cb_open(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    user_id = callback.from_user.id

    if get_treasury(chat_id)["treasury_on"]:
        return await callback.answer("Казна уже подключена", show_alert=True)

    try:
        member = await callback.message.chat.get_member(user_id)
        if member.status not in ("creator", "administrator"):
            return await callback.answer("Казну подключает администратор чата", show_alert=True)
    except Exception:
        return await callback.answer("Не удалось проверить права", show_alert=True)

    if get_balance(user_id) < TREASURY_PRICE:
        return await callback.answer(
            f"Подключение стоит {fmt(TREASURY_PRICE)} {CURRENCY}, на балансе не хватает",
            show_alert=True,
        )

    update_balance(user_id, -TREASURY_PRICE)
    add_bank(TREASURY_PRICE)
    open_treasury(chat_id, REWARD_MIN)

    await callback.message.edit_text(
        f"✅ Казна подключена!\n\n{status_text(chat_id)}\n\n"
        f"Пополнить: <code>казна сумма</code>\n"
        f"Изменить награду: <code>награда сумма</code> "
        f"(от {fmt(REWARD_MIN)} до {fmt(REWARD_MAX)} {CURRENCY})",
        parse_mode="HTML",
    )
    await callback.answer()


# ==========================================
# 💵 ПОПОЛНЕНИЕ КАЗНЫ
# ==========================================
@router.message(F.text.regexp(r"(?i)^казна\s+(\d+)$").as_("match"))
async def cmd_topup(message: types.Message, match: re.Match):
    chat_id = message.chat.id
    user_id = message.from_user.id
    amount = int(match.group(1))

    if amount <= 0:
        return

    if not get_treasury(chat_id)["treasury_on"]:
        return await message.answer("Казна в этом чате ещё не подключена. Напишите «казна»")

    if get_balance(user_id) < amount:
        return await message.answer(
            f"{mention(user_id, message.from_user.first_name)}, недостаточно {CURRENCY}!",
            parse_mode="HTML",
        )

    update_balance(user_id, -amount)
    add_treasury(chat_id, amount)

    await message.answer(
        f"Вы {mention(user_id, message.from_user.first_name)} успешно пополнили "
        f"казну чата на {fmt(amount)} {CURRENCY}",
        parse_mode="HTML",
    )


# ==========================================
# 🎁 НАСТРОЙКА НАГРАДЫ
# ==========================================
@router.message(F.text.regexp(r"(?i)^награда\s+(\d+)$").as_("match"))
async def cmd_reward(message: types.Message, match: re.Match):
    chat_id = message.chat.id
    reward = int(match.group(1))

    if not get_treasury(chat_id)["treasury_on"]:
        return await message.answer("Казна в этом чате ещё не подключена. Напишите «казна»")

    if not await is_chat_admin(message):
        return await message.answer("Награду меняет администратор чата")

    if not REWARD_MIN <= reward <= REWARD_MAX:
        return await message.answer(
            f"Награда может быть от {fmt(REWARD_MIN)} до {fmt(REWARD_MAX)} {CURRENCY}"
        )

    set_treasury_reward(chat_id, reward)
    await message.answer(f"✅ Награда за приглашение: {fmt(reward)} {CURRENCY}\n\n{status_text(chat_id)}")


# ==========================================
# 👥 ВЫПЛАТА ЗА ПРИГЛАШЁННЫХ
# ==========================================
async def reward_invites(bot: Bot, chat_id: int, inviter: types.User, members: list):
    """Платит пригласившему за каждого нового человека.

    Вызывается из двух мест: служебного сообщения о добавлении и обновления
    chat_member. Одного и того же человека в одном чате оплачиваем только раз,
    поэтому ни двойных выплат, ни накрутки через кик и повторное добавление.
    """
    data = get_treasury(chat_id)

    if not data["treasury_on"] or inviter is None:
        return

    reward = data["treasury_reward"]
    paid, empty = 0, False

    for member in members:
        # Боты и те, кто зашёл сам по ссылке, награду не приносят
        if member.is_bot or member.id == inviter.id:
            continue

        update_user_name(member.id, member.first_name, member.username or "")

        if not register_invite(chat_id, member.id, inviter.id):
            continue  # за этого человека уже платили

        if pay_from_treasury(chat_id, inviter.id, reward):
            paid += 1
        else:
            empty = True
            break

    if paid or empty:
        add_to_batch(bot, chat_id, inviter, paid, reward * paid, empty)


# ==========================================
# 📦 ОДНО СООБЩЕНИЕ НА ВСЕХ ПРИГЛАШЁННЫХ
# ==========================================
# Телеграм присылает каждого добавленного отдельным событием. Чтобы на сто
# друзей не улетело сто сообщений, копим их пару секунд и шлём одно.
BATCH_DELAY = 3.0

_batches = {}


def add_to_batch(bot: Bot, chat_id: int, inviter: types.User, count: int, total: int, empty: bool):
    key = (chat_id, inviter.id)
    entry = _batches.get(key)

    if entry is None:
        entry = {"count": 0, "total": 0, "empty": False, "inviter": inviter}
        _batches[key] = entry
        entry["task"] = asyncio.create_task(flush_batch(bot, key))

    entry["count"] += count
    entry["total"] += total
    entry["empty"] = entry["empty"] or empty
    entry["deadline"] = time.monotonic() + BATCH_DELAY


async def flush_batch(bot: Bot, key):
    """Ждём, пока приглашения перестанут приходить, и отправляем итог."""
    while True:
        entry = _batches.get(key)
        if entry is None:
            return

        left = entry["deadline"] - time.monotonic()
        if left <= 0:
            break
        await asyncio.sleep(left)

    entry = _batches.pop(key, None)
    if entry is None:
        return

    chat_id = key[0]
    inviter = entry["inviter"]

    try:
        if entry["count"]:
            who = profile_link(inviter.id, inviter.first_name, inviter.username or "")
            await bot.send_message(
                chat_id,
                f"{who} запросив {entry['count']} друзів\n"
                f"💰Нагорода: {fmt(entry['total'])} {CURRENCY}",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

        if entry["empty"]:
            await bot.send_message(
                chat_id,
                f"💰 В казне не хватает {CURRENCY} на награду. "
                f"Пополнить: <code>казна сумма</code>",
                parse_mode="HTML",
            )
    except Exception as e:
        print(f"Ошибка выплаты за приглашение: {e}")


@router.message(F.new_chat_members)
async def on_join_message(message: types.Message, bot: Bot):
    """Служебное сообщение «X добавил Y»."""
    await reward_invites(bot, message.chat.id, message.from_user, message.new_chat_members)


@router.chat_member()
async def on_chat_member(event: types.ChatMemberUpdated, bot: Bot):
    """Запасной путь: Telegram не всегда шлёт служебное сообщение о входе.

    Это обновление приходит, только если бот администратор чата.
    """
    was = event.old_chat_member.status
    now = event.new_chat_member.status

    # Интересует только переход «не в чате» -> «в чате»
    if was not in ("left", "kicked") or now not in ("member", "administrator", "creator"):
        return

    await reward_invites(bot, event.chat.id, event.from_user, [event.new_chat_member.user])
