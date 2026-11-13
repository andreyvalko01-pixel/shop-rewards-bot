"""Стартовий каталог винагород і акції. Запуск: python -m bot.seed"""

import asyncio
from datetime import date, timedelta

from sqlalchemy import select

from .models import Promo, Reward, Session, init_db

REWARDS = [
    ("Знижка 50 грн", 500, "На будь-яку покупку від 300 грн"),
    ("Знижка 100 грн", 1000, "На будь-яку покупку від 500 грн"),
    ("Кава в подарунок", 300, "Капучино або американо в кафе при магазині"),
    ("Безкоштовна доставка", 400, "Одне замовлення з сайту з доставкою Новою поштою"),
    ("Знижка 15% на категорію", 1500, "Одноразово на одну категорію товарів на вибір"),
]


async def seed():
    await init_db()
    async with Session() as session:
        if await session.scalar(select(Reward.id).limit(1)):
            return
        session.add_all(Reward(title=t, cost=c, description=d) for t, c, d in REWARDS)
        session.add_all([
            Promo(title="Подвійні бали у вихідні", text="У суботу та неділю нараховуємо ×2 бали на всі покупки.",
                  valid_until=date.today() + timedelta(days=10)),
            Promo(title="−20% на зимове взуття", text="Для учасників програми — додаткові −20% за кодом картки."),
        ])
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
