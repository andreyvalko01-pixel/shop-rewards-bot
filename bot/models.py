from datetime import date, datetime
from pathlib import Path

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import settings

if settings.database_url.startswith("sqlite"):
    Path(settings.database_url.split("///")[-1]).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(settings.database_url)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(20))
    # короткий код картки, який клієнт показує на касі
    card_code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)
    total_spent: Mapped[int] = mapped_column(Integer, default=0)   # сума покупок, грн — від неї залежить рівень
    notify: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="customer", order_by="Transaction.id.desc()")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    points: Mapped[int] = mapped_column(Integer)                  # + нарахування, − списання
    kind: Mapped[str] = mapped_column(String(20))                  # purchase / reward / welcome / manual
    description: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    customer: Mapped[Customer] = relationship(back_populates="transactions")


class Reward(Base):
    __tablename__ = "rewards"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(100))
    cost: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(default=True)


class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    reward_id: Mapped[int] = mapped_column(ForeignKey("rewards.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)

    reward: Mapped[Reward] = relationship(lazy="selectin")
    customer: Mapped[Customer] = relationship(lazy="selectin")


class Promo(Base):
    __tablename__ = "promos"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)
    valid_until: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
