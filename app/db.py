# app/db.py
"""
Инициализация асинхронной БД (SQLAlchemy 2.x, async).
В dev по умолчанию — SQLite (aiosqlite), URL берётся из .env.
Создание таблиц происходит автоматически при старте (для prod — миграции).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import Settings


def make_engine(settings: Settings):
    """Создаёт AsyncEngine для SQLAlchemy."""
    return create_async_engine(
        settings.db_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )


def make_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Создаёт фабрику сессий."""
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def lifespan_db(settings: Settings) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """
    Контекст жизненного цикла БД:
    - создаёт engine,
    - создаёт таблицы,
    - отдаёт фабрику сессий,
    - закрывает engine по завершении.
    """
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)

    from .models import Base as _Base  # импорт отложенно, чтобы не образовать циклы

    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)

    try:
        yield session_factory
    finally:
        await engine.dispose()
