from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import os

PRICE_1 = int(os.getenv("PRICE_1"))
PRICE_2 = int(os.getenv("PRICE_2"))
PRICE_3 = int(os.getenv("PRICE_3"))

DAYS_1 = int(os.getenv("DAYS_1"))
DAYS_2 = int(os.getenv("DAYS_2"))
DAYS_3 = int(os.getenv("DAYS_3"))

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔑 Мои ключи"), KeyboardButton(text="💳 Пополнить баланс")],
        [KeyboardButton(text="🎁 Бесплатный период"), KeyboardButton(text="💰 Баланс")],
        [KeyboardButton(text="💸 Скидка"), KeyboardButton(text="💰 Купить ключ")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите пункт меню."
)

buy_key_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text=f'💳 {DAYS_1} дней — {PRICE_1 / 100}₽', callback_data="buy_key_14"),
            InlineKeyboardButton(text=f'💳 {DAYS_2} дней — {PRICE_2 / 100}₽', callback_data="buy_key_30"),
        ],
        [
            InlineKeyboardButton(text=f'💳 {DAYS_3} дней — {PRICE_3 / 100}₽', callback_data="buy_key_60"),
        ]
    ]
)

buy_balance_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text=f'💳 {DAYS_1} дней — {PRICE_1 / 100}₽', callback_data="buy_balance_14"),
            InlineKeyboardButton(text=f'💳 {DAYS_2} дней — {PRICE_2 / 100}₽', callback_data="buy_balance_30"),
        ],
        [
            InlineKeyboardButton(text=f'💳 {DAYS_3} дней — {PRICE_3 / 100}₽', callback_data="buy_balance_60"),
            InlineKeyboardButton(text='💳 Своя сумма', callback_data="custom_balance_price"),
        ]
    ]
)

mini_app_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text=f'Открыть', web_app=WebAppInfo(url="https://cabinet.vrp-vpn.online/"))
        ]
    ]
)

def payment_keyboard(url: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить", url=url)]
    ])