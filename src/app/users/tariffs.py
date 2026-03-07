import os

PRICE_1 = int(os.getenv("PRICE_1"))
PRICE_2 = int(os.getenv("PRICE_2"))
PRICE_3 = int(os.getenv("PRICE_3"))

DAYS_1 = int(os.getenv("DAYS_1"))
DAYS_2 = int(os.getenv("DAYS_2"))
DAYS_3 = int(os.getenv("DAYS_3"))

prices_key = {
    "buy_key_14": ("Ключ на 14 дней", PRICE_1, DAYS_1, "tariff-1"),
    "buy_key_30": ("Ключ на 30 дней", PRICE_2, DAYS_2, "tariff-2"),
    "buy_key_60": ("Ключ на 60 дней", PRICE_3, DAYS_3, "tariff-3"),
}

prices_balance = {
    "buy_balance_14": ("Баланс на 14 дней подписки", PRICE_1),
    "buy_balance_30": ("Баланс на 30 дней подписки", PRICE_2),
    "buy_balance_60": ("Баланс на 60 дней подписки", PRICE_3),
}