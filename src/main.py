from aiogram import Bot, Dispatcher
from app.common.utils import BOT_TOKEN
import asyncio
from app.common.handlers import router
from app.users.db.repositories import UserRepository
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def main():
    dp.include_router(router)

    UserRepository.create_tables()

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
