# app/bot.py
"""
Сборка бота: конфиг, БД, логирование, middlewares, регистрация роутеров.
Порядок роутеров важен: profile перед registration, чтобы текст анкеты не перехватывался регистрацией.
"""

from __future__ import annotations

from aiogram import Bot, Dispatcher

from .config import Settings
from .db import lifespan_db
from .logger import setup_logging
from .middlewares.db_session import DbSessionMiddleware

# handlers
from .handlers.start import router as start_router
from .handlers.profile import router as profile_router  # ← раньше
from .handlers.registration import router as registration_router  # ← после анкеты
from .handlers.admin import router as admin_router


async def create_dispatcher(settings: Settings) -> Dispatcher:
    """Создаёт Dispatcher и регистрирует роутеры."""
    setup_logging(settings.log_level)
    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(profile_router)  # важно: анкета выше
    dp.include_router(registration_router)  # регистрация ниже
    dp.include_router(admin_router)
    return dp


async def run_bot() -> None:
    """Точка запуска: инициализирует всё и стартует polling."""
    settings = Settings.load()
    bot = Bot(token=settings.bot_token)
    dp = await create_dispatcher(settings)

    async with lifespan_db(settings) as session_factory:
        dp.update.outer_middleware(DbSessionMiddleware(session_factory))
        dp["settings"] = settings
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, settings=settings)
