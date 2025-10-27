# app/handlers/start.py
"""
/start — пользовательский путь (без автоперехода в админку).
Создаёт пользователя при первом входе, восстанавливает стадию.
Гасит прошлые клавиатуры, где это уместно.
"""

from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import Settings
from ..keyboards import kb_start_authorized, kb_profile_filled, kb_auth_code_wait
from ..models import User
from ..logger import setup_logging

router = Router()
setup_logging()


async def _clear_last_kb(state: FSMContext, chat_id: int, bot) -> None:
    data = await state.get_data()
    mid = data.get("last_kb_mid")
    if mid:
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=mid, reply_markup=None
            )
        except Exception:
            pass
        await state.update_data(last_kb_mid=None)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Обрабатывает /start по сценарию ТЗ (восстановление текущей стадии)."""
    async with session_factory() as session:
        user = await _get_or_create_user(
            session, message.from_user.id, message.from_user.username
        )
        user.last_activity = datetime.now(timezone.utc)

        # гасим старые кнопки, если есть
        await _clear_last_kb(state, message.chat.id, message.bot)

        if user.status == "blocked":
            await session.commit()
            await message.answer(
                "Доступ временно заблокирован. Свяжитесь с администратором."
            )
            return

        # регистрация e-mail
        if user.stage in {"new", "verifying_email", "verifying_email_error"}:
            user.stage = "verifying_email"
            await session.commit()
            await message.answer(
                "Привет! Давайте зарегистрируемся через корпоративную почту.\n"
                "Отправьте адрес (например, name@corp.com):"
            )
            return

        # ожидание OTP — показываем кнопки переотправки/смены почты
        if user.stage in {"verifying_code", "verifying_code_error"}:
            await session.commit()
            sent = await message.answer(
                "Мы уже отправили код подтверждения на вашу почту. Введите код.\n"
                "Если код истёк — воспользуйтесь кнопкой ниже.",
                reply_markup=kb_auth_code_wait(),
            )
            await state.update_data(last_kb_mid=sent.message_id)
            return

        # авторизован — предлагаем перейти к анкете
        if user.stage == "authorized":
            await session.commit()
            sent = await message.answer(
                "Успешная авторизация! Перейдём к анкете.",
                reply_markup=kb_start_authorized(),
            )
            await state.update_data(last_kb_mid=sent.message_id)
            return

        if user.stage == "profile_filled":
            # send preview with photos (if any) first, then text+buttons
            user.stage = "profile_filled"  # ensure stage is set
            await session.commit()
            # import helper to use same preview logic
            from .profile import _send_profile_preview_with_photos

            await _send_profile_preview_with_photos(
                message.bot, message.chat.id, user, state, kb_profile_filled()
            )
            return

        if user.stage in {
            "profile_name",
            "profile_photo",
            "profile_bio",
            "profile_age",
            "profile_interests",
            "profile_review",
        }:
            await session.commit()
            sent = await message.answer(
                "Продолжим заполнение анкеты. Нажмите «Анкета 🪪».",
                reply_markup=kb_start_authorized(),
            )
            await state.update_data(last_kb_mid=sent.message_id)
            return

        await session.commit()
        await message.answer("Начнём регистрацию. Отправьте ваш корпоративный e-mail.")


def _profile_preview_text(user: User) -> str:
    lines = ["📇 Ваша анкета:"]
    if user.name:
        lines.append(f"• Имя: {user.name}")
    if user.age:
        lines.append(f"• Возраст: {user.age}")
    if user.bio:
        lines.append(f"• О себе: {user.bio}")
    if user.interests_json and user.interests_json.get("interests"):
        lines.append("• Интересы: " + ", ".join(user.interests_json["interests"]))
    if user.photos_json and user.photos_json.get("photos"):
        lines.append(f"• Фото: {len(user.photos_json['photos'])} шт.")
    return "\n".join(lines)


async def _get_or_create_user(
    session: AsyncSession, tg_id: int, username: str | None
) -> User:
    res = await session.execute(select(User).where(User.telegram_id == tg_id))
    user = res.scalar_one_or_none()
    if user:
        if username and user.username != username:
            user.username = username
        return user
    user = User(
        telegram_id=tg_id, username=username, status="new", stage="new", origin="self"
    )
    session.add(user)
    await session.flush()
    return user
