"""Тестові учасники програми з історією покупок — щоб подивитися панель.

    python -m bot.seed && python scripts/demo_customers.py
"""

import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from bot.models import Customer, Reward, Session  # noqa: E402
from bot.services import loyalty  # noqa: E402

NAMES = ["Ірина Бойко", "Олег Ткаченко", "Марина Кравчук", "Сергій Поліщук", "Анастасія Литвин",
         "Дмитро Савченко", "Юлія Марченко", "Віктор Остапенко", "Світлана Гнатюк", "Роман Захарченко"]


async def main():
    random.seed(3)
    async with Session() as session:
        rewards = (await session.scalars(select(Reward))).all()
        for i, name in enumerate(NAMES):
            c = Customer(telegram_id=700000 + i, name=name, phone=f"+38050{random.randint(1000000, 9999999)}",
                         card_code=await loyalty.unique_card_code(session))
            session.add(c)
            await session.flush()
            await loyalty.add_points(session, c, 100, "welcome", "Бонус за реєстрацію")
            for _ in range(random.randint(2, 9)):
                await loyalty.register_purchase(session, c, random.choice([340, 780, 1250, 2100, 3900, 650]))
            affordable = [r for r in rewards if r.cost <= c.balance]
            if affordable and random.random() < 0.6:
                await loyalty.redeem(session, c, random.choice(affordable))
        await session.commit()
    print("Готово")


asyncio.run(main())
