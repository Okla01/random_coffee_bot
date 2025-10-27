# app/keyboards.py
"""
Клавиатуры (inline) для сценариев:
- авторизация (resend / change email),
- анкета (предпросмотр/сохранение/редактирование),
- админка (блок/разблок).
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def kb_auth_code_wait() -> InlineKeyboardMarkup:
    """Кнопки в стадии ввода кода OTP."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отправить заново 🔁", callback_data="otp:resend"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Изменить email ✏️", callback_data="otp:change_email"
                )
            ],
        ]
    )


def kb_start_authorized() -> InlineKeyboardMarkup:
    """Кнопка перехода к анкете после успешной авторизации."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Анкета 🪪", callback_data="prof:start")],
        ]
    )


def kb_profile_filled() -> InlineKeyboardMarkup:
    """Кнопки после сохранения анкеты."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Изменить анкету ✏️", callback_data="prof:edit:review"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Участвовать в подборе 🥰", callback_data="prof:join"
                )
            ],
        ]
    )


def kb_profile_photo() -> InlineKeyboardMarkup:
    """Кнопки на шаге фотографий."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Взять из профиля 👤", callback_data="prof:photo:from_profile"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Пропустить ▶️", callback_data="prof:photo:skip"
                )
            ],
        ]
    )


def kb_prefilled_data() -> InlineKeyboardMarkup:
    """Кнопки для подтверждения предзаполненного значения из импорта."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Оставить ✅", callback_data="prof:prefilled:keep"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Ввести новые данные ✏️", callback_data="prof:prefilled:new"
                )
            ],
        ]
    )


def kb_profile_review() -> InlineKeyboardMarkup:
    """Кнопки предпросмотра анкеты."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сохранить ✅", callback_data="prof:save")],
            [
                InlineKeyboardButton(
                    text="Изменить имя", callback_data="prof:edit:name"
                ),
                InlineKeyboardButton(
                    text="Изменить фото", callback_data="prof:edit:photo"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Изменить описание", callback_data="prof:edit:bio"
                ),
                InlineKeyboardButton(
                    text="Изменить возраст", callback_data="prof:edit:age"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Изменить интересы", callback_data="prof:edit:interests"
                )
            ],
        ]
    )


def kb_admin_decision(user_id: int) -> InlineKeyboardMarkup:
    """Кнопки для заявки админам (блок/разблок)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Заблокировать 🔒", callback_data=f"admin:block:{user_id}"
                ),
                InlineKeyboardButton(
                    text="Разблокировать 🔓", callback_data=f"admin:unblock:{user_id}"
                ),
            ]
        ]
    )
