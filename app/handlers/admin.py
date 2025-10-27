# app/handlers/admin.py
"""
Админ-панель только по /admin (ТЗ 8.*), доступ:
- если есть роль 'admin' (roles/user_roles) ИЛИ id в ADMIN_IDS, и при этом status != blocked.
Синхронизация ролей с .env.
Логирование всех действий в admin_log.
"""

from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import Settings
from ..keyboards import kb_admin_decision
from ..models import User, Role, UserRole, AdminLog, AuthAttempt

router = Router()


async def _get_user(session: AsyncSession, tg_id: int) -> User | None:
    return (await session.execute(select(User).where(User.telegram_id == tg_id))).scalar_one_or_none()


async def _is_admin(session: AsyncSession, settings: Settings, tg_id: int) -> bool:
    user = await _get_user(session, tg_id)
    # Если пользователя нет, но tg_id в ADMIN_IDS — создадим пользователя и продолжим синхронизацию ролей (п.8.3)
    if not user:
        if tg_id in settings.admin_ids:
            user = User(telegram_id=tg_id, username=None, status="new", stage="new")
            session.add(user)
            await session.flush()
        else:
            return False

    if tg_id in settings.admin_ids:
        # синхронизируем роль
        role = (await session.execute(select(Role).where(Role.name == "admin"))).scalar_one_or_none()
        if not role:
            role = Role(name="admin")
            session.add(role)
            await session.flush()
        link = (
            await session.execute(select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id))
        ).scalar_one_or_none()
        if not link:
            session.add(UserRole(user_id=user.id, role_id=role.id))
            await session.flush()

    # проверяем по ролям
    q = select(Role).join(UserRole, UserRole.role_id == Role.id).where(UserRole.user_id == user.id, Role.name == "admin")
    return (await session.execute(q)).scalar_one_or_none() is not None


@router.message(Command("admin"))
async def cmd_admin(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    async with session_factory() as session:
        user = await _get_user(session, message.from_user.id)
        if not user:
            # создаём, если tg_id ∈ ADMIN_IDS (ТЗ 8.3)
            if message.from_user.id in settings.admin_ids:
                user = User(
                    telegram_id=message.from_user.id,
                    username=message.from_user.username,
                    status="new",
                    stage="new",
                )
                session.add(user)
                await session.flush()
            else:
                await message.answer("⛔️ Нет прав.")
                return

        if user.status == "blocked":
            await message.answer("⛔️ Нет прав (пользователь заблокирован).")
            return

        if not await _is_admin(session, settings, message.from_user.id):
            await message.answer("⛔️ Нет прав.")
            return

        user.last_activity = datetime.now(timezone.utc)
        session.add(
            AdminLog(
                admin_telegram_id=message.from_user.id,
                action="open_admin",
                payload={"user_id": user.id},
            )
        )
        await session.commit()

        await message.answer("Админ-панель открыта.\nДействия по заявкам будут приходить в админ-чат при блокировках.")


@router.callback_query()
async def admin_callbacks(
    cq: CallbackQuery,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    data = cq.data or ""
    if not (data.startswith("admin:block:") or data.startswith("admin:unblock:")):
        return

    async with session_factory() as session:
        if not await _is_admin(session, settings, cq.from_user.id):
            await cq.answer("Нет прав")
            return

        _, action, user_id_str = data.split(":")
        target_id = int(user_id_str)
        user = (await session.execute(select(User).where(User.id == target_id))).scalar_one_or_none()
        if not user:
            await cq.answer("Пользователь не найден")
            return

        reviewed_by = cq.from_user.username or str(cq.from_user.id)
        if action == "block":
            user.status = "blocked"
            session.add(AdminLog(admin_telegram_id=cq.from_user.id, action="block", payload={"user_id": user.id}))
            await session.commit()
            # Отредактируем исходное сообщение заявки: отметим решение и уберём кнопки
            try:
                await cq.message.edit_text(cq.message.text + f"\n\nРешение: Пользователь {'@' + user.username} заблокирован.\n👨‍💻Рассмотрел: {'@' + reviewed_by}")
            except Exception:
                pass
            # Попробуем уведомить пользователя
            if user.telegram_id:
                try:
                    await cq.message.bot.send_message(user.telegram_id, "Решение по временной блокировке: Вам закрыт доступ. Если считаете это ошибкой - обратитесь к администратору.")
                except Exception:
                    pass
        else:
            # Разблокировать: status=new, stage=verifying_email, counters reset
            user.status = "new"
            user.stage = "verifying_email"
            user.email_attempts = 0
            user.otp_attempts = 0
            session.add(AdminLog(admin_telegram_id=cq.from_user.id, action="unblock", payload={"user_id": user.id}))
            await session.commit()
            # Редактируем исходное сообщение заявки
            try:
                await cq.message.edit_text(cq.message.text + f"\n\nРешение: Пользователь {'@' + user.username} разблокирован и возвращён к вводу корпоративного e‑mail.\n👨‍💻Рассмотрел: {'@' + reviewed_by}")
            except Exception:
                pass
            # Уведомляем пользователя
            if user.telegram_id:
                try:
                    await cq.message.bot.send_message(user.telegram_id, "Решение по временной блокировке: Вас разблокировали. Пожалуйста, пройдите регистрацию заново и введите корпоративный e‑mail:")
                except Exception:
                    pass
        # Убираем inline-кнопки у исходного сообщения, если они остались
        try:
            await cq.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await cq.answer()
