# app/models.py
"""
Модели БД (SQLAlchemy, async), приведённые к требованиям ТЗ:

Таблицы:
- users: пользователь, его статус/стадия, анкета и счётчики попыток.
- otp: одноразовые коды с TTL, лимитами переотправок и временем последней отправки.
- auth_attempts: последние введённые значения (email/otp) для заявок админам.
- roles, user_roles: доступ к админ-панели по ролям.
- admin_log: журнал действий админ-панели.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс декларативных моделей."""


# ----------------------------- Users ----------------------------- #


class User(Base):
    """Пользователь и его состояние в сценариях авторизации/анкеты."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Текущий статус/стадия
    status: Mapped[str] = mapped_column(
        String(16), default="new", index=True
    )  # new/active/blocked/imported
    stage: Mapped[str] = mapped_column(String(32), default="new", index=True)

    # Авторизация через e-mail
    email: Mapped[Optional[str]] = mapped_column(
        String(255), unique=True, nullable=True
    )
    email_attempts: Mapped[int] = mapped_column(Integer, default=0)
    otp_attempts: Mapped[int] = mapped_column(Integer, default=0)

    # Анкета
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    photos_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # {"photos": [{"file_id":..., "ts":...}, ...]}
    bio: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    interests_json: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # {"interests": [...]}

    # Импорт
    origin: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True
    )  # 'import' | 'self'
    import_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Аудит
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    otps: Mapped[list["Otp"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    attempts: Mapped[list["AuthAttempt"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


# ------------------------------ OTP ------------------------------ #


class Otp(Base):
    """Одноразовые коды с TTL и лимитами переотправки (cooldown 120с, ≤3 resend/сессию)."""

    __tablename__ = "otp"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    code: Mapped[str] = mapped_column(String(12))
    session_id: Mapped[str] = mapped_column(
        String(32), index=True
    )  # логическая «сессия» для контроля resend
    resend_count: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="otps")

    __table_args__ = (
        UniqueConstraint("user_id", "session_id", name="uq_otp_user_session"),
    )


# ------------------------ Auth Attempts -------------------------- #


class AuthAttempt(Base):
    """Последние введённые значения для заявок админам (email/otp)."""

    __tablename__ = "auth_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    type: Mapped[str] = mapped_column(String(16))  # "email" | "otp"
    value: Mapped[str] = mapped_column(String(255))
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user: Mapped["User"] = relationship(back_populates="attempts")


# ------------------------------ Roles ---------------------------- #


class Role(Base):
    """Роль в системе (например, 'admin')."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, index=True)


class UserRole(Base):
    """Связь пользователь — роль."""

    __tablename__ = "user_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), index=True
    )

    user: Mapped["User"] = relationship(back_populates="roles")
    role: Mapped["Role"] = relationship()


# --------------------------- Admin log --------------------------- #


class AdminLog(Base):
    """Журнал действий админ-панели."""

    __tablename__ = "admin_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_telegram_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
