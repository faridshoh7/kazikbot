from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# ==========================================
# ⌨️ ГЛАВНОЕ МЕНЮ (нижние кнопки)
# ==========================================
BTN_PROFILE = "👤 Профиль"
BTN_HOGWARTS = "🔮 Хогвартс"
BTN_COMMANDS = "📋Команды"
BTN_DONATE = "🛒Донат"
BTN_TOURNAMENTS = "🏆Турниры"
BTN_CHATS = "💬Чаты"
BTN_CLANS = "🏰 Кланы"
BTN_GAMES = "🎮Игры"
BTN_BONUS = "🎁Бонус"
BTN_POLICY = "Политика"
BTN_LANG = "Изменить язык"


def main_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=BTN_PROFILE)
    builder.button(text=BTN_HOGWARTS)
    builder.button(text=BTN_COMMANDS)
    builder.button(text=BTN_DONATE)
    builder.button(text=BTN_TOURNAMENTS)
    builder.button(text=BTN_CHATS)
    builder.button(text=BTN_CLANS)
    builder.button(text=BTN_GAMES)
    builder.button(text=BTN_BONUS)
    builder.button(text=BTN_POLICY)
    builder.button(text=BTN_LANG)
    # Раскладка точь-в-точь как на скриншоте
    builder.adjust(2, 2, 1, 2, 2, 2)
    return builder.as_markup(resize_keyboard=True)
