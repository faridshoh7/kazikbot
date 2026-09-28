import asyncio

import single_instance

# Проверяем до тяжёлых импортов, чтобы второй запуск отвечал сразу.
# Два бота на одном токене отвечают на каждое сообщение дважды.
if __name__ == "__main__" and not single_instance.acquire():
    print("❌ Бот уже запущен! Закрой старое окно и запусти заново.")
    raise SystemExit(1)

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, ErrorEvent
from aiogram.exceptions import TelegramBadRequest

from config import BOT_TOKEN, ADMIN_ID, START_BANK
from database import update_user_name, update_chat_info, get_setting
from admin_db import get_ban, touch_member, set_admin, get_admin_level, get_bank, set_bank

from handlers.start import router as start_router
from handlers.profile import router as profile_router
from handlers.hogwarts import router as hogwarts_router
from handlers.commands import router as commands_router
from handlers.donate import router as donate_router
from handlers.tournaments import router as tournaments_router
from handlers.clans import router as clans_router
from handlers.games import router as games_router
from handlers.bonus import router as bonus_router
from handlers.money import router as money_router
from handlers.history import router as history_router
from handlers.admin import router as admin_router
from handlers.change_text import router as change_router
from handlers.roulette import router as roulette_router
from handlers.mines import router as mines_router
from handlers.joker import router as joker_router
from handlers.duel import router as duel_router
from handlers.treasury import router as treasury_router
from refunds import refund_task
from backup import make_backup, backup_task


# ==========================================
# 🧠 СОХРАНЕНИЕ ИГРОКА И ЧАТА
# ==========================================
class NameMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user:
            try:
                update_user_name(user.id, user.first_name, user.username or "")
            except Exception as e:
                print(f"Ошибка сохранения имени: {e}")
        return await handler(event, data)


class ChatInfoMiddleware(BaseMiddleware):
    """Запоминает группу для турнира чатов и её участников для /top."""

    async def __call__(self, handler, event, data):
        chat = getattr(event, "chat", None)
        user = getattr(event, "from_user", None)

        if chat and chat.type in ("group", "supergroup"):
            try:
                update_chat_info(chat.id, chat.title or "Чат", chat.username or "")
                if user:
                    touch_member(chat.id, user.id)
            except Exception as e:
                print(f"Ошибка сохранения чата: {e}")

        return await handler(event, data)


# ==========================================
# 🚫 БЛОКИРОВКА ИГРОКОВ
# ==========================================
class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)

        if not user:
            return await handler(event, data)

        ban = get_ban(user.id)
        if not ban:
            return await handler(event, data)

        from handlers.admin import ban_text

        # В личке объясняем причину, в группах молчим, чтобы не спамить
        if isinstance(event, CallbackQuery):
            try:
                await event.answer(ban_text(ban), show_alert=True)
            except Exception:
                pass
        elif isinstance(event, Message) and event.chat.type == "private":
            try:
                await event.answer(ban_text(ban))
            except Exception:
                pass

        return


async def on_error(event: ErrorEvent):
    """Гасим шум от устаревших нажатий и удалённых сообщений."""
    error = event.exception

    if isinstance(error, TelegramBadRequest):
        text = str(error).lower()
        if "query is too old" in text or "message is not modified" in text:
            return True
        if "message to edit not found" in text or "message can't be edited" in text:
            return True

    print(f"Ошибка обработки: {type(error).__name__}: {error}")
    return True


async def main():
    if not BOT_TOKEN:
        print("❌ Укажи BOT_TOKEN в .env")
        return

    # Копия базы на случай, если что-то пойдёт не так
    try:
        print(f"📦 Бэкап базы: {make_backup('start')}")
    except Exception as e:
        print(f"Не удалось сделать бэкап: {e}")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    # Первый запуск — наполняем банк, иначе выигрыши платить не из чего
    if get_setting("bank") is None:
        set_bank(START_BANK)

    # Владелец всегда админ 3 уровня
    if get_admin_level(ADMIN_ID) < 3:
        set_admin(ADMIN_ID, 3, ADMIN_ID)

    dp.message.middleware(BanMiddleware())
    dp.callback_query.middleware(BanMiddleware())
    dp.message.middleware(NameMiddleware())
    dp.callback_query.middleware(NameMiddleware())
    dp.message.middleware(ChatInfoMiddleware())

    # Админка первой, чтобы её команды не перехватили другие роутеры
    dp.include_router(admin_router)
    dp.include_router(change_router)
    dp.include_router(start_router)
    dp.include_router(profile_router)
    dp.include_router(hogwarts_router)
    dp.include_router(commands_router)
    dp.include_router(donate_router)
    dp.include_router(tournaments_router)
    dp.include_router(clans_router)
    dp.include_router(games_router)
    dp.include_router(bonus_router)
    dp.include_router(money_router)
    dp.include_router(history_router)
    dp.include_router(roulette_router)
    dp.include_router(mines_router)
    dp.include_router(joker_router)
    dp.include_router(duel_router)
    dp.include_router(treasury_router)

    dp.errors.register(on_error)

    # Фоновый возврат зависших ставок
    asyncio.create_task(refund_task(bot))

    # Ежечасная копия базы
    asyncio.create_task(backup_task())

    from settings import CURRENCY
    print(f"🚀 Бот {CURRENCY} запущен!")
    # drop_pending_updates — не отвечаем на сообщения, накопившиеся пока бот лежал
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        single_instance.release()


if __name__ == "__main__":
    asyncio.run(main())
