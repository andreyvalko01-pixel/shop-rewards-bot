import asyncio
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + os.path.join(tempfile.mkdtemp(), "t.sqlite").replace("\\", "/")

import pytest
from sqlalchemy import select

from bot.models import Customer, Reward, Session
from bot.seed import seed
from bot.services import loyalty
from webadmin.emulator import CHAT_ID, Emulator


def test_tiers():
    assert loyalty.tier_for(0).name == "Bronze"
    assert loyalty.tier_for(5_000).name == "Silver"
    assert loyalty.tier_for(25_000).name == "Gold"
    assert loyalty.next_tier(25_000) is None


def test_points_rounded_down():
    assert loyalty.points_for_purchase(999, 0) == 29       # 3%
    assert loyalty.points_for_purchase(1000, 6_000) == 50  # 5%


def test_codes_are_readable():
    code = loyalty.new_code(50)
    assert not set(code) & set("0O1I")


def test_bot_flow_registration_purchase_and_reward():
    async def scenario():
        await seed()
        emu = Emulator()
        await emu.send_text("/start")
        await emu.send_contact()
        assert "Нараховано 100 балів" in emu.chat.messages[-1]["text"]

        async with Session() as session:
            customer = await session.scalar(select(Customer).where(Customer.telegram_id == CHAT_ID))
            points, new_tier = await loyalty.register_purchase(session, customer, 7_000)
            await session.commit()
        assert points == 210 and new_tier.name == "Silver"

        def last_with_buttons():
            msg = next(m for m in reversed(emu.chat.messages) if m["buttons"])
            return msg["id"], [b for row in msg["buttons"] for b in row]

        mid, buttons = last_with_buttons()
        await emu.press(mid, next(b["data"] for b in buttons if "Винагороди" in b["text"]))
        mid, buttons = last_with_buttons()
        await emu.press(mid, next(b["data"] for b in buttons if "Кава" in b["text"]))
        mid, buttons = last_with_buttons()
        await emu.press(mid, buttons[0]["data"])   # "Так, обміняти"

        text = emu.chat.messages[-1]["text"]
        assert "Ваш купон" in text

        async with Session() as session:
            customer = await session.scalar(select(Customer).where(Customer.telegram_id == CHAT_ID))
            assert customer.balance == 100 + 210 - 300

            code = text.split("<code>")[1].split("</code>")[0]
            await loyalty.use_coupon(session, code)
            await session.commit()
            with pytest.raises(loyalty.LoyaltyError):
                await loyalty.use_coupon(session, code)

    asyncio.run(scenario())


def test_cannot_redeem_without_points():
    async def scenario():
        await seed()
        async with Session() as session:
            customer = Customer(telegram_id=42, name="Тест", card_code="TEST42", balance=10)
            session.add(customer)
            await session.flush()
            reward = await session.scalar(select(Reward).order_by(Reward.cost.desc()))
            with pytest.raises(loyalty.LoyaltyError):
                await loyalty.redeem(session, customer, reward)

    asyncio.run(scenario())
