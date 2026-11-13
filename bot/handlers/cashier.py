"""Команди касира: нарахування балів за покупку і погашення купонів."""

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select

from ..config import settings
from ..models import Customer, Session
from ..services import loyalty

router = Router()
router.message.filter(F.from_user.id.in_(settings.cashiers))


@router.message(Command("add"))
async def add_purchase(message: Message, command: CommandObject, bot: Bot):
    """/add ABC123 1250 — покупка на 1250 грн для картки ABC123"""
    try:
        code, amount = command.args.split()
        amount = int(amount)
    except (AttributeError, ValueError):
        await message.answer("Формат: /add КОД_КАРТКИ СУМА\nНаприклад: /add K7M2QX 1250")
        return

    async with Session() as session:
        customer = await session.scalar(select(Customer).where(Customer.card_code == code.upper()))
        if not customer:
            await message.answer("Картку не знайдено")
            return
        try:
            points, new_tier = await loyalty.register_purchase(session, customer, amount)
        except loyalty.LoyaltyError as e:
            await message.answer(str(e))
            return
        await session.commit()

    await message.answer(f"✅ {customer.name}: +{points} балів, баланс {customer.balance}")

    text = f"🛍 Дякуємо за покупку на {amount} грн!\n+{points} балів, на рахунку {customer.balance}."
    if new_tier:
        text += f"\n\n{new_tier.emoji} Вітаємо, ви перейшли на рівень {new_tier.name} — тепер {new_tier.percent}% з кожної покупки!"
    await bot.send_message(customer.telegram_id, text)


@router.message(Command("coupon"))
async def check_coupon(message: Message, command: CommandObject):
    """/coupon ABCD2345 — погасити купон"""
    if not command.args:
        await message.answer("Формат: /coupon КОД")
        return
    async with Session() as session:
        try:
            coupon = await loyalty.use_coupon(session, command.args)
        except loyalty.LoyaltyError as e:
            await message.answer(f"❌ {e}")
            return
        await session.commit()
    await message.answer(f"✅ Купон дійсний: «{coupon.reward.title}» для {coupon.customer.name}. Позначено як використаний.")
