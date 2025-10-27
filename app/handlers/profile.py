# app/handlers/profile.py
"""
Анкета: name → photo → bio → age → interests → review → filled.
Гасим кнопки после действия пользователя. Стадии анкеты имеют приоритет над регистрацией.
"""

from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.types import InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.dispatcher.event.bases import SkipHandler

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..config import Settings
from ..keyboards import (
    kb_profile_filled,
    kb_profile_photo,
    kb_prefilled_data,
    kb_profile_review,
)
from ..models import User
from ..utils.security import contains_banned_words, normalize_interests

router = Router()


# --------------------------- helpers ---------------------------- #


async def _user(session: AsyncSession, tg_id: int) -> User:
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


def _photos_count(user: User) -> int:
    return len((user.photos_json or {}).get("photos", []))


def _append_photo(user: User, file_id: str) -> None:
    photos = (user.photos_json or {}).get("photos", [])
    if len(photos) >= 3:
        return
    photos.append({"file_id": file_id, "ts": datetime.now(timezone.utc).isoformat()})
    user.photos_json = {"photos": photos}


def _preview_text(user: User) -> str:
    lines = ["📇 Предпросмотр анкеты:"]
    if user.name:
        lines.append(f"• Имя: {user.name}")
    if user.age:
        lines.append(f"• Возраст: {user.age}")
    if user.bio:
        lines.append(f"• О себе: {user.bio}")
    interests = (user.interests_json or {}).get("interests", [])
    if interests:
        lines.append("• Интересы: " + ", ".join(interests))
    if _photos_count(user):
        lines.append(f"• Фото: {_photos_count(user)} шт.")
    return "\n".join(lines)


async def _send_profile_preview_with_photos(
    bot, chat_id: int, user: User, state: FSMContext, reply_markup
) -> None:
    """Send profile preview with user photos.

    Behavior:
    - If user has photos: first send them as media_group (album), then send text preview with buttons
    - If no photos: just send text preview with buttons
    """
    preview = _preview_text(user)
    photos = (user.photos_json or {}).get("photos", [])
    file_ids = [p.get("file_id") for p in photos if p.get("file_id")]

    # no photos -> simple text message
    if not file_ids:
        sent = await bot.send_message(chat_id, preview, reply_markup=reply_markup)
        await state.update_data(last_kb_mid=sent.message_id)
        return

    # has photos -> first send them as media_group (album), then send text preview with buttons
    media = []
    for fid in file_ids[:10]:
        media.append(InputMediaPhoto(media=fid))

    try:
        # send photos as media group (album)
        await bot.send_media_group(chat_id=chat_id, media=media)
    except Exception:
        # ignore photo sending errors, still try to send preview text
        pass

    # then send preview text with buttons as a separate message
    sent = await bot.send_message(chat_id, preview, reply_markup=reply_markup)
    await state.update_data(last_kb_mid=sent.message_id)
    return


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


# --------------------------- entry point ------------------------ #


@router.callback_query(F.data == "prof:start")
async def cb_prof_start(
    cq: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    # снимаем кнопки у нажатого сообщения
    try:
        await cq.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    async with session_factory() as session:
        user = await _user(session, cq.from_user.id)
        user.last_activity = datetime.now(timezone.utc)

        if user.status == "blocked":
            await session.commit()
            await cq.message.answer(
                "Доступ временно заблокирован. Свяжитесь с администратором."
            )
            await cq.answer()
            return

        # If user is already in profile flow, resume their current stage instead of forcing name step.
        profile_steps = {
            "profile_name",
            "profile_photo",
            "profile_bio",
            "profile_age",
            "profile_interests",
            "profile_review",
            "profile_filled",
        }

        if user.stage not in profile_steps:
            # start from name for new users
            user.stage = "profile_name"

            # Предзаполнение имени из import_payload
            prefilled = None
            if user.origin == "import" and user.import_payload:
                prefilled = user.import_payload.get("profile_name")
                if prefilled and 2 <= len(prefilled) <= 100:
                    banned, _ = contains_banned_words(prefilled, settings.banned_words)
                    if not banned:
                        await session.commit()
                        sent = await cq.message.answer(
                            f"У нас есть ваше имя из импорта: {prefilled}\nОставить или ввести новое?",
                            reply_markup=kb_prefilled_data(),
                        )
                        await state.update_data(last_kb_mid=sent.message_id)
                        await cq.answer()
                        return

            await session.commit()
            await cq.message.answer("Давайте заполним акнету! Как вас зовут?")
            await state.update_data(last_kb_mid=None)
            await cq.answer()
            return

        # If we're here, user.stage is in profile_steps — resume where they left off.
        await session.commit()

        if user.stage == "profile_name":
            await cq.message.answer("Давайте заполним акнету! Как вас зовут?")
            await state.update_data(last_kb_mid=None)
        elif user.stage == "profile_photo":
            sent = await cq.message.answer(
                "Отправьте до 3 фото (можно альбомом) или воспользуйтесь кнопкой:",
                reply_markup=kb_profile_photo(),
            )
            await state.update_data(last_kb_mid=sent.message_id)
        elif user.stage == "profile_bio":
            await cq.message.answer("Расскажите о себе (до 500 символов):")
            await state.update_data(last_kb_mid=None)
        elif user.stage == "profile_age":
            await cq.message.answer("Введите ваш возраст (18–50):")
            await state.update_data(last_kb_mid=None)
        elif user.stage == "profile_interests":
            await cq.message.answer(
                "Перечислите интересы через запятую (например: Python, музыка, дизайн)."
            )
            await state.update_data(last_kb_mid=None)
        elif user.stage == "profile_review":
            # send preview with attached photos (if any)
            await _send_profile_preview_with_photos(
                cq.message.bot, cq.message.chat.id, user, state, kb_profile_review()
            )
        elif user.stage == "profile_filled":
            sent = await cq.message.answer(
                _preview_text(user), reply_markup=kb_profile_filled()
            )
            await state.update_data(last_kb_mid=sent.message_id)

        await cq.answer()


@router.callback_query(F.data == "prof:prefilled:keep")
async def cb_prefilled_keep(
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
        user.stage = "profile_photo"
        if user.import_payload and user.import_payload.get("profile_name"):
            user.name = user.import_payload["profile_name"]
        await session.commit()
        sent = await cq.message.answer(
            "Отправьте до 3 фото (можно альбомом) или воспользуйтесь кнопкой:",
            reply_markup=kb_profile_photo(),
        )
        await state.update_data(last_kb_mid=sent.message_id)
        await cq.answer()


@router.callback_query(F.data == "prof:prefilled:new")
async def cb_prefilled_new(
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
        user.stage = "profile_name"
        await session.commit()
        await cq.message.answer("Давайте заполним анкету! Как вас зовут?")
        await state.update_data(last_kb_mid=None)
        await cq.answer()


# --------------------------- text steps ------------------------- #


@router.message(F.text & ~F.text.startswith("/"))
async def on_profile_text(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """
    Текстовый обработчик только для стадий анкеты.
    """
    async with session_factory() as session:
        user = await _user(session, message.from_user.id)

        # обрабатываем только свои стадии — если не наша стадия, отменяем обработчик
        if user.stage not in {
            "profile_name",
            "profile_bio",
            "profile_age",
            "profile_interests",
        }:
            await session.commit()
            raise SkipHandler()

        # гасим предыдущие кнопки
        await _clear_last_kb(state, message.chat.id, message.bot)

        user.last_activity = datetime.now(timezone.utc)
        text = (message.text or "").strip()

        if user.status == "blocked":
            await session.commit()
            await message.answer(
                "Доступ временно заблокирован. Свяжитесь с администратором."
            )
            return

        # NAME
        if user.stage == "profile_name":
            if not (2 <= len(text) <= 100):
                await message.answer(
                    "⚠️ Имя должно быть от 2 до 100 символов. Попробуйте ещё раз."
                )
                await session.commit()
                return
            bad, word = contains_banned_words(text, settings.banned_words)
            if bad:
                await message.answer(
                    f"⚠️ Имя содержит запрещённое слово «{word}». Введите другое."
                )
                await session.commit()
                return
            user.name = text
            user.stage = "profile_photo"
            await session.commit()
            sent = await message.answer(
                "Отправьте до 3 фото (можно альбомом) или нажмите:",
                reply_markup=kb_profile_photo(),
            )
            await state.update_data(last_kb_mid=sent.message_id)
            return

        # BIO
        if user.stage == "profile_bio":
            if len(text) > 500:
                await message.answer("⚠️ Описание должно быть не длиннее 500 символов.")
                await session.commit()
                return
            bad, word = contains_banned_words(text, settings.banned_words)
            if bad:
                await message.answer(
                    f"⚠️ Текст содержит запрещённое слово «{word}». Исправьте, пожалуйста."
                )
                await session.commit()
                return
            user.bio = text
            user.stage = "profile_age"
            await session.commit()
            await message.answer("Введите ваш возраст (18–50):")
            await state.update_data(last_kb_mid=None)
            return

        # AGE
        if user.stage == "profile_age":
            if not text.isdigit():
                await message.answer("⚠️ Возраст должен быть числом от 18 до 50.")
                await session.commit()
                return
            age = int(text)
            if not (18 <= age <= 50):
                await message.answer("⚠️ Возраст должен быть числом от 18 до 50.")
                await session.commit()
                return
            user.age = age
            user.stage = "profile_interests"
            await session.commit()
            await message.answer(
                "Перечислите интересы через запятую (например: Python, музыка, дизайн)."
            )
            await state.update_data(last_kb_mid=None)
            return

        # INTERESTS
        if user.stage == "profile_interests":
            interests, err = normalize_interests(text, settings.banned_words)
            if err:
                await message.answer("⚠️ " + err)
                await session.commit()
                return
            user.interests_json = {"interests": interests or []}
            user.stage = "profile_review"
            await session.commit()
            # send preview with attached photos (if any)
            await _send_profile_preview_with_photos(
                message.bot, message.chat.id, user, state, kb_profile_review()
            )
            return


# --------------------------- photo ------------------------------ #


@router.callback_query(F.data == "prof:photo:from_profile")
async def cb_photo_from_profile(
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
        user.last_activity = datetime.now(timezone.utc)

        if user.stage != "profile_photo":
            await session.commit()
            await cq.answer("Не на шаге фото.")
            return

        photos = await cq.message.bot.get_user_profile_photos(user.telegram_id, limit=3)
        count = 0
        for p in photos.photos:
            if not p:
                continue
            file_id = p[-1].file_id
            _append_photo(user, file_id)
            count += 1
            if count >= 3:
                break

        user.stage = "profile_bio"
        await session.commit()
        await cq.message.answer(
            "Фото добавлены. Теперь расскажите о себе (до 500 символов):"
        )
        await state.update_data(last_kb_mid=None)
        await cq.answer()


@router.callback_query(F.data == "prof:photo:skip")
async def cb_photo_skip(
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
        user.last_activity = datetime.now(timezone.utc)
        if user.stage != "profile_photo":
            await session.commit()
            await cq.answer()
            return
        user.stage = "profile_bio"
        await session.commit()
        await cq.message.answer(
            "Хорошо, можно без фото. Расскажите о себе (до 500 символов):"
        )
        await state.update_data(last_kb_mid=None)
        await cq.answer()


@router.message(F.photo)
async def on_photo(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Принимает 1–3 фото; можно присылать по одному или альбомом."""
    async with session_factory() as session:
        user = await _user(session, message.from_user.id)
        user.last_activity = datetime.now(timezone.utc)

        if user.status == "blocked":
            await session.commit()
            return
        if user.stage != "profile_photo":
            await session.commit()
            return

        # гасим предыдущие кнопки, если были
        await _clear_last_kb(state, message.chat.id, message.bot)

        file_id = message.photo[-1].file_id
        _append_photo(user, file_id)

        if _photos_count(user) >= 3:
            user.stage = "profile_bio"
            await session.commit()
            await message.answer(
                "Принял 3 фото. Теперь расскажите о себе (до 500 символов):"
            )
            await state.update_data(last_kb_mid=None)
            return

        await session.commit()
        await message.answer(
            f"Фото сохранено ({_photos_count(user)}/3). Можно отправить ещё или нажать «Пропустить ▶️»."
        )
        await state.update_data(last_kb_mid=None)  # без клавиатуры
        return


# --------------------------- review / save ---------------------- #


@router.callback_query(F.data == "prof:save")
async def cb_prof_save(
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
        user.stage = "profile_filled"
        await session.commit()
        sent = await cq.message.answer(
            "Анкета сохранена! 🎉", reply_markup=kb_profile_filled()
        )
        await state.update_data(last_kb_mid=sent.message_id)
        await cq.answer()


@router.callback_query(F.data == "prof:edit:review")
async def cb_prof_edit_review(
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
        user.stage = "profile_review"
        await session.commit()
        # send preview with attached photos (if any)
        await _send_profile_preview_with_photos(
            cq.message.bot, cq.message.chat.id, user, state, kb_profile_review()
        )
        await cq.answer()


@router.callback_query(F.data.startswith("prof:edit:"))
async def cb_prof_edit_field(
    cq: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    try:
        await cq.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    field = cq.data.split(":", 2)[2]
    async with session_factory() as session:
        user = await _user(session, cq.from_user.id)
        if field == "name":
            user.stage = "profile_name"
            await session.commit()
            await cq.message.answer("Давайте заполним анкету! Как вас зовут?")
            await state.update_data(last_kb_mid=None)
        elif field == "photo":
            user.stage = "profile_photo"
            await session.commit()
            sent = await cq.message.answer(
                "Отправьте до 3 фото (можно альбомом) или нажмите:",
                reply_markup=kb_profile_photo(),
            )
            await state.update_data(last_kb_mid=sent.message_id)
        elif field == "bio":
            user.stage = "profile_bio"
            await session.commit()
            await cq.message.answer("Расскажите о себе (до 500 символов):")
            await state.update_data(last_kb_mid=None)
        elif field == "age":
            user.stage = "profile_age"
            await session.commit()
            await cq.message.answer("Введите ваш возраст (18–50):")
            await state.update_data(last_kb_mid=None)
        elif field == "interests":
            user.stage = "profile_interests"
            await session.commit()
            await cq.message.answer("Перечислите интересы через запятую.")
            await state.update_data(last_kb_mid=None)
        await cq.answer()


@router.callback_query(F.data == "prof:join")
async def cb_prof_join(
    cq: CallbackQuery,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    try:
        await cq.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cq.message.answer(
        "Отлично! Вы будете участвовать в подборе, когда это станет доступно."
    )
    await state.update_data(last_kb_mid=None)
    await cq.answer()
