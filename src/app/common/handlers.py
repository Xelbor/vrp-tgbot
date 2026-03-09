from aiogram import types, F, Router, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from app.users.db.repositories import UserRepository, SubscriptionRepository
from app.users.services import referral_service, subscription_service
from app.common.keyboards import main_kb, buy_key_kb, buy_balance_kb, payment_keyboard, mini_app_kb
from app.users.tariffs import prices_key, prices_balance
from app.common.large_texts import *
import app.common.utils as utils
import logging
import asyncio
router = Router()

user_repo = UserRepository()

class BuyBalanceState(StatesGroup):
    waiting_for_amount = State()

class WaitTextState(StatesGroup):
    waiting_for_confirm = State()

# -------------------- START --------------------
@router.message(CommandStart())
async def main(message: types.Message):
    referral_service_instance = referral_service(user_repo)

    referral_service_instance.registered_by_referral(
        user_id=message.from_user.id,
        ref_code=referral_service_instance.parse_ref(message.text)
    )

    await message.answer(welcome_text, reply_markup=main_kb, parse_mode='HTML')
    await message.answer("ℹ️ Узнай, как получить скидку:", reply_markup=refs_inline)

@router.callback_query(F.data == "refs_call")
async def refs_callback(call: types.CallbackQuery):
    await call.answer()
    await referal_system(
        bot=call.bot,
        user_id=call.from_user.id,
        chat_id=call.message.chat.id
    )

# -------------------- BUY BALANCE --------------------
@router.callback_query(F.data == "buy_balance_call")
async def buy_balance(call: types.CallbackQuery):
    await call.answer(buy_balance_text, parse_mode='html', reply_markup=buy_balance_kb)

@router.callback_query(F.data.startswith("buy_balance"))
async def callback_buy(call: types.CallbackQuery):
    title, amount = prices_balance[call.data]
    await send_payment(
        message=call.message,
        user_id=call.from_user.id,
        amount=amount/100,
        title=title
    )

async def send_payment(message: types.Message, user_id, amount, title):
    payment = utils.create_payment(
        amount=amount,
        description=title,
        user_id=user_id
    )

    payment_url = payment.confirmation.confirmation_url

    await message.answer(
        """<b>💸 Вот ваша ссылки для оплаты.\n ⌛️ Ссылка будет активна в течении 10 минут!\n ❗️Деньги зачисляться на ваш баланс в течении 1 минуты после оплаты.</b>\n Нажимая кнопку "Оплатить", вы соглашаетесь с <a href="https://vrp-vpn.online/terms.html">Пользовательским соглашением</a> и <a href="https://vrp-vpn.online/privacy.html">Политикой конфиденциальности</a>.
        """,
        parse_mode="HTML",
        reply_markup=payment_keyboard(payment_url),
    )

@router.callback_query(F.data == "custom_balance_price")
async def buy_balance_own(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(BuyBalanceState.waiting_for_amount)

    await call.message.answer("💰 Введите сумму, на которую хотите пополнить баланс (в рублях):")


@router.message(BuyBalanceState.waiting_for_amount)
async def process_custom_amount(message: types.Message, state: FSMContext):
    print(message.text)
    print(message.from_user.id)
    if not message.text.isdigit():
        await message.answer("❌ Введите корректное число в рублях.")
        return
    
    amount_rub = int(message.text)
    if amount_rub < 10:
        await message.answer("❌ Минимальная сумма пополнения — 10₽.")
        return

    await state.clear()
    
    title = f"Пополнение баланса на {amount_rub}₽"

    await send_payment(message, user_id=message.from_user.id, amount=amount_rub, title=title)

# -------------------- BUY KEY --------------------
async def buy_key(message: types.Message):
    await message.answer(buy_key_text, parse_mode='html', reply_markup=buy_key_kb)

@router.callback_query(F.data.startswith("buy_key_"))
async def buy_key_handler(call: types.CallbackQuery):
    title, amount, days, tariff = prices_key[call.data]
    amount_rub = amount / 100

    user_balance = user_repo.get_balance(call.from_user.id)
    if(user_balance < amount_rub):
        markup = types.InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    types.InlineKeyboardButton(text='💳 Пополнить баланс', callback_data="buy_balance_call")
                ]
            ]
        )
        await call.message.answer("⚠️ <b>Не хватает денег на балансе</b> ⚠️", parse_mode='html', reply_markup=markup)
        return
    
    user_repo.uncharge_balance(call.from_user.id, amount_rub)
    
    sub_repo = SubscriptionRepository()
    subscription_service_instance = subscription_service(sub_repo)

    sub_link = await subscription_service_instance.buy_subscription(
        user_id=call.from_user.id,
        tariff=tariff,
        days=days
    )
    
    await call.message.answer(key_text + f"\n{sub_link}", parse_mode='html')

@router.callback_query(F.data == "back_to_buy")
async def buy_back(call: types.CallbackQuery):
    await buy_balance(call.message)

# -------------------- CHECK KEY --------------------
async def check_key(message: types.Message):
    status_msg = await message.answer("⏳ Проверяем ваши ключи...", parse_mode="HTML")

    sub_repo = SubscriptionRepository()
    subscription_service_instance = subscription_service(sub_repo)
    user_subscription_links = await utils.get_user_links(str(message.from_user.id))

    if not user_subscription_links:
        await status_msg.edit_text(
            "У вас пока нет активных ключей.\n\n"
            "Нажмите 🎁 <b>Бесплатный период</b> или 💳 <b>Пополнить баланс</b>",
            parse_mode="HTML"
        )
        return

    text = "<b>Ваши активные ключи:</b>\n\n"

    await subscription_service_instance.sync_subscriptions(message.from_user.id)
    
    for i, link in enumerate(user_subscription_links, start=1):
        raw_type = sub_repo.get_subscription_type(link)
        
        if raw_type and len(raw_type) > 0:
            val = raw_type[0]
            type_name = "🎁 Пробный" if val == "trial" else "💳 Платный"
        else:
            type_name = "❓ Неизвестный тип"

        end_date = await utils.get_subscribe_end_date(str(message.from_user.id), link)
        expires = end_date.strftime("%d.%m.%Y %H:%M") if end_date else "Без срока"

        text += (
            f"<b>{i}. {type_name}</b>\n"
            f" Истекает: {expires}\n"
            f" <code>{link}</code>\n\n"
        )

    await status_msg.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)

# ---------------------- GIFT ----------------------
@router.message(Command('gift'))
async def gift(message: types.Message):
    if user_repo.user_has_trial(message.from_user.id):
        await message.answer("<b>Вы уже использовали бесплатный период</b> 👀 \n\nДля просмотра ключа нажмите кнопку 🔑 Мои ключи", parse_mode='HTML')
    else:
        invited = user_repo.user_has_been_invited(message.from_user.id)

        if invited is not None:
            bonus_amount = float(os.getenv("REFS_BONUS", 25))
            print(bonus_amount)

            user_repo.add_balance(invited, bonus_amount)
            user_repo.add_referral_bonus(message.from_user.id, bonus_amount)

        sub_repo = SubscriptionRepository()
        subscription_service_instance = subscription_service(sub_repo)

        sub_link = await subscription_service_instance.give_trial(message.from_user.id)

        await message.answer(gift_text, parse_mode="HTML")
        await message.answer(f"<tg-spoiler>{sub_link}</tg-spoiler>", parse_mode='HTML')

# ---------------------- Broadcast ----------------------
@router.message(Command('broadcast'))
async def broadcast_handler(message: types.Message, state: FSMContext):
    if message.from_user.id != int(utils.SERVICE_CHAT_ID):
        await message.answer("Нет прав на выполнение команды")
        return
    
    text = message.text.replace("/broadcast", "", 1).strip()
    
    if not text:
        await message.answer("Текст рассылки пуст")
        return
    
    if text == "tech_works":
        await broadcast(message.bot, "test tech works")
        return
    
    await state.update_data(broadcast_text=text)
    await state.set_state(WaitTextState.waiting_for_confirm)

    await message.answer(
        f"{text}\n\nСообщение корректное? (y/n):",
        parse_mode="HTML"
    )

@router.message(WaitTextState.waiting_for_confirm)
async def confirm_broadcast(message: types.Message, state: FSMContext):
    answer = message.text.lower().strip()

    data = await state.get_data()
    text = data.get("broadcast_text")

    if answer == "y":
        await broadcast(message.bot, text)
        await message.answer("Рассылка завершена")
        await state.clear()

    elif answer == "n":
        await message.answer("Рассылка отменена")
        await state.clear()

    else:
        await message.answer("Ответьте 'y' или 'n'")


async def broadcast(bot: Bot, text: str):
    users = user_repo.get_all_users()

    for (user_id,) in users:
        try:
            await bot.send_message(user_id, text, parse_mode='HTML')
            await asyncio.sleep(0.05)  # защита от FloodWait
        except Exception:
            pass

# ----------------------- Balance ------------------------
@router.message(Command('balance'))
async def balance(message: types.Message):
    user_balance = user_repo.get_balance(message.from_user.id)
    await message.answer(f"💰 <b>Ваш текущий баланс:</b> {str(user_balance)}₽", parse_mode='HTML')
    
# -------------------- Referal System --------------------
async def referal_system(bot: Bot, user_id: int, chat_id: int):    
    await bot.send_message(chat_id, ref_text, parse_mode='HTML')

    row = user_repo.get_referrer_code_by_user(user_id)

    ref_code = row[0]

    if ref_code is None:
        ref_code = utils.generate_username(6)
        user_repo.set_referrer(user_id, ref_code)

    link = f"{utils.BOT_LINK}?start=ref_{ref_code}"
    await bot.send_message(
        chat_id, 
        "🎁 <b>Вот ваша ссылка для друга:</b>\n" + link,
        parse_mode='HTML'
    )

# -------------------- MARKUP BUTTONS --------------------
@router.message()
async def handle_markup_keyboard(message: types.Message):
    if message.text == "🔑 Мои ключи":
        await check_key(message)
    elif message.text == "💳 Пополнить баланс":
        await buy_balance(message)
    elif message.text == "🎁 Бесплатный период":
        await gift(message)
    elif message.text == "💰 Баланс":
        await balance(message)
    elif message.text == "💸 Скидка":
        await referal_system(bot=message.bot, user_id=message.from_user.id, chat_id=message.chat.id)
    elif message.text == "💰 Купить ключ":
        await buy_key(message)
