import os
import random
import string
from datetime import datetime, timedelta
import pytz
from remnawave import RemnawaveSDK
from remnawave.models import UserResponseDto, CreateUserRequestDto, UpdateUserRequestDto, HWIDDeleteRequest
from yookassa import Configuration, Payment
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)

DB_PATH = "/app/data/users.db"

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_LINK = os.getenv("BOT_LINK")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")

SERVICE_CHAT_ID = os.getenv("SERVICE_CHAT_ID")

Configuration.account_id = os.getenv("SHOP_ID")
Configuration.secret_key = os.getenv("SHOP_SECRET_KEY")

base_url: str = os.getenv("REMNAWAVE_BASE_URL")
token: str = os.getenv("REMNAWAVE_TOKEN")

remnawave = RemnawaveSDK(base_url=base_url, token=token)

def generate_username(length=10):
    chars = string.ascii_lowercase + string.digits
    name = ''.join(random.choice(chars) for _ in range(length))
    return f"{name}"

def generate_email(length=10):
    return generate_username(length) + "@mail.com"

async def create_a_subscribe_link(telegram_id, expiryTime, tariff):
    username = generate_username()

    match tariff:
        case "trial":
            external_squad_uuid = 'd7f71a0d-0769-485f-bfad-33d0d27fa0bf'
        case "tariff-1":
            external_squad_uuid = 'a9dddb0e-1b30-4792-b11e-55f73153e5e3'
        case "tariff-2":
            external_squad_uuid = '486e8d21-b21f-44da-8905-0f8027054c93'
        case "tariff-3":
            external_squad_uuid = 'c7c7625b-3f03-40e5-a3e8-722fa01c7fda'

    try:
        await remnawave.users.create_user(
            CreateUserRequestDto(
                username=username,
                telegram_id=telegram_id,
                expire_at=datetime.now(tz=pytz.UTC) + timedelta(days=expiryTime),
                active_internal_squads=['f92bea77-ab89-4f2c-bb60-2a7e4ad95257'],
                external_squad_uuid=external_squad_uuid
            )
        )

        user: UserResponseDto = await remnawave.users.get_user_by_username(username)

        if not user or not user.subscription_url:
            return False
        
        return user.subscription_url
    
    except Exception as e:
        logger.error(f"Error while creating subscribe link: {e}")
        return e
    
async def expand_subscribe_link(telegram_id: int, sub_link: str, days: int):
    try:
        users = await remnawave.users.get_users_by_telegram_id(str(telegram_id))

        if not users:
            return False
        
        for user in users:
            uuid = user.uuid
            if user.subscription_url == sub_link:
                now = datetime.now(tz=pytz.UTC)

                base_date = user.expire_at if user.expire_at > now else now
                new_expire = base_date + timedelta(days=days)

                await remnawave.users.update_user(
                    UpdateUserRequestDto(
                        uuid=uuid,
                        expire_at=new_expire
                    )
                )

                return True
                

    except Exception as e:
        print(e)
        return False

async def delete_a_subscribe_link(telegram_id, sub_link):
    try:
        users = await remnawave.users.get_users_by_telegram_id(telegram_id)

        for user in users:
            if user.subscription_url == sub_link:
                uuid = user.uuid

                await remnawave.users.delete_user(str(uuid))
                return True
    
    except Exception as e:
        print(e)
    
    return False

async def get_user_traffic(user_id: int, sub_link) -> int | None:
    try:
        users = await remnawave.users.get_users_by_telegram_id(user_id)

        if not users:
            return None
        
        for user in users:
            if user.subscription_url == sub_link:
                return user.user_traffic.used_traffic_bytes

    except Exception as e:
        print(e)
        return None
    
async def get_user_links(user_id):
    try:
        users = await remnawave.users.get_users_by_telegram_id(user_id)

        if not users:
            return None
        
        return [user.subscription_url for user in users if user.subscription_url]
    
    except Exception as e:
        print(e)
        return None

    
async def get_subscribtion_status(user_id, sub_link):
    try:
        users = await remnawave.users.get_users_by_telegram_id(user_id)

        if not users:
            return None
        
        for user in users:
            if user.subscription_url == sub_link:
                return user.status
    
    except Exception as e:
        print(e)
        return None

async def get_subscribe_end_date(user_id, vpn_key):
    try:
        users = await remnawave.users.get_users_by_telegram_id(user_id)

        if not users:
            return None
        
        # Перебираем всех пользователей, привязанных к этому telegram_id
        for user in users:
            # Сравниваем subscription_url с тем, что передал пользователь
            # (или можно сравнивать user.short_uuid, если vpn_key — это только ID)
            if user.subscription_url == vpn_key:
                return user.expire_at
        
        # Если цикл закончился и ничего не нашли
        return None
    
    except Exception as e:
        print(f"Ошибка при получении даты: {e}")
        return None


    
async def get_user_devices(user_id, sub_link):
    try:
        users = await remnawave.users.get_users_by_telegram_id(user_id)

        if not users:
            return None
        
        for user in users:
            if user.subscription_url == sub_link:
                uuid = user.uuid
                devices = await remnawave.hwid.get_hwid_user(str(uuid))
        
                return {
                    "total": devices.total,
                    "devices": [
                        {
                            "hwid_uuid": d.hwid,
                            "platform": d.platform,
                            "device_model": d.device_model
                        }
                        for d in devices.devices
                    ]
                }
    
    except Exception as e:
        print(e)
        return None
    
async def delete_user_device(user_id, sub_link, hwid):
    try:
        users = await remnawave.users.get_users_by_telegram_id(user_id)

        if not users:
            return None
        
        for user in users:
            if user.subscription_url == sub_link:
                uuid = user.uuid
        
                delete = await remnawave.hwid.delete_hwid_to_user(
                    HWIDDeleteRequest(
                        user_uuid=str(uuid),
                        hwid=str(hwid)
                    )
                )
                return delete
    
    except Exception as e:
        print(e)
        return None

def create_payment(amount: float, description: str, user_id: int):
    payment = Payment.create({
        "amount": {
            "value": f"{amount}",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://www.vrp-vpn.online/successful-payment"
        },
        "capture": True,
        "description": f"{description}",
        "metadata": {
            "user_id": str(user_id)
        }
    })

    return payment

def create_payment_with_method(amount: float, method: str, description: str, user_id: int):
    payment = Payment.create({
        "amount": {
            "value": f"{amount}",
            "currency": "RUB"
        },
        "payment_method_data": {
            "type": f"{method}"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://www.vrp-vpn.online/successful-payment"
        },
        "capture": True,
        "description": f"{description}",
        "metadata": {
            "user_id": str(user_id)
        }
    })

    return payment
