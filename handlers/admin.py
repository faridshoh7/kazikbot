import asyncio
import html
import io
import re
from datetime import datetime

from aiogram import Router, types, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import (
    get_user,
    update_balance,
    update_user_name,
    set_rtp,
    get_rtp,
    get_name,
)
from admin_db import (
    find_user,
    get_admin_level,
    set_admin,
    remove_admin,
    get_admins,
    ban_user,
    unban_user,
    get_ban,
    get_all_bans,
    log_admin,
    get_admin_log,
    get_bank,
    set_bank,
    get_all_users,
    count_users,
    count_chats,
    get_totals,
    get_top_donaters,
    get_transfers,
    get_game_log,
)
from utils import fmt, mention
from config import ADMIN_ID
from settings import CURRENCY

router = Router()

# Какой уровень нужен для команды
LEVELS = {
    "info": 1,
    "change": 3,
    "ban": 2,
    "unban": 2,
    "rassilka": 2,
    "give": 3,
    "take": 3,
    "bank": 3,
    "rtp": 3,
    "adminlogs": 3,
    "admins": 3,
    "players": 3,
    "donaters": 3,
    "graminfo": 3,
    "manage": 3,
}


def level_of(user_id: int) -> int:
    """Владелец всегда максимальный уровень."""
    if user_id == ADMIN_ID:
        return 3
    return get_admin_level(user_id)


def date_str(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")


def ban_text(ban: dict) -> str:
    until = "навсегда" if not ban["until"] else date_str(ban["until"])
    return f"🚫 Вы заблокированы.\nдо: {until}\nПричина: {ban['reason'] or '—'}"


async def deny(message: types.Message, need: int) -> bool:
    """True, если прав не хватает. Обычным игрокам бот просто молчит."""
    level = level_of(message.from_user.id)

    if level >= need:
        return False

    if level >= 1:
        await message.answer("❌ Недостаточно прав")
    return True


def parse_target(message: types.Message, arg: str = None):
    """Ищет игрока по ответу на сообщение, ID или @username."""
    if message.reply_to_message:
        rival = message.reply_to_message.from_user
        update_user_name(rival.id, rival.first_name, rival.username or "")
        return get_user(rival.id)

    if arg:
        return find_user(arg)

    return None


def as_file(name: str, text: str) -> BufferedInputFile:
    return BufferedInputFile(text.encode("utf-8"), filename=name)


async def send_long(message: types.Message, text: str, filename: str):
    """Короткое отправляем сообщением, длинное — файлом."""
    if len(text) <= 3500:
        await message.answer(f"<pre>{html.escape(text)}</pre>", parse_mode="HTML")
    else:
        await message.answer_document(as_file(filename, text))


# ==========================================
# 📋 СПИСОК КОМАНД
# ==========================================
@router.message(Command("admin", ignore_case=True))
async def cmd_admin(message: types.Message):
    level = level_of(message.from_user.id)

    if level < 1:
        return

    lines = [f"<b>Админ-панель</b> — ваш уровень: {level}\n"]

    lines.append("<b>Уровень 1:</b>")
    lines.append("/info айди/юзернейм/ответом — информация об игроке")

    if level >= 2:
        lines.append("\n<b>Уровень 2:</b>")
        lines.append("/ban дней|навсегда причина айди/юзернейм/ответом — блокировка")
        lines.append("/unban айди/юзернейм/ответом — снять блокировку")
        lines.append("/rassilka текст (можно с фото) — рассылка по игрокам")

    if level >= 3:
        lines.append("\n<b>Уровень 3:</b>")
        lines.append("/give сумма айди/юзернейм/ответом — выдать монеты")
        lines.append("/take сумма айди/юзернейм/ответом — забрать монеты")
        lines.append("/bank — показать банк, /bank сумма — задать банк")
        lines.append("/minesrtp n — RTP минного поля")
        lines.append("/jokerrtp n — RTP джокера")
        lines.append("/rtp — текущие RTP игр")
        lines.append("/change — изменить любой текст в меню бота")
        lines.append(f"/changevalyut имя — переименовать валюту (сейчас {CURRENCY})")
        lines.append("/adminlogs — логи выдачи монет и список банов")
        lines.append("/+admin 1|2|3 айди/юзернейм/ответом — выдать админку")
        lines.append("/-admin айди/юзернейм/ответом — забрать админку")
        lines.append("/admins — список админов")
        lines.append("/players — все игроки файлом")
        lines.append("/donaters — топ 50 донатеров")
        lines.append("/graminfo — общая статистика бота")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ==========================================
# 🔎 ИНФОРМАЦИЯ ОБ ИГРОКЕ
# ==========================================
@router.message(Command("info", ignore_case=True))
async def cmd_info(message: types.Message, command: CommandObject):
    if await deny(message, LEVELS["info"]):
        return

    target = parse_target(message, command.args)
    if not target:
        return await message.answer("Игрок не найден. Укажите ID, @username или ответьте на сообщение")

    user_id = target["user_id"]
    ban = get_ban(user_id)
    ban_line = "нет"
    if ban:
        until = "навсегда" if not ban["until"] else date_str(ban["until"])
        ban_line = f"да, до {until} ({ban['reason'] or '—'})"

    username = f"@{target['username']}" if target["username"] else "—"

    text = (
        f"👤 {mention(user_id, target['name'])} ({username})\n"
        f"🆔 <code>{user_id}</code>\n"
        f"💰 Баланс: {fmt(target['balance'])} {CURRENCY}\n"
        f"🪙 Галеоны: {fmt(target['galleons'])}\n"
        f"🚫 Бан: {ban_line}\n\n"
        f"📊 Сумма ставок: {fmt(target['total_bets'])} {CURRENCY}\n"
        f"✅ Выиграно: {fmt(target['total_won'])} {CURRENCY}\n"
        f"❌ Проиграно: {fmt(target['total_lost'])} {CURRENCY}\n"
        f"📅 В боте с: {date_str(target['reg_date']) if target['reg_date'] else '—'}"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="показать переводы(100)", callback_data=f"adm_tr:{user_id}")
    builder.button(text="показать последние ставки(100)", callback_data=f"adm_bets:{user_id}")
    builder.adjust(1)

    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("adm_tr:"))
async def cb_transfers(callback: types.CallbackQuery):
    if level_of(callback.from_user.id) < LEVELS["info"]:
        return await callback.answer("Недостаточно прав", show_alert=True)

    user_id = int(callback.data.split(":")[1])
    rows = get_transfers(user_id, 100)

    if not rows:
        return await callback.answer("Переводов нет", show_alert=True)

    lines = []
    for row in rows:
        sign = "+" if row["amount"] >= 0 else "-"
        partner = get_name(row["partner_id"]) if row["partner_id"] else "—"
        lines.append(f"[{date_str(row['created_at'])}] {sign}{abs(row['amount'])} | {partner} ({row['partner_id']})")

    await send_long(callback.message, "\n".join(lines), f"transfers_{user_id}.txt")
    await callback.answer()


@router.callback_query(F.data.startswith("adm_bets:"))
async def cb_bets(callback: types.CallbackQuery):
    if level_of(callback.from_user.id) < LEVELS["info"]:
        return await callback.answer("Недостаточно прав", show_alert=True)

    user_id = int(callback.data.split(":")[1])
    rows = get_game_log(user_id, 100)

    if not rows:
        return await callback.answer("Ставок нет", show_alert=True)

    lines = []
    for row in rows:
        result = "выигрыш" if row["amount"] >= 0 else "проигрыш"
        lines.append(f"[{date_str(row['created_at'])}] {row['kind']}: {result} {abs(row['amount'])}")

    await send_long(callback.message, "\n".join(lines), f"bets_{user_id}.txt")
    await callback.answer()


# ==========================================
# 🚫 БАН И РАЗБАН
# ==========================================
@router.message(Command("ban", ignore_case=True))
async def cmd_ban(message: types.Message, command: CommandObject, bot: Bot):
    if await deny(message, LEVELS["ban"]):
        return

    args = (command.args or "").split()
    if not args:
        return await message.answer("Формат: /ban дней|навсегда причина [айди/юзернейм]")

    raw_days = args[0].lower()
    days = None if raw_days in {"навсегда", "forever", "всегда"} else None
    if raw_days.isdigit():
        days = int(raw_days)
    elif raw_days not in {"навсегда", "forever", "всегда"}:
        return await message.answer("Первым аргументом укажите число дней или «навсегда»")

    rest = args[1:]

    # Без ответа последний аргумент — это получатель бана
    if message.reply_to_message:
        target = parse_target(message)
        reason = " ".join(rest)
    else:
        if not rest:
            return await message.answer("Укажите причину и получателя бана")
        target = find_user(rest[-1])
        reason = " ".join(rest[:-1])
        if not target:
            target = find_user(rest[0])
            reason = " ".join(rest[1:])

    if not target:
        return await message.answer("Игрок не найден")

    if target["user_id"] == ADMIN_ID:
        return await message.answer("Владельца забанить нельзя")

    until = ban_user(target["user_id"], days, reason, message.from_user.id)
    until_text = "навсегда" if not until else date_str(until)

    await message.answer(
        f"🚫 {mention(target['user_id'], target['name'])} заблокирован\n"
        f"до: {until_text}\nПричина: {reason or '—'}",
        parse_mode="HTML",
    )

    try:
        await bot.send_message(target["user_id"], ban_text(get_ban(target["user_id"])))
    except Exception:
        pass


@router.message(Command("unban", ignore_case=True))
async def cmd_unban(message: types.Message, command: CommandObject):
    if await deny(message, LEVELS["unban"]):
        return

    target = parse_target(message, command.args)
    if not target:
        return await message.answer("Игрок не найден")

    if unban_user(target["user_id"]):
        await message.answer(
            f"✅ {mention(target['user_id'], target['name'])} разблокирован", parse_mode="HTML"
        )
    else:
        await message.answer("У этого игрока нет активной блокировки")


# ==========================================
# 💰 ВЫДАЧА И ИЗЪЯТИЕ МОНЕТ
# ==========================================
async def money_command(message: types.Message, args: str, take: bool):
    parts = (args or "").split()
    if not parts or not parts[0].isdigit():
        return await message.answer(
            f"Формат: /{'take' if take else 'give'} сумма [айди/юзернейм]"
        )

    amount = int(parts[0])
    target = parse_target(message, parts[1] if len(parts) > 1 else None)

    if not target:
        return await message.answer("Игрок не найден")

    if take:
        amount = min(amount, target["balance"])
        update_balance(target["user_id"], -amount)
    else:
        update_balance(target["user_id"], amount)

    log_admin(message.from_user.id, "take" if take else "give", target["user_id"], amount)

    verb = "забрал у" if take else "выдал"
    await message.answer(
        f"✅ Админ {mention(message.from_user.id, message.from_user.first_name)} {verb} "
        f"{mention(target['user_id'], target['name'])} {fmt(amount)} {CURRENCY}",
        parse_mode="HTML",
    )


@router.message(Command("give", ignore_case=True))
async def cmd_give(message: types.Message, command: CommandObject):
    if await deny(message, LEVELS["give"]):
        return
    await money_command(message, command.args, take=False)


@router.message(Command("take", ignore_case=True))
async def cmd_take(message: types.Message, command: CommandObject):
    if await deny(message, LEVELS["take"]):
        return
    await money_command(message, command.args, take=True)


# ==========================================
# 📢 РАССЫЛКА
# ==========================================
@router.message(Command("rassilka", ignore_case=True))
async def cmd_rassilka(message: types.Message, command: CommandObject, bot: Bot):
    if await deny(message, LEVELS["rassilka"]):
        return

    text = command.args or ""
    photo = message.photo[-1].file_id if message.photo else None

    if not text and not photo:
        return await message.answer("Формат: /rassilka текст (можно с фото)")

    await message.answer("📢 Рассылка запущена")
    asyncio.create_task(run_broadcast(bot, message, text, photo))


async def run_broadcast(bot: Bot, message: types.Message, text: str, photo: str):
    sent, failed = 0, 0

    for user in get_all_users():
        try:
            if photo:
                await bot.send_photo(user["user_id"], photo, caption=text)
            else:
                await bot.send_message(user["user_id"], text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    try:
        await message.answer(f"📢 Рассылка закончена\n✅ Доставлено: {sent}\n❌ Не дошло: {failed}")
    except Exception:
        pass


# ==========================================
# ✏️ СМЕНА НАЗВАНИЙ И ССЫЛОК
# ==========================================
@router.message(Command("changevalyut", ignore_case=True))
async def cmd_change_currency(message: types.Message, command: CommandObject):
    if await deny(message, LEVELS["change"]):
        return

    name = (command.args or "").strip()

    if not name:
        return await message.answer(f"Формат: /changevalyut имя\nСейчас: {CURRENCY}")

    if len(name) > 16:
        return await message.answer("Название валюты не длиннее 16 символов")

    old = str(CURRENCY)
    CURRENCY.set(name)
    await message.answer(f"✅ Валюта переименована: {old} → {name}\n\nНовое название уже везде в боте.")


# ==========================================
# 🏦 БАНК И RTP
# ==========================================
@router.message(Command("bank", ignore_case=True))
async def cmd_bank(message: types.Message, command: CommandObject):
    if await deny(message, LEVELS["bank"]):
        return

    args = (command.args or "").strip()

    if args:
        if not args.lstrip("-").isdigit():
            return await message.answer("Формат: /bank сумма")
        set_bank(int(args))

    await message.answer(f"🏦 Банк бота: {fmt(get_bank())} {CURRENCY}")


async def rtp_command(message: types.Message, args: str, game: str, title: str):
    args = (args or "").strip().replace(",", ".")

    if not args:
        return await message.answer(f"Формат: /{game}rtp 0.98")

    try:
        value = float(args)
    except ValueError:
        return await message.answer("RTP должен быть числом, например 0.98 или 1.2")

    if not 0 < value <= 5:
        return await message.answer("RTP должен быть больше 0 и не больше 5")

    set_rtp(game, value)
    await message.answer(f"✅ RTP {title}: {value}")


@router.message(Command("minesrtp", ignore_case=True))
async def cmd_minesrtp(message: types.Message, command: CommandObject):
    if await deny(message, LEVELS["rtp"]):
        return
    await rtp_command(message, command.args, "mines", "минного поля")


@router.message(Command("jokerrtp", ignore_case=True))
async def cmd_jokerrtp(message: types.Message, command: CommandObject):
    if await deny(message, LEVELS["rtp"]):
        return
    await rtp_command(message, command.args, "joker", "джокера")


@router.message(Command("rtp", ignore_case=True))
async def cmd_rtp(message: types.Message):
    if await deny(message, LEVELS["rtp"]):
        return

    await message.answer(
        f"🎛 <b>Текущие RTP</b>\n\n"
        f"💣 Минное поле: {get_rtp('mines')}\n"
        f"🃏 Джокер: {get_rtp('joker')}\n"
        f"🎰 Рулетка: честная (36/количество чисел)",
        parse_mode="HTML",
    )


# ==========================================
# 📜 ЛОГИ
# ==========================================
@router.message(Command("adminlogs", ignore_case=True))
async def cmd_adminlogs(message: types.Message):
    if await deny(message, LEVELS["adminlogs"]):
        return

    money_lines = ["Дата | Действие | Сумма | Кому (ID) | Админ (ID)"]
    for row in get_admin_log():
        action = "ВЫДАЛ" if row["action"] == "give" else "ЗАБРАЛ"
        money_lines.append(
            f"{date_str(row['created_at'])} | {action} | {row['amount']} | "
            f"{get_name(row['target_id'])} ({row['target_id']}) | "
            f"{get_name(row['admin_id'])} ({row['admin_id']})"
        )

    ban_lines = ["Дата бана | Игрок (ID) | До | Причина | Админ (ID) | Активен"]
    for row in get_all_bans():
        until = "навсегда" if not row["until"] else date_str(row["until"])
        ban_lines.append(
            f"{date_str(row['created_at'])} | {get_name(row['user_id'])} ({row['user_id']}) | "
            f"{until} | {row['reason'] or '—'} | "
            f"{get_name(row['admin_id'])} ({row['admin_id']}) | "
            f"{'да' if row['is_active'] else 'нет'}"
        )

    await message.answer_document(
        as_file("money_logs.txt", "\n".join(money_lines)), caption="💰 Логи выдачи и изъятия монет"
    )
    await message.answer_document(
        as_file("ban_logs.txt", "\n".join(ban_lines)), caption="🚫 Все блокировки за всё время"
    )


# ==========================================
# 👮 УПРАВЛЕНИЕ АДМИНАМИ
# ==========================================
@router.message(F.text.regexp(r"(?i)^/\+admin(?:\s+(.*))?$").as_("match"))
async def cmd_add_admin(message: types.Message, match: re.Match):
    if await deny(message, LEVELS["manage"]):
        return

    args = (match.group(1) or "").split()
    if not args or not args[0].isdigit() or int(args[0]) not in (1, 2, 3):
        return await message.answer("Формат: /+admin 1|2|3 айди/юзернейм (или ответом)")

    level = int(args[0])
    target = parse_target(message, args[1] if len(args) > 1 else None)

    if not target:
        return await message.answer("Игрок не найден")

    set_admin(target["user_id"], level, message.from_user.id)
    await message.answer(
        f"✅ {mention(target['user_id'], target['name'])} теперь админ {level} уровня",
        parse_mode="HTML",
    )


@router.message(F.text.regexp(r"(?i)^/-admin(?:\s+(.*))?$").as_("match"))
async def cmd_del_admin(message: types.Message, match: re.Match):
    if await deny(message, LEVELS["manage"]):
        return

    args = (match.group(1) or "").strip()
    target = parse_target(message, args or None)

    if not target:
        return await message.answer("Игрок не найден")

    if remove_admin(target["user_id"]):
        await message.answer(
            f"✅ {mention(target['user_id'], target['name'])} больше не админ", parse_mode="HTML"
        )
    else:
        await message.answer("Этот игрок не был админом")


@router.message(Command("admins", ignore_case=True))
async def cmd_admins(message: types.Message):
    if await deny(message, LEVELS["admins"]):
        return

    lines = [f"👑 Владелец: {mention(ADMIN_ID, get_name(ADMIN_ID))} (<code>{ADMIN_ID}</code>)\n"]

    admins = [a for a in get_admins() if a["user_id"] != ADMIN_ID]
    if not admins:
        lines.append("Других админов нет")
    else:
        lines.append("<b>Админы:</b>")
        for admin in admins:
            lines.append(
                f"{mention(admin['user_id'], get_name(admin['user_id']))} "
                f"(<code>{admin['user_id']}</code>) — уровень {admin['level']}"
            )

    await message.answer("\n".join(lines), parse_mode="HTML")


# ==========================================
# 📈 СТАТИСТИКА
# ==========================================
@router.message(Command("players", ignore_case=True))
async def cmd_players(message: types.Message):
    if await deny(message, LEVELS["players"]):
        return

    users = get_all_users()
    lines = ["ID | Юзернейм | Имя | Дата регистрации"]
    for user in users:
        username = f"@{user['username']}" if user["username"] else "—"
        reg = date_str(user["reg_date"]) if user["reg_date"] else "—"
        lines.append(f"{user['user_id']} | {username} | {user['name']} | {reg}")

    await message.answer(f"👥 Всего игроков в боте: <b>{fmt(len(users))}</b>", parse_mode="HTML")
    await message.answer_document(as_file("players.txt", "\n".join(lines)))


@router.message(Command("donaters", ignore_case=True))
async def cmd_donaters(message: types.Message):
    if await deny(message, LEVELS["donaters"]):
        return

    top = get_top_donaters(50)

    if not top:
        return await message.answer("Донатов пока не было")

    lines = ["💎 <b>Топ 50 донатеров</b>\n"]
    for i, row in enumerate(top, start=1):
        username = f"@{row['username']}" if row["username"] else row["name"] or "Игрок"
        lines.append(f"{i}. {username} — {fmt(row['total'])} {CURRENCY} ({row['stars']} ⭐)")

    await send_long(message, "\n".join(lines).replace("<b>", "").replace("</b>", ""), "donaters.txt")


@router.message(Command("graminfo", ignore_case=True))
async def cmd_graminfo(message: types.Message):
    if await deny(message, LEVELS["graminfo"]):
        return

    totals = get_totals()

    await message.answer(
        f"📊 <b>Статистика {CURRENCY}</b>\n\n"
        f"🎲 Общая сумма ставок: {fmt(totals['bets'])} {CURRENCY}\n"
        f"✅ Общий выигрыш игроков: {fmt(totals['won'])} {CURRENCY}\n"
        f"❌ Общий проигрыш игроков: {fmt(totals['lost'])} {CURRENCY}\n\n"
        f"💎 Куплено за донат: {fmt(totals['donated'])} {CURRENCY} ({fmt(totals['stars'])} ⭐)\n"
        f"👥 Игроков в боте: {fmt(count_users())}\n"
        f"💬 Групп с ботом: {fmt(count_chats())}\n"
        f"🏦 Банк бота: {fmt(get_bank())} {CURRENCY}",
        parse_mode="HTML",
    )
