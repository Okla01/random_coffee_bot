# app/handlers/registration.py
"""
Регистрация через e-mail и OTP (ТЗ 4–6), с корректным гашением кнопок:
- проверка e-mail по regex и доменам,
- учёт попыток и автоблок,
- генерация, отправка и переотправка OTP c лимитами (TTL, cooldown 120с, ≤3 resend/сессию),
- проверка кода, переход к 'authorized',
- заявки админам с последними 3 значениями,
- снятие старых инлайн-кнопок после любого действия пользователя.

Стадии: verifying_email / verifying_email_error / verifying_code / verifying_code_error / authorized.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.dispatcher.event.bases import SkipHandler

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import Settings
from ..keyboards import kb_auth_code_wait, kb_start_authorized, kb_admin_decision
from ..models import User, Otp, AuthAttempt, AdminLog
from ..utils.email_sender import send_otp_email
from ..utils.security import validate_email, generate_otp
from ..utils.dt import now_utc, ensure_aware_utc

router = Router()


# --------------------------- helpers ---------------------------- #


async def _user(session: AsyncSession, tg_id: int) -> User:
    """Возвращает пользователя или создаёт нового (status=new, stage=new, origin='self')."""
    res = await session.execute(select(User).where(User.telegram_id == tg_id))
    user = res.scalar_one_or_none()
    if user:
        return user
    # Если пользователя нет — создаём (аналогично /start)
    user = User(
        telegram_id=tg_id, username=None, status="new", stage="new", origin="self"
    )
    session.add(user)
    await session.flush()
    return user


async def _log_attempt(
    session: AsyncSession, user_id: int, typ: str, value: str
) -> None:
    # Сохраним попытку и оставим только последние 3 для данного user_id/type
    session.add(AuthAttempt(user_id=user_id, type=typ, value=value))
    await session.flush()
    # Оставляем только последние 3 записи; удаляем более старые
    q = (
        select(AuthAttempt)
        .where(AuthAttempt.user_id == user_id, AuthAttempt.type == typ)
        .order_by(desc(AuthAttempt.ts))
    )
    rows = list((await session.execute(q)).scalars())
    if len(rows) > 3:
        for old in rows[3:]:
            session.delete(old)


async def _last_attempts(
    session: AsyncSession, user_id: int, typ: str, limit: int = 3
) -> list[AuthAttempt]:
    q = (
        select(AuthAttempt)
        .where(AuthAttempt.user_id == user_id, AuthAttempt.type == typ)
        .order_by(desc(AuthAttempt.ts))
        .limit(limit)
    )
    return list((await session.execute(q)).scalars())


async def _clear_last_kb(state: FSMContext, chat_id: int, bot) -> None:
    """Снимает клавиатуру у последнего нашего сообщения, если оно есть."""
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


async def _send_or_resend_otp(
    session: AsyncSession, settings: Settings, user: User
) -> tuple[bool, str | None]:
    """
    Создаёт новую "сессию" OTP, либо переотправляет существующую с соблюдением ограничений:
    - не чаще 1 раза в 120 секунд,
    - не более 3 переотправок за одну сессию,
    - TTL кода settings.otp_ttl_seconds.
    """
    now = now_utc()

    existing = (
        (
            await session.execute(
                select(Otp)
                .where(Otp.user_id == user.id, Otp.used_at.is_(None))
                .order_by(desc(Otp.created_at))
            )
        )
        .scalars()
        .first()
    )

    warn: str | None = None

    if existing:
        ex_expires_at = ensure_aware_utc(existing.expires_at)
        ex_last_sent_at = ensure_aware_utc(existing.last_sent_at)

        if ex_expires_at and ex_expires_at > now:
            if (
                ex_last_sent_at
                and (ex_last_sent_at + timedelta(seconds=settings.otp_cooldown_seconds))
                > now
            ):
                warn = "Повторная отправка возможна не чаще, чем раз в 120 секунд."
            else:
                if existing.resend_count >= settings.resend_max_per_session:
                    warn = "Достигнут лимит переотправок для этой сессии."
                else:
                    await send_otp_email(settings, user.email, existing.code)
                    existing.resend_count += 1
                    existing.last_sent_at = now
                    warn = "Код отправлен повторно."
            return True, warn

    code = generate_otp(6)
    session_id = uuid.uuid4().hex[:8]
    expires = now + timedelta(seconds=settings.otp_ttl_seconds)

    otp = Otp(
        user_id=user.id,
        code=code,
        session_id=session_id,
        resend_count=0,
        last_sent_at=now,
        created_at=now,
        expires_at=expires,
    )
    session.add(otp)
    await send_otp_email(settings, user.email, code)
    return True, warn


async def _notify_admin_on_block(
    session: AsyncSession,
    settings: Settings,
    user: User,
    reason: str,
    typ: str,
    bot,
    sender_name: str,
) -> None:
    """
    Создаёт запись в admin_log и отправляет уведомление в admin_chat (с кнопками блок/разблок).
    """
    if not settings.admin_chat_id:
        return
    attempts = await _last_attempts(session, user.id, typ)
    payload = {
        "user_id": user.id,
        "reason": reason,
        "type": typ,
        "attempts": [a.value for a in attempts],
    }
    session.add(
        AdminLog(
            admin_telegram_id=0,
            action="auth_block_request",
            payload=payload,
        )
    )
    # Сохраняем запись в БД, чтобы в admin_log было видно заявку
    await session.commit()
    # Отправляем сообщение в админ-чат с последними попытками и кнопками для принятия решения
    try:
        text = (
            f"❗️Неудачный вход\n"
            f"👤: {sender_name}\n"
            f"🔗: {'@' + user.username if user.username else 'нет username'}\n"
            f"🆔: {user.telegram_id}\n\n"
            f"Причина: {reason}\n"
            f"Последние {typ} попытки: {', '.join([a.value for a in attempts]) if attempts else 'нет данных'}"
        )
        await bot.send_message(
            chat_id=settings.admin_chat_id,
            text=text,
            reply_markup=kb_admin_decision(user.id),
        )
    except Exception:
        # Не фейлим основную операцию из-за ошибки отправки нотификации
        pass


# ------------------------- email / code ------------------------- #


@router.message(F.text & ~F.text.startswith("/"))
async def on_email_or_code(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """
    Текст обрабатываем ТОЛЬКО на стадиях регистрации: verifying_email*, verifying_code*.
    На шаги анкеты не претендуем — их ловит profile.py.
    """
    async with session_factory() as session:
        user = await _user(session, message.from_user.id)
        # Обрабатываем только свои стадии — если не наша стадия, отменяем обработчик
        if user.stage not in {
            "new",
            "verifying_email",
            "verifying_email_error",
            "verifying_code",
            "verifying_code_error",
        }:
            await session.commit()
            raise SkipHandler()

        # Снимем старые кнопки, если были
        await _clear_last_kb(state, message.chat.id, message.bot)

        user.last_activity = now_utc()
        text = (message.text or "").strip()

        if user.status == "blocked":
            await session.commit()
            await message.answer(
                "Доступ временно заблокирован. Свяжитесь с администратором."
            )
            return

        # E-MAIL
        if user.stage in {"new", "verifying_email", "verifying_email_error"}:
            email = text
            await _log_attempt(session, user.id, "email", email)

            exists = (
                await session.execute(
                    select(User).where(
                        User.email == email, User.telegram_id != user.telegram_id
                    )
                )
            ).scalar_one_or_none()
            if exists:
                await session.commit()
                await message.answer(
                    "Этот email уже привязан к другому аккаунту. Если это ошибка — обратитесь к администратору."
                )
                return

            ok, err = validate_email(
                email, settings.email_regex, settings.allowed_domains
            )
            if not ok:
                user.email_attempts += 1
                user.stage = "verifying_email"
                if user.email_attempts > settings.email_max_attempts:
                    user.status = "blocked"
                    user.stage = "verifying_email_error"
                    await _notify_admin_on_block(
                        session,
                        settings,
                        user,
                        "Слишком много неверных адресов",
                        "email",
                        message.bot,
                        message.from_user.full_name,
                    )
                    await session.commit()
                    await message.answer(
                        "Слишком много неверных адресов. Доступ заблокирован, администратор уведомлён, ожидайте решения."
                    )
                    return
                await session.commit()
                await message.answer(
                    f"⚠️ {err}\nПопробуйте ещё раз (корпоративный e-mail).\nПопыток осталось: {settings.email_max_attempts - user.email_attempts + 1}"
                )
                return

            user.email = email
            user.email_attempts = 0
            user.stage = "verifying_code"
            ok, warn = await _send_or_resend_otp(session, settings, user)
            await session.commit()
            msg = (
                "Отправили 6-значный код на вашу почту. Введите его в течение 2 минут."
            )
            if warn:
                msg += f"\n⚠️ {warn}"
            sent = await message.answer(msg, reply_markup=kb_auth_code_wait())
            await state.update_data(last_kb_mid=sent.message_id)
            return

        # OTP
        if user.stage in {"verifying_code", "verifying_code_error"}:
            if not text.isdigit() or not (4 <= len(text) <= 8):
                await message.answer("Ожидаю код из письма (4–8 цифр).")
                await session.commit()
                return

            code = text
            await _log_attempt(session, user.id, "otp", code)

            now = now_utc()
            otp_row = (
                (
                    await session.execute(
                        select(Otp)
                        .where(Otp.user_id == user.id)
                        .order_by(desc(Otp.created_at))
                    )
                )
                .scalars()
                .first()
            )

            if not otp_row:
                await session.commit()
                sent = await message.answer(
                    f"Код не найден. Отправить новый код на {user.email}?",
                    reply_markup=kb_auth_code_wait(),
                )
                await state.update_data(last_kb_mid=sent.message_id)
                return

            exp = ensure_aware_utc(otp_row.expires_at)
            used_at = ensure_aware_utc(otp_row.used_at)

            if not exp or exp <= now:
                await session.commit()
                sent = await message.answer(
                    f"Код истёк. Отправить новый код на {user.email}?",
                    reply_markup=kb_auth_code_wait(),
                )
                await state.update_data(last_kb_mid=sent.message_id)
                return

            if used_at:
                await session.commit()
                sent = await message.answer(
                    "Код уже был использован. Запросите новый.",
                    reply_markup=kb_auth_code_wait(),
                )
                await state.update_data(last_kb_mid=sent.message_id)
                return

            if code != otp_row.code:
                user.otp_attempts += 1
                user.stage = "verifying_code"
                if user.otp_attempts > settings.otp_max_attempts:
                    user.status = "blocked"
                    user.stage = "verifying_code_error"
                    await _notify_admin_on_block(
                        session,
                        settings,
                        user,
                        "Слишком много неверных OTP-кодов",
                        "otp",
                        message.bot,
                        message.from_user.full_name,
                    )
                    await session.commit()
                    await message.answer(
                        "Слишком много неверных попыток. Доступ заблокирован, администратор уведомлён, ожидайте решения."
                    )
                    return
                await session.commit()
                sent = await message.answer(
                    f"Неверный код. Попробуйте ещё раз или запросите новый.\nПопыток осталось: {settings.otp_max_attempts - user.otp_attempts + 1}",
                    reply_markup=kb_auth_code_wait(),
                )
                await state.update_data(last_kb_mid=sent.message_id)
                return

            # УСПЕХ: показать «Анкета 🪪»
            otp_row.used_at = now
            user.status = "active"
            user.stage = "authorized"
            user.email_attempts = 0
            user.otp_attempts = 0
            await session.commit()
            sent = await message.answer(
                "Успешная авторизация! ✅", reply_markup=kb_start_authorized()
            )
            await state.update_data(last_kb_mid=sent.message_id)
            return

        await session.commit()
        return


# ------------------------ callbacks: resend/change -------------- #


@router.callback_query(F.data == "otp:resend")
async def cb_otp_resend(
    cq: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    # гасим текущие кнопки в сообщении с которым работаем
    try:
        await cq.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    async with session_factory() as session:
        user = await _user(session, cq.from_user.id)
        user.last_activity = now_utc()

        if user.status == "blocked":
            await session.commit()
            await cq.message.answer(
                "Доступ временно заблокирован. Свяжитесь с администратором."
            )
            await cq.answer()
            return

        if user.stage not in {"verifying_code", "verifying_code_error"}:
            await session.commit()
            await cq.answer("Не требуется переотправка.")
            return

        ok, warn = await _send_or_resend_otp(session, settings, user)
        await session.commit()
        await cq.message.answer(
            ("Код отправлен повторно." if ok else "Не удалось отправить код.")
            + (f"\n⚠️ {warn}" if warn else "")
        )
        await state.update_data(
            last_kb_mid=None
        )  # текущего клавиатурного сообщения уже нет
        await cq.answer()


@router.callback_query(F.data == "otp:change_email")
async def cb_change_email(
    cq: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    try:
        await cq.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    async with session_factory() as session:
        user = await _user(session, cq.from_user.id)
        user.last_activity = now_utc()

        if user.status == "blocked":
            await session.commit()
            await cq.message.answer(
                "Доступ временно заблокирован. Свяжитесь с администратором."
            )
            await cq.answer()
            return

        user.stage = "verifying_email"
        await session.commit()
        await cq.message.answer("Отправьте новый корпоративный e-mail:")
        await state.update_data(last_kb_mid=None)
        await cq.answer()
