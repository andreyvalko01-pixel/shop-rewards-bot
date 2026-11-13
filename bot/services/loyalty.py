"""Правила програми лояльності: рівні, нарахування, обмін балів на купони."""

import secrets
import string
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from ..models import Coupon, Customer, Reward, Transaction


@dataclass(frozen=True)
class Tier:
    name: str
    emoji: str
    min_spent: int
    percent: int


# рівень визначається загальною сумою покупок
TIERS = [
    Tier("Bronze", "🥉", 0, 3),
    Tier("Silver", "🥈", 5_000, 5),
    Tier("Gold", "🥇", 20_000, 7),
]


class LoyaltyError(Exception):
    pass


def tier_for(total_spent: int) -> Tier:
    return [t for t in TIERS if total_spent >= t.min_spent][-1]


def next_tier(total_spent: int) -> Tier | None:
    higher = [t for t in TIERS if t.min_spent > total_spent]
    return higher[0] if higher else None


def points_for_purchase(amount: int, total_spent: int) -> int:
    """1 бал = 1 грн знижки. Округлюємо вниз, щоб не роздавати копійки."""
    return amount * tier_for(total_spent).percent // 100


def new_code(length: int = 6) -> str:
    # без схожих символів (0/O, 1/I), щоб касиру було легко ввести з екрана
    alphabet = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O1I")
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def unique_card_code(session) -> str:
    while True:
        code = new_code()
        if not await session.scalar(select(Customer.id).where(Customer.card_code == code)):
            return code


async def add_points(session, customer: Customer, points: int, kind: str, description: str) -> Transaction:
    customer.balance += points
    tx = Transaction(customer_id=customer.id, points=points, kind=kind, description=description)
    session.add(tx)
    return tx


async def register_purchase(session, customer: Customer, amount: int) -> tuple[int, Tier | None]:
    """Нараховує бали за покупку. Повертає (бали, новий рівень, якщо клієнт його щойно досяг)."""
    if amount <= 0:
        raise LoyaltyError("Сума покупки має бути більшою за нуль")

    old_tier = tier_for(customer.total_spent)
    points = points_for_purchase(amount, customer.total_spent)
    customer.total_spent += amount
    await add_points(session, customer, points, "purchase", f"Покупка на {amount} грн")

    new_tier = tier_for(customer.total_spent)
    return points, (new_tier if new_tier != old_tier else None)


async def redeem(session, customer: Customer, reward: Reward) -> Coupon:
    if not reward.active:
        raise LoyaltyError("Ця винагорода вже недоступна")
    if customer.balance < reward.cost:
        raise LoyaltyError(f"Не вистачає {reward.cost - customer.balance} балів")

    await add_points(session, customer, -reward.cost, "reward", f"Обмін: {reward.title}")
    coupon = Coupon(code=new_code(8), customer_id=customer.id, reward_id=reward.id)
    session.add(coupon)
    return coupon


async def use_coupon(session, code: str) -> Coupon:
    coupon = await session.scalar(select(Coupon).where(Coupon.code == code.strip().upper()))
    if not coupon:
        raise LoyaltyError("Купон не знайдено")
    if coupon.used_at:
        raise LoyaltyError(f"Купон уже використано {coupon.used_at:%d.%m.%Y %H:%M}")
    coupon.used_at = datetime.now()
    return coupon
