from datetime import date

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import or_, select

from .. import keyboards as kb
from ..config import settings
from ..models import Customer, Promo, Reward, Session, Transaction
from ..services import loyalty

router = Router()


def plural_points(n: int) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return "бал"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "бали"
    return "балів"


async def get_customer(session, user_id: int) -> Customer | None:
    return await session.scalar(select(Customer).where(Customer.telegram_id == user_id))


@router.message(CommandStart())
async def start(message: Message):
    async with Session() as session:
        customer = await get_customer(session, message.from_user.id)

    if customer and customer.phone:
        await message.answer(
            f"Вітаємо у {settings.shop_name}! 👋\nПереглядайте бонуси та пропозиції магазину.",
            reply_markup=kb.main_menu(customer.notify),
        )
        return

    await message.answer(
        f"Вітаємо у {settings.shop_name}! 👋\n\n"
        f"Це бонусна картка магазину: за кожну покупку повертаємо від 3% балами, а бали можна обміняти на знижки.\n\n"
        f"Поділіться номером телефону — і отримаєте {settings.welcome_bonus} балів за реєстрацію 🎁",
        reply_markup=kb.share_phone(),
    )


@router.message(F.contact)
async def on_contact(message: Message):
    if message.contact.user_id != message.from_user.id:
        await message.answer("Потрібен саме ваш номер — натисніть кнопку нижче.", reply_markup=kb.share_phone())
        return

    async with Session() as session:
        customer = await get_customer(session, message.from_user.id)
        is_new = customer is None
        if is_new:
            customer = Customer(
                telegram_id=message.from_user.id,
                name=message.from_user.full_name,
                card_code=await loyalty.unique_card_code(session),
            )
            session.add(customer)
            await session.flush()
            await loyalty.add_points(session, customer, settings.welcome_bonus, "welcome", "Бонус за реєстрацію")
        customer.phone = "+" + message.contact.phone_number.lstrip("+")
        await session.commit()

    await message.answer("Готово! ✅", reply_markup=kb.remove)
    text = f"Ваша картка: <b>{customer.card_code}</b>\nПокажіть цей код на касі, щоб отримати бали."
    if is_new:
        text = f"🎁 Нараховано {settings.welcome_bonus} балів за реєстрацію!\n\n" + text
    await message.answer(text, parse_mode="HTML", reply_markup=kb.main_menu(customer.notify))


async def _need_customer(call: CallbackQuery, session) -> Customer | None:
    customer = await get_customer(session, call.from_user.id)
    if not customer:
        await call.answer("Спершу натисніть /start і поділіться номером", show_alert=True)
    return customer


@router.callback_query(kb.Menu.filter(F.section == "menu"))
async def menu(call: CallbackQuery):
    async with Session() as session:
        customer = await _need_customer(call, session)
    if customer:
        await call.message.edit_text("Оберіть розділ:", reply_markup=kb.main_menu(customer.notify))
        await call.answer()


@router.callback_query(kb.Menu.filter(F.section == "balance"))
async def balance(call: CallbackQuery):
    async with Session() as session:
        customer = await _need_customer(call, session)
        if not customer:
            return
        last = await session.scalar(
            select(Transaction).where(Transaction.customer_id == customer.id, Transaction.points > 0)
            .order_by(Transaction.id.desc()).limit(1)
        )
        cheapest = await session.scalar(select(Reward).where(Reward.active).order_by(Reward.cost).limit(1))

    tier = loyalty.tier_for(customer.total_spent)
    lines = [
        f"💎 Ваш баланс: <b>{customer.balance:,} {plural_points(customer.balance)}</b>".replace(",", " "),
    ]
    if last:
        lines.append(f"Останнє нарахування: +{last.points} ({last.description.lower()})")
    lines.append(f"\n{tier.emoji} Рівень {tier.name}: {tier.percent}% з кожної покупки")
    if nxt := loyalty.next_tier(customer.total_spent):
        lines.append(f"До {nxt.name} ({nxt.percent}%) залишилось покупок на {nxt.min_spent - customer.total_spent:,} грн".replace(",", " "))
    if cheapest:
        if customer.balance >= cheapest.cost:
            lines.append(f"\n🎁 Вже можна обміняти {cheapest.cost} балів на «{cheapest.title}»")
        else:
            lines.append(f"\n🎁 До «{cheapest.title}» — ще {cheapest.cost - customer.balance} балів")

    await call.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.back())
    await call.answer()


@router.callback_query(kb.Menu.filter(F.section == "promos"))
async def promos(call: CallbackQuery):
    async with Session() as session:
        items = (await session.scalars(
            select(Promo).where(or_(Promo.valid_until.is_(None), Promo.valid_until >= date.today()))
            .order_by(Promo.id.desc()).limit(5)
        )).all()

    if not items:
        text = "Зараз активних акцій немає. Ми напишемо, щойно з'являться 😉"
    else:
        blocks = []
        for p in items:
            until = f"\n<i>до {p.valid_until:%d.%m}</i>" if p.valid_until else ""
            blocks.append(f"🏷 <b>{p.title}</b>\n{p.text}{until}")
        text = "\n\n".join(blocks)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb.back())
    await call.answer()


@router.callback_query(kb.Menu.filter(F.section == "rewards"))
async def rewards(call: CallbackQuery):
    async with Session() as session:
        customer = await _need_customer(call, session)
        if not customer:
            return
        items = (await session.scalars(select(Reward).where(Reward.active).order_by(Reward.cost))).all()
    await call.message.edit_text(
        f"🎁 Обміняйте бали на винагороду. Зараз у вас {customer.balance} {plural_points(customer.balance)}.",
        reply_markup=kb.rewards_kb(items, customer.balance),
    )
    await call.answer()


@router.callback_query(kb.RewardPick.filter(~F.confirm))
async def reward_ask(call: CallbackQuery, callback_data: kb.RewardPick):
    async with Session() as session:
        customer = await _need_customer(call, session)
        reward = await session.get(Reward, callback_data.reward_id)
    if not customer:
        return
    if customer.balance < reward.cost:
        await call.answer(f"Не вистачає {reward.cost - customer.balance} балів", show_alert=True)
        return
    await call.message.edit_text(
        f"Обміняти {reward.cost} балів на «{reward.title}»?\n{reward.description}",
        reply_markup=kb.confirm_reward(reward.id),
    )
    await call.answer()


@router.callback_query(kb.RewardPick.filter(F.confirm))
async def reward_confirm(call: CallbackQuery, callback_data: kb.RewardPick):
    async with Session() as session:
        customer = await _need_customer(call, session)
        if not customer:
            return
        reward = await session.get(Reward, callback_data.reward_id)
        try:
            coupon = await loyalty.redeem(session, customer, reward)
        except loyalty.LoyaltyError as e:
            await call.answer(str(e), show_alert=True)
            return
        await session.commit()

    await call.message.edit_text(
        f"🎉 Готово! Ваш купон: <code>{coupon.code}</code>\n«{reward.title}»\n\n"
        f"Назвіть код на касі. Залишок: {customer.balance} {plural_points(customer.balance)}.",
        parse_mode="HTML", reply_markup=kb.back(),
    )
    await call.answer()


@router.callback_query(kb.Menu.filter(F.section == "history"))
async def history(call: CallbackQuery):
    async with Session() as session:
        customer = await _need_customer(call, session)
        if not customer:
            return
        txs = (await session.scalars(
            select(Transaction).where(Transaction.customer_id == customer.id).order_by(Transaction.id.desc()).limit(10)
        )).all()

    lines = ["🕓 Останні операції:\n"]
    for t in txs:
        sign = "+" if t.points > 0 else "−"
        lines.append(f"{t.created_at:%d.%m}  {sign}{abs(t.points)}  {t.description}")
    await call.message.edit_text("\n".join(lines), reply_markup=kb.back())
    await call.answer()


@router.callback_query(kb.Menu.filter(F.section == "card"))
async def card(call: CallbackQuery):
    async with Session() as session:
        customer = await _need_customer(call, session)
    if not customer:
        return
    tier = loyalty.tier_for(customer.total_spent)
    await call.message.edit_text(
        f"💳 Картка {settings.shop_name}\n\nКод: <b>{customer.card_code}</b>\n{tier.emoji} {tier.name} · {tier.percent}%\n\n"
        "Покажіть код касиру перед оплатою.",
        parse_mode="HTML", reply_markup=kb.back(),
    )
    await call.answer()


@router.callback_query(kb.Menu.filter(F.section == "notify"))
async def toggle_notify(call: CallbackQuery):
    async with Session() as session:
        customer = await _need_customer(call, session)
        if not customer:
            return
        customer.notify = not customer.notify
        session.add(customer)
        await session.commit()

    state = "увімкнено" if customer.notify else "вимкнено"
    await call.message.edit_text(f"🔔 Сповіщення про акції {state}.", reply_markup=kb.main_menu(customer.notify))
    await call.answer()
