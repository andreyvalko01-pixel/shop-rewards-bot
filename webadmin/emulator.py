"""Емулятор Telegram для локальної перевірки бота без токена.

Справжній Dispatcher з усіма обробниками отримує апдейти, а замість запитів до api.telegram.org
відповіді бота перехоплює EmulatorSession і складає їх у список — його малює сторінка /dev/chat.
"""

import itertools
from datetime import datetime

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (AnswerCallbackQuery, EditMessageReplyMarkup, EditMessageText, SendChatAction,
                             SendMessage)
from aiogram.types import CallbackQuery, Chat, Contact, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, User

from bot.main import build_dispatcher

BOT_USER = User(id=1, is_bot=True, first_name="Shop Rewards")
CHAT_ID = 1001
CLIENT = User(id=CHAT_ID, is_bot=False, first_name="Максим", last_name="Коваленко")


class EmulatorSession(BaseSession):
    def __init__(self, chat: "ChatLog"):
        super().__init__()
        self.chat = chat

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):
        raise NotImplementedError

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, SendMessage):
            msg = self.chat.add("bot", method.text, method.reply_markup)
            return self.chat.to_message(msg)
        if isinstance(method, EditMessageText):
            msg = self.chat.edit(method.message_id, text=method.text, markup=method.reply_markup)
            return self.chat.to_message(msg)
        if isinstance(method, EditMessageReplyMarkup):
            msg = self.chat.edit(method.message_id, markup=method.reply_markup)
            return self.chat.to_message(msg)
        if isinstance(method, AnswerCallbackQuery):
            if method.text:
                self.chat.toast = method.text
            return True
        if isinstance(method, SendChatAction):
            return True
        return True


class ChatLog:
    def __init__(self):
        self.messages: list[dict] = []
        self.reply_keyboard: list[list[dict]] | None = None
        self.toast: str | None = None
        self._ids = itertools.count(1)
        self._updates = itertools.count(1)

    def add(self, sender: str, text: str, markup=None) -> dict:
        msg = {"id": next(self._ids), "from": sender, "text": text, "buttons": None, "time": datetime.now().strftime("%H:%M")}
        self._apply_markup(msg, markup)
        self.messages.append(msg)
        return msg

    def edit(self, message_id: int, text: str | None = None, markup=None) -> dict:
        msg = next(m for m in self.messages if m["id"] == message_id)
        if text is not None:
            msg["text"] = text
        msg["buttons"] = None
        self._apply_markup(msg, markup)
        return msg

    def _apply_markup(self, msg: dict, markup):
        if isinstance(markup, ReplyKeyboardMarkup):
            self.reply_keyboard = [[{"text": b.text, "contact": bool(b.request_contact)} for b in row] for row in markup.keyboard]
        elif isinstance(markup, ReplyKeyboardRemove):
            self.reply_keyboard = None
        elif markup is not None:
            msg["buttons"] = [[{"text": b.text, "data": b.callback_data, "url": b.url} for b in row]
                              for row in markup.inline_keyboard]

    def to_message(self, msg: dict) -> Message:
        return Message(message_id=msg["id"], date=datetime.now(), chat=Chat(id=CHAT_ID, type="private"),
                       from_user=BOT_USER, text=msg["text"])


class Emulator:
    def __init__(self):
        self.chat = ChatLog()
        self.bot = Bot("1:EMULATOR", session=EmulatorSession(self.chat))
        self.dp = build_dispatcher()

    def _user_message(self, **kwargs) -> Message:
        return Message(message_id=next(self.chat._ids), date=datetime.now(),
                       chat=Chat(id=CHAT_ID, type="private"), from_user=CLIENT, **kwargs)

    async def send_text(self, text: str):
        self.chat.add("user", text)
        update = Update(update_id=next(self.chat._updates), message=self._user_message(text=text))
        await self.dp.feed_update(self.bot, update)

    async def send_contact(self):
        self.chat.add("user", "📱 +380 93 555 12 34")
        contact = Contact(phone_number="380935551234", first_name="Максим", user_id=CHAT_ID)
        update = Update(update_id=next(self.chat._updates), message=self._user_message(contact=contact))
        await self.dp.feed_update(self.bot, update)

    async def press(self, message_id: int, data: str):
        msg = next(m for m in self.chat.messages if m["id"] == message_id)
        query = CallbackQuery(id=str(next(self.chat._updates)), from_user=CLIENT, chat_instance="emu",
                              data=data, message=self.chat.to_message(msg))
        await self.dp.feed_update(self.bot, Update(update_id=next(self.chat._updates), callback_query=query))

    def state(self) -> dict:
        toast, self.chat.toast = self.chat.toast, None
        return {"messages": self.chat.messages, "keyboard": self.chat.reply_keyboard, "toast": toast}
