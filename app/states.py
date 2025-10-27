# app/states.py
"""
Состояния FSM (для фильтрации хендлеров), соответствуют стадиям из ТЗ.
Фактическое восстановление сценария делается по users.stage.
"""

from aiogram.fsm.state import State, StatesGroup


class AuthStates(StatesGroup):
    """Состояния авторизации (email → code)."""

    verifying_email = State()
    verifying_email_error = State()
    verifying_code = State()
    verifying_code_error = State()
    authorized = State()


class ProfileStates(StatesGroup):
    """Состояния анкеты."""

    profile_name = State()
    profile_photo = State()
    profile_bio = State()
    profile_age = State()
    profile_interests = State()
    profile_review = State()
    profile_filled = State()
