import json
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from yookassa import Payment, Configuration
from yookassa.domain.notification import WebhookNotification
from app.users.db.repositories import UserRepository, SubscriptionRepository
from app.users.services import subscription_service
import app.common.utils as utils
import logging
import os
from init_data_py import InitData
from datetime import datetime, timedelta
import jwt

JWT_AT_SECRET = os.getenv("JWT_AT_SECRET")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)

app = FastAPI()
security = HTTPBearer()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://cabinet.vrp-vpn.online"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

user_repo = UserRepository()
sub_repo = SubscriptionRepository()

Configuration.account_id = os.getenv("SHOP_ID")
Configuration.secret_key = os.getenv("SHOP_SECRET_KEY")


# -------------------------
# Helpers
# -------------------------

def get_payment_from_yookassa(payment_id: str):
    logger.info("Payment_id is: %s", payment_id)
    try:
        return Payment.find_one(payment_id)
    except Exception:
        return None

def get_current_user(credentials=Depends(security)):
    if not credentials:
        logger.error("No credentials provided by HTTPBearer")
        raise HTTPException(status_code=401, detail="NO_CREDENTIALS")

    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            JWT_AT_SECRET,
            algorithms=["HS256"]
        )

        if payload.get("type") != "access":
            logger.error("Wrong token type: %s", payload.get("type"))
            raise HTTPException(status_code=401, detail="WRONG_TOKEN_TYPE")

        return payload["id"]

    except jwt.ExpiredSignatureError:
        logger.error("Token expired")
        raise HTTPException(status_code=401, detail="ACCESS_TOKEN_EXPIRED")

    except jwt.InvalidSignatureError:
        logger.error("Invalid token signature")
        raise HTTPException(status_code=401, detail="INVALID_SIGNATURE")

    except jwt.DecodeError as e:
        logger.error("Decode error: %s", str(e))
        raise HTTPException(status_code=401, detail="DECODE_ERROR")

    except jwt.PyJWTError as e:
        logger.error("JWT error: %s", str(e))
        raise HTTPException(status_code=401, detail="INVALID_TOKEN")

    except Exception as e:
        logger.exception("Unexpected auth error")
        raise HTTPException(status_code=401, detail="AUTH_ERROR")
    
def create_access_token(user_id: int):
    payload = {
        "id": user_id,
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=15)
    }
    return jwt.encode(payload, JWT_AT_SECRET, algorithm="HS256")


def create_refresh_token(user_id: int):
    payload = {
        "id": user_id,
        "type": "refresh",
        "exp": datetime.utcnow() + timedelta(days=30)
    }
    return jwt.encode(payload, JWT_AT_SECRET, algorithm="HS256")

# -------------------------
# Schemas
# -------------------------

class AuthRequest(BaseModel):
    initData: str

class RefreshRequest(BaseModel):
    refresh_token: str

class chargeBalanceRequest(BaseModel):
    amount: int
    method: str

class DeleteHwidRequest(BaseModel):
    hwid: str

class buyKeyRequest(BaseModel):
    tariff: str


# -------------------------
# Webhook
# -------------------------

@app.post("/api/yookassa/webhook")
async def yookassa_webhook(request: Request):
    try:
        event_json = await request.json()
    except Exception:
        logger.warning("Invalid JSON")
        return JSONResponse({"error": "invalid json"}, status_code=400)

    logger.info("Webhook received")
    logger.info("Raw body: %s", event_json)

    if not event_json:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    try:
        notification = WebhookNotification(event_json)
    except Exception:
        logger.exception("Failed to parse WebhookNotification")
        return JSONResponse({"error": "invalid notification"}, status_code=400)

    logger.info("Event type: %s", notification.event)

    if notification.event != "payment.succeeded":
        return {"status": "ignored"}

    payment_from_hook = notification.object
    payment_id = payment_from_hook.id

    if user_repo.is_payment_processed(payment_id):
        return {"status": "already processed"}

    payment = get_payment_from_yookassa(payment_id)

    if payment is None:
        logger.error("Payment not found: %s", payment_id)
        return {"error": "payment not found"}

    if payment.status != "succeeded":
        return {"status": "not succeeded"}

    try:
        user_id = int(payment.metadata.get("user_id"))
        amount = float(payment.amount.value)
    except Exception:
        logger.exception("Invalid metadata")
        return {"error": "invalid metadata"}

    try:
        user_repo.add_balance(user_id, amount)
        user_repo.mark_payment_processed(payment_id, user_id, amount)
    except Exception:
        logger.exception("DB error")
        return JSONResponse({"error": "db error"}, status_code=500)

    return {"status": "ok"}



# -------------------------
# Auth
# -------------------------
@app.post("/api/auth/telegram")
def auth_telegram(data: AuthRequest):

    init_data = InitData.parse(data.initData)

    if not init_data.validate(
        bot_token=utils.BOT_TOKEN,
        lifetime=3600,
    ):
        raise HTTPException(status_code=401, detail="INVALID_INIT_DATA")

    telegram_user = init_data.user

    telegram_id = telegram_user.id

    # создать или получить пользователя
    user_repo.create_user_if_not_exists(telegram_id)

    access_token = create_access_token(telegram_id)
    refresh_token = create_refresh_token(telegram_id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@app.post("/api/auth/refresh")
def refresh(data: RefreshRequest):
    try:
        payload = jwt.decode(
            data.refresh_token,
            JWT_AT_SECRET,
            algorithms=["HS256"]
        )

        if payload["type"] != "refresh":
            raise HTTPException(status_code=401, detail="INVALID_TOKEN")

        user_id = payload["id"]

        new_access_token = create_access_token(user_id)

        return {
            "access_token": new_access_token
        }

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="REFRESH_TOKEN_EXPIRED")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="INVALID_TOKEN")

# -------------------------
# Home
# -------------------------
@app.post("/api/home")
async def home(user_id: int = Depends(get_current_user)):
    subscription_service_instance = subscription_service(sub_repo)
    
    await subscription_service_instance.sync_subscriptions(user_id)
    
    balance = user_repo.get_balance(user_id)
    
    user_subscription_links = await utils.get_user_links(str(user_id))

    if user_subscription_links is None:
        return {
            "balance": balance,
            "subscriptions": []
        }

    subscriptions_data = []

    for sub in user_subscription_links:
        type = sub_repo.get_subscription_type(sub)

        status = await utils.get_subscribtion_status(str(user_id), sub)
        end_date = await utils.get_subscribe_end_date(str(user_id), sub)
        traffic = await utils.get_user_traffic(str(user_id), sub)
        traffic_limit = await utils.get_user_traffic(str(user_id), sub)
        devices = await utils.get_user_devices(str(user_id), sub)

        subscriptions_data.append({
            "link": sub,
            "type": type,
            "status": status,
            "end_date": end_date,
            "traffic": traffic,
            "traffic_limit": traffic_limit,
            "devices": devices
        })

    return {
        "balance": balance,
        "subscriptions": subscriptions_data
    }


# -------------------------
# Balance
# -------------------------
@app.post("/api/balance")
async def balance(user_id: int = Depends(get_current_user)):
    logger.info("Balance endpoint called for user_id: %s", user_id)

    balance = user_repo.get_balance(user_id)

    logger.info("User balance: %s", balance)

    return {
        "balance": balance,
    }

@app.post("/api/chargeBalance")
async def chargeBalance(request_data: chargeBalanceRequest, user_id: int = Depends(get_current_user)):
    payment = utils.create_payment_with_method(request_data.amount, request_data.method, "Пополнение баланса", user_id)
    payment_url = payment.confirmation.confirmation_url

    return {
        "payment_link": payment_url,
    }

# -------------------------
# Delete HWID
# -------------------------

@app.post("/api/delete_hwid_user")
async def delete_hwid_user(request_data: DeleteHwidRequest, user_id: int = Depends(get_current_user)):
    user_link = sub_repo.get_active_paid(user_id)
    result = await utils.delete_user_device(str(user_id), user_link, request_data.hwid)

    if result is None:
        raise HTTPException(status_code=500, detail="error")

    return {"status": "ok", "result": str(result)}


# -------------------------
# Buy key
# -------------------------

@app.post("/api/buykey")
async def buyKey(request_data: buyKeyRequest, user_id: int = Depends(get_current_user)):
    match request_data.tariff:
        case "trial":
            if user_repo.user_has_trial(user_id):
                raise HTTPException(
                    status_code=400,
                    detail="TRIAL_ALREADY_USED"
                )

            invited = user_repo.user_has_been_invited(user_id)

            if invited is not None:
                bonus_amount = float(os.getenv("REFS_BONUS", 25))

                user_repo.add_balance(invited, bonus_amount)
                user_repo.add_referral_bonus(user_id, bonus_amount)

            subscription_service_instance = subscription_service(sub_repo)

            await subscription_service_instance.give_trial(
                user_id,
                15
            )

            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "type": "trial"
                }
            )

        case "paid_1":
            amount = int(os.getenv("PRICE_1"))
            amount_rub = amount / 100
            user_balance = user_repo.get_balance(user_id)
            if(user_balance < amount_rub):
                return JSONResponse(
                    status_code=400,
                    content={
                        "NOT_ENOUGH_MONEY_ON_BALANCE"
                    }
                )

            user_repo.uncharge_balance(user_id, amount_rub)

            subscription_service_instance = subscription_service(sub_repo)
            await subscription_service_instance.buy_subscription(
                user_id=user_id,
                tariff='tariff-1',
                days=int(os.getenv("DAYS_1"))
            )

            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "type": "trial"
                }
            )

        case "paid_2":
            amount = int(os.getenv("PRICE_2"))
            amount_rub = amount / 100
            user_balance = user_repo.get_balance(user_id)
            if(user_balance < amount_rub):
                return JSONResponse(
                    status_code=400,
                    content={
                        "NOT_ENOUGH_MONEY_ON_BALANCE"
                    }
                )

            user_repo.uncharge_balance(user_id, amount_rub)

            subscription_service_instance = subscription_service(sub_repo)
            await subscription_service_instance.buy_subscription(
                user_id=user_id,
                tariff='tariff-2',
                days=int(os.getenv("DAYS_2"))
            )

            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "type": "trial"
                }
            )

        case _:
            amount = int(os.getenv("PRICE_3"))
            amount_rub = amount / 100
            user_balance = user_repo.get_balance(user_id)
            if(user_balance < amount_rub):
                return JSONResponse(
                    status_code=400,
                    content={
                        "NOT_ENOUGH_MONEY_ON_BALANCE"
                    }
                )

            user_repo.uncharge_balance(user_id, amount_rub)

            subscription_service_instance = subscription_service(sub_repo)
            await subscription_service_instance.buy_subscription(
                user_id=user_id,
                tariff='tariff-3',
                days=int(os.getenv("DAYS_3"))
            )

            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "type": "trial"
                }
            )
            
# -------------------------
# Refferals
# -------------------------
@app.post("/api/refferals")
async def referrals(user_id: int = Depends(get_current_user)):
    invited_count = user_repo.count_invited_users(user_id)
    trial_count = user_repo.count_invited_with_trial(user_id)
    total_bonus = user_repo.get_total_referral_earnings(user_id)

    row = user_repo.get_referrer_code_by_user(user_id)

    ref_code = row[0]

    if ref_code is None:
        ref_code = utils.generate_username(6)
        user_repo.set_referrer(user_id, ref_code)

    invite_link = f"{utils.BOT_LINK}?start=ref_{ref_code}"

    return {
        "invited": invited_count,
        "trial": trial_count,
        "total_bonus": total_bonus,
        "invite_link": invite_link
    }