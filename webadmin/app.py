"""Панель магазину: статистика, нарахування балів з каси, акції з розсилкою + емулятор чату.

Запуск: uvicorn webadmin.app:app --port 8080
"""

import asyncio
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import func, select

from bot.config import settings
from bot.models import Coupon, Customer, Promo, Session, Transaction, init_db
from bot.services import loyalty

BASE = Path(__file__).parent
app = FastAPI(title="Shop Rewards — панель")
templates = Jinja2Templates(directory=BASE / "templates")
security = HTTPBasic()


@app.on_event("startup")
async def startup():
    await init_db()


def admin_only(credentials: HTTPBasicCredentials = Depends(security)):
    if not (secrets.compare_digest(credentials.username, settings.web_admin_user)
            and secrets.compare_digest(credentials.password, settings.web_admin_password)):
        raise HTTPException(401, headers={"WWW-Authenticate": "Basic"})


async def send_to_customer(telegram_id: int, text: str):
    """У проді — справжній бот; поки працює емулятор, повідомлення потрапляє в нього."""
    if emulator and telegram_id == emulator_chat_id():
        await emulator.bot.send_message(telegram_id, text)
        return
    from aiogram import Bot

    bot = Bot(settings.bot_token)
    try:
        await bot.send_message(telegram_id, text)
    except Exception:
        pass
    finally:
        await bot.session.close()


@app.get("/", dependencies=[Depends(admin_only)])
async def dashboard(request: Request, msg: str | None = None):
    month_ago = datetime.now() - timedelta(days=30)
    async with Session() as session:
        customers = await session.scalar(select(func.count(Customer.id)))
        new_customers = await session.scalar(select(func.count(Customer.id)).where(Customer.created_at >= month_ago))
        issued = await session.scalar(select(func.coalesce(func.sum(Transaction.points), 0))
                                      .where(Transaction.points > 0, Transaction.created_at >= month_ago))
        spent = await session.scalar(select(func.coalesce(func.sum(-Transaction.points), 0))
                                     .where(Transaction.points < 0, Transaction.created_at >= month_ago))
        coupons_used = await session.scalar(select(func.count(Coupon.id)).where(Coupon.used_at.isnot(None)))
        recent = (await session.execute(
            select(Transaction, Customer).join(Customer).order_by(Transaction.id.desc()).limit(12)
        )).all()
        top = (await session.scalars(select(Customer).order_by(Customer.total_spent.desc()).limit(6))).all()
        promos = (await session.scalars(select(Promo).order_by(Promo.id.desc()).limit(4))).all()

    return templates.TemplateResponse(request, "dashboard.html", {
        "customers": customers, "new_customers": new_customers, "issued": issued, "spent": spent,
        "coupons_used": coupons_used, "recent": recent, "top": top, "promos": promos,
        "tier_for": loyalty.tier_for, "msg": msg,
    })


@app.post("/purchase", dependencies=[Depends(admin_only)])
async def purchase(card_code: str = Form(...), amount: int = Form(...)):
    async with Session() as session:
        customer = await session.scalar(select(Customer).where(Customer.card_code == card_code.strip().upper()))
        if not customer:
            return RedirectResponse("/?msg=Картку+не+знайдено", status_code=303)
        points, new_tier = await loyalty.register_purchase(session, customer, amount)
        await session.commit()

    text = f"🛍 Дякуємо за покупку на {amount} грн!\n+{points} балів, на рахунку {customer.balance}."
    if new_tier:
        text += f"\n\n{new_tier.emoji} Ви перейшли на рівень {new_tier.name} — тепер {new_tier.percent}% з кожної покупки!"
    await send_to_customer(customer.telegram_id, text)
    return RedirectResponse(f"/?msg={customer.name}:+{points}+балів", status_code=303)


@app.post("/promos", dependencies=[Depends(admin_only)])
async def create_promo(title: str = Form(...), text: str = Form(...), valid_until: date | None = Form(None),
                       broadcast: bool = Form(False)):
    async with Session() as session:
        session.add(Promo(title=title, text=text, valid_until=valid_until))
        await session.commit()
        ids = (await session.scalars(select(Customer.telegram_id).where(Customer.notify))).all() if broadcast else []

    for telegram_id in ids:
        await send_to_customer(telegram_id, f"🏷 {title}\n\n{text}")
        await asyncio.sleep(0.05)
    return RedirectResponse(f"/?msg=Акцію+створено,+розіслано:+{len(ids)}", status_code=303)


# ---------- емулятор ----------

emulator = None


def emulator_chat_id():
    from .emulator import CHAT_ID
    return CHAT_ID


class EmuIn(BaseModel):
    text: str | None = None
    contact: bool = False
    message_id: int | None = None
    data: str | None = None


def get_emulator():
    global emulator
    if emulator is None:
        from .emulator import Emulator
        emulator = Emulator()
    return emulator


@app.get("/dev/chat")
def chat_page():
    return FileResponse(BASE / "templates" / "chat.html")


@app.get("/dev/chat/state")
async def chat_state():
    return get_emulator().state()


@app.post("/dev/chat/send")
async def chat_send(data: EmuIn):
    emu = get_emulator()
    if data.contact:
        await emu.send_contact()
    elif data.data:
        await emu.press(data.message_id, data.data)
    elif data.text:
        await emu.send_text(data.text)
    return emu.state()
