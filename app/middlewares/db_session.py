# app/middlewares/db_session.py
"""
Мидлварь, прокидывающая фабрику сессий в контекст хендлеров.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession


class DbSessionMiddleware(BaseMiddleware):
    """Добавляет session_factory в data для каждого апдейта."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__()
        self._factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        data["session_factory"] = self._factory
        return await handler(event, data)
