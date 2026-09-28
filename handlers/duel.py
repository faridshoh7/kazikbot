import secrets
import time

from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import (
    STATS,
    get_stats,
    get_stats_sum,
    update_balance,
    update_galleons,
    update_user_name,
    add_duel,
    get_duels_since,
    add_history,
    add_win,
    get_name,
)
from utils import fmt, mention
from config import (
    DUEL_COOLDOWN,
    DUELS_PER_DAY,
    DUEL_REWARD_MIN,
    DUEL_REWARD_MAX,
    DUEL_GALLEONS_MAX,
    DUEL_STATS_FOR_MAX,
    DUEL_MODE,
)
from settings import CURRENCY

router = Router()
# Дуэли только в чатах
router.message.filter(F.chat.type.in_({"group", "supergroup"}))

rnd = secrets.SystemRandom()

DUEL_WORDS = {"дуэль", "дуэльку", "дуель", "/дуэль", "дуэлька"}

UP = "🔼"
DOWN = "🔽"
SAME = "➖"


# ==========================================
# ⏳ КУЛДАУН
# ==========================================
def check_cooldown(user_id: int):
    """Возвращает текст ошибки, если дуэль пока недоступна."""
    now = time.time()
    day_ago = now - 24 * 60 * 60
    duels = get_duels_since(user_id, day_ago)

    # Лимит на сутки
    if len(duels) >= DUELS_PER_DAY:
        # Ждём, пока самая старая из последних дуэлей выйдет за сутки
        oldest = duels[-DUELS_PER_DAY]
        left = (oldest + 24 * 60 * 60) - now
        hours = max(1, int(left // 3600) + (1 if left % 3600 else 0))
        return f"⏳ Дуэль будет доступна через {hours} часов."

    # Перерыв между дуэлями
    if duels:
        left = DUEL_COOLDOWN - (now - duels[-1])
        if left > 0:
            minutes = max(1, int(left // 60) + (1 if left % 60 else 0))
            return f"⏳ Дуэль будет доступна через {minutes} мин."

    return None


# ==========================================
# ⚔️ ВЫЗОВ НА ДУЭЛЬ
# ==========================================
@router.message(F.text.lower().in_(DUEL_WORDS))
async def cmd_duel(message: types.Message):
    if not message.reply_to_message:
        return await message.answer("Напишите «дуэль» в ответ на сообщение игрока")

    user = message.from_user
    rival = message.reply_to_message.from_user

    if rival.id == user.id:
        return await message.answer("Нельзя вызвать на дуэль самого себя")

    error = check_cooldown(user.id)
    if error:
        return await message.answer(error)

    # Соперник мог ещё ни разу не писать боту — заводим ему профиль
    update_user_name(rival.id, rival.first_name, rival.username or "")

    my_stats = get_stats(user.id)
    his_stats = get_stats(rival.id)
    rival_name = rival.username or rival.first_name

    lines = [f"Ваши характеристики | характеристики {rival_name}", ""]
    for key, title in STATS.items():
        mine, his = my_stats[key], his_stats[key]
        arrow = UP if mine > his else (DOWN if mine < his else SAME)
        lines.append(f"{title}: {mine} {arrow} | {title}: {his}")

    builder = InlineKeyboardBuilder()
    builder.button(
        text="⚔️ Атаковать",
        callback_data=f"duel_hit:{user.id}:{rival.id}",
        style="primary",
    )

    await message.answer("\n".join(lines), reply_markup=builder.as_markup())


# ==========================================
# 🗡 АТАКА
# ==========================================
@router.callback_query(F.data.startswith("duel_hit:"))
async def cb_attack(callback: types.CallbackQuery):
    _, user_id, rival_id = callback.data.split(":")
    user_id, rival_id = int(user_id), int(rival_id)

    if callback.from_user.id != user_id:
        return await callback.answer("Это не ваша дуэль!", show_alert=True)

    error = check_cooldown(user_id)
    if error:
        return await callback.answer(error, show_alert=True)

    chat_id = callback.message.chat.id
    my_power = get_stats_sum(user_id)
    his_power = get_stats_sum(rival_id)

    if DUEL_MODE == "stats":
        # Побеждает тот, у кого характеристики выше (при равенстве — монетка)
        is_win = my_power > his_power or (my_power == his_power and rnd.random() < 0.5)
    else:
        # Шанс победы пропорционален характеристикам
        is_win = rnd.random() < my_power / (my_power + his_power)

    winner_id = user_id if is_win else rival_id
    winner_power = my_power if is_win else his_power

    reward = rnd.randint(DUEL_REWARD_MIN, DUEL_REWARD_MAX)

    # Чем выше характеристики победителя, тем больше галеонов
    share = min(1.0, winner_power / DUEL_STATS_FOR_MAX)
    galleons = rnd.randint(0, int(DUEL_GALLEONS_MAX * share))

    update_balance(winner_id, reward)
    update_galleons(winner_id, galleons)
    add_win(winner_id, reward, chat_id)
    add_duel(user_id, rival_id, chat_id, is_win, reward, galleons)
    add_history(user_id, "duel", reward if is_win else -reward, rival_id)

    name = callback.from_user.first_name
    who = mention(user_id, name)

    if is_win:
        text = (
            f"{who}, Вы победили\n\n"
            f"Награда за победу:\n"
            f"💰 {fmt(reward)} {CURRENCY} | 🪙 {fmt(galleons)} галеонов"
        )
    else:
        text = (
            f"{who}, Вы проиграли\n\n"
            f"Победу забирает {mention(rival_id, get_name(rival_id))}:\n"
            f"💰 {fmt(reward)} {CURRENCY} | 🪙 {fmt(galleons)} галеонов"
        )

    await callback.message.reply(text, parse_mode="HTML")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer()
