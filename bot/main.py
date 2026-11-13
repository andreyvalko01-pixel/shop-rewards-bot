"""Запуск бота: python -m bot.main"""

import asyncio
import logging

from aiogram import Bot, Dispatcher

from .config import settings
from .handlers import cashier, customer
from .models import init_db

_dispatcher: Dispatcher | None = None


def build_dispatcher() -> Dispatcher:
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = Dispatcher()
        _dispatcher.include_routers(cashier.router, customer.router)
    return _dispatcher


async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    await build_dispatcher().start_polling(Bot(settings.bot_token))


if __name__ == "__main__":
    asyncio.run(main())
