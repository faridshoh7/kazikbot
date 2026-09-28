import random

from aiogram import Router, types, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder

from keyboards import BTN_DONATE
from database import update_balance, get_balance, create_payment, close_payment, get_payment, set_vip
from utils import fmt
from settings import CURRENCY
from texts import render

router = Router()
# Кнопки меню работают только в личных сообщениях
router.message.filter(F.chat.type == "private")

# ==========================================
# 🛒 ПАКЕТЫ ДОНАТА
# ==========================================
PACKAGES = {
    "p1": {"gram": 100_000, "stars": 50, "bonus": ""},
    "p2": {"gram": 204_000, "stars": 100, "bonus": "(+2%)"},
    "p3": {"gram": 525_000, "stars": 250, "bonus": "(+5%)"},
    "p4": {"gram": 1_150_000, "stars": 500, "bonus": "(+10%)"},
    "p5": {"gram": 2_300_000, "stars": 1000, "bonus": "(+15%)"},
    "p6": {"gram": 6_250_000, "stars": 2500, "bonus": "(+25%)"},
    "vip": {"gram": 0, "stars": 100, "bonus": "", "is_vip": True},
}


def new_payment_id() -> int:
    return random.randint(100_000_000, 999_999_999)


# ==========================================
# 🏪 ВИТРИНА
# ==========================================
@router.message(F.text == BTN_DONATE)
async def show_donate(message: types.Message):
    builder = InlineKeyboardBuilder()

    for pack_id, pack in PACKAGES.items():
        if pack.get("is_vip"):
            btn_text = f"{pack['stars']} ⭐ - VIP"
        else:
            btn_text = f"{pack['stars']} ⭐ - {fmt(pack['gram'])} {pack['bonus']}".strip()
        builder.button(text=btn_text, callback_data=f"donate:{pack_id}")

    builder.adjust(1)

    await message.answer(
        render("donate"),
        reply_markup=builder.as_markup(),
    )


# ==========================================
# 🧾 СОЗДАНИЕ СЧЁТА
# ==========================================
@router.callback_query(F.data.startswith("donate:"))
async def create_invoice(callback: types.CallbackQuery, bot: Bot):
    pack_id = callback.data.split(":", 1)[1]
    pack = PACKAGES.get(pack_id)

    if not pack:
        return await callback.answer("Пакет не найден.", show_alert=True)

    payment_id = new_payment_id()
    is_vip = pack.get("is_vip", False)

    title = "Покупка VIP" if is_vip else f"Пополнение {fmt(pack['gram'])} {CURRENCY}"
    label = "VIP" if is_vip else f"{fmt(pack['gram'])} {CURRENCY} {pack['bonus']}".strip()

    try:
        invoice_link = await bot.create_invoice_link(
            title=title,
            description=title,
            payload=f"gram:{payment_id}",
            provider_token="",
            currency="XTR",
            prices=[types.LabeledPrice(label=label, amount=pack["stars"])],
        )
    except Exception as e:
        return await callback.answer(f"Не удалось создать счёт: {e}", show_alert=True)

    create_payment(payment_id, callback.from_user.id, pack_id, pack["gram"], pack["stars"])

    amount_text = "VIP" if is_vip else f"{fmt(pack['gram'])} {CURRENCY}"
    text = (
        "<b>Счет создан!</b>\n"
        f"Пополнение на: {amount_text}\n\n"
        f"ID платежа: {fmt(payment_id)}\n\n"
        f"Пожалуйста, оплатите {pack['stars']} Telegram Stars по ссылке ниже:"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text=f"оплатить {amount_text}", url=invoice_link)

    await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()


# ==========================================
# 🛡 ПОДТВЕРЖДЕНИЕ ОПЛАТЫ
# ==========================================
@router.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    await query.answer(ok=True)


# ==========================================
# ✅ УСПЕШНАЯ ОПЛАТА
# ==========================================
@router.message(F.successful_payment)
async def on_paid(message: types.Message):
    payload = message.successful_payment.invoice_payload

    if not payload.startswith("gram:"):
        return

    payment_id = int(payload.split(":", 1)[1])
    payment = get_payment(payment_id)

    if not payment or payment["is_paid"]:
        return

    close_payment(payment_id)

    user_id = message.from_user.id
    pack = PACKAGES.get(payment["pack_id"])
    if not pack:
        return

    if pack.get("is_vip"):
        set_vip(user_id)
        return await message.answer(
            "✅ <b>Оплата прошла успешно!</b>\n\nСтатус <b>VIP</b> активирован.",
            parse_mode="HTML",
        )

    update_balance(user_id, pack["gram"])
    await message.answer(
        "✅ <b>Оплата прошла успешно!</b>\n\n"
        f"Начислено: <b>{fmt(pack['gram'])} {CURRENCY}</b>\n"
        f"💰 Баланс: {fmt(get_balance(user_id))} {CURRENCY}",
        parse_mode="HTML",
    )
