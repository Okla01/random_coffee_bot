# app/utils/dt.py
"""
Вспомогательные функции для работы со временем (UTC).
Используются, чтобы унифицировать сравнение дат из БД (naive) и кода (aware).
"""

from __future__ import annotations

from datetime import datetime, timezone


def now_utc() -> datetime:
    """
    Текущее время в UTC со встроенной таймзоной (aware).
    """
    return datetime.now(timezone.utc)


def ensure_aware_utc(dt: datetime | None) -> datetime | None:
    """
    Приводит datetime к aware-UTC:
    - если dt is None — вернуть None;
    - если naive (tzinfo is None) — просто присвоить tz UTC;
    - если aware — сконвертировать в UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Считаем, что «наивное» время — это UTC в нашей системе.
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
