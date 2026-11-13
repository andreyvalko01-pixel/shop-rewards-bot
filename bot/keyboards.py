from aiogram.filters.callback_data import CallbackData
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder


class Menu(CallbackData, prefix="m"):
    section: str


class RewardPick(CallbackData, prefix="rw"):
    reward_id: int
    confirm: bool = False


def main_menu(notify: bool):
    kb = InlineKeyboardBuilder()
    kb.button(text="⭐ Мої бонуси", callback_data=Menu(section="balance"))
    kb.button(text="🏷 Акції", callback_data=Menu(section="promos"))
    kb.button(text="🎁 Винагороди", callback_data=Menu(section="rewards"))
    kb.button(text="🕓 Історія", callback_data=Menu(section="history"))
    kb.button(text="💳 Моя картка", callback_data=Menu(section="card"))
    kb.button(text=("🔔 Сповіщення: увімк." if notify else "🔕 Сповіщення: вимк."), callback_data=Menu(section="notify"))
    kb.adjust(2)
    return kb.as_markup()


def back():
    kb = InlineKeyboardBuilder()
    kb.button(text="← Меню", callback_data=Menu(section="menu"))
    return kb.as_markup()


def rewards_kb(rewards, balance: int):
    kb = InlineKeyboardBuilder()
    for r in rewards:
        mark = "✅" if balance >= r.cost else "🔒"
        kb.button(text=f"{mark} {r.title} — {r.cost} балів", callback_data=RewardPick(reward_id=r.id))
    kb.button(text="← Меню", callback_data=Menu(section="menu"))
    kb.adjust(1)
    return kb.as_markup()


def confirm_reward(reward_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="Так, обміняти", callback_data=RewardPick(reward_id=reward_id, confirm=True))
    kb.button(text="Ні", callback_data=Menu(section="rewards"))
    kb.adjust(2)
    return kb.as_markup()


def share_phone():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поділитися номером", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )


remove = ReplyKeyboardRemove()
