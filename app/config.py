# app/config.py
"""
Загрузка конфигурации из .env:
- ALLOWED_DOMAINS (список доменов),
- EMAIL_REGEX (регулярка для e-mail),
- ADMIN_IDS/ADMIN_CHAT_ID (поддерживается также ADMIN_CHAT_ID_NOTIFICATION),
- SMTP_* для отправки писем,
- лимиты OTP/попыток,
- общие настройки.

Файл читает .env через python-dotenv (load_dotenv).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Pattern, Set, List

from dotenv import load_dotenv  # <— добавлено


def _parse_list(raw: str) -> List[str]:
    """Пробует распарсить строку как JSON-список или как CSV/пробел-разделённый список."""
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("["):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except Exception:
            pass
    parts = re.split(r"[,\s]+", raw)
    return [x.strip() for x in parts if x.strip()]


@dataclass(frozen=True)
class Settings:
    """Иммутабельные настройки приложения."""

    # Bot / Admin
    bot_token: str
    admin_ids: Set[int]
    admin_chat_id: int | None

    # Email checks
    email_regex_str: str
    email_regex: Pattern[str]
    allowed_domains: Set[str]

    # SMTP
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str

    # DB
    db_url: str

    # Limits / Flow
    otp_ttl_seconds: int
    otp_cooldown_seconds: int
    resend_max_per_session: int
    email_max_attempts: int
    otp_max_attempts: int

    # Matching (на будущее)
    min_jaccard: float
    cooldown_weeks: int
    match_day: str
    match_utc_hour: int

    # Misc
    log_level: str
    tz_default: str
    banned_words: List[str]

    @classmethod
    def load(cls) -> "Settings":
        # ВАЖНО: загрузить .env из корня проекта
        load_dotenv()  # <— теперь переменные из .env будут в os.environ

        bot_token = os.getenv("BOT_TOKEN", "").strip()
        if not bot_token:
            raise RuntimeError("BOT_TOKEN не задан в .env")

        allowed_domains = set(_parse_list(os.getenv("ALLOWED_DOMAINS", "")))
        email_regex_str = os.getenv(
            "EMAIL_REGEX", r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
        )
        email_regex = re.compile(email_regex_str)

        admin_ids: Set[int] = set()
        for x in _parse_list(os.getenv("ADMIN_IDS", "")):
            try:
                admin_ids.add(int(x))
            except Exception:
                pass

        # Поддерживаем два имени: ADMIN_CHAT_ID и ADMIN_CHAT_ID_NOTIFICATION
        admin_chat_id_env = (
            os.getenv("ADMIN_CHAT_ID", "").strip()
            or os.getenv("ADMIN_CHAT_ID_NOTIFICATION", "").strip()
        )
        admin_chat_id = int(admin_chat_id_env) if admin_chat_id_env else None

        return cls(
            # bot/admin
            bot_token=bot_token,
            admin_ids=admin_ids,
            admin_chat_id=admin_chat_id,
            # email
            email_regex_str=email_regex_str,
            email_regex=email_regex,
            allowed_domains=allowed_domains,
            # smtp
            smtp_host=os.getenv("SMTP_HOST", ""),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            smtp_user=os.getenv("SMTP_USER", ""),
            smtp_password=os.getenv("SMTP_PASSWORD", ""),
            smtp_from=os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")),
            # db
            db_url=os.getenv("DB_URL", "sqlite+aiosqlite:///./data/app.db"),
            # limits
            otp_ttl_seconds=int(os.getenv("OTP_TTL_SECONDS", "120")),
            otp_cooldown_seconds=int(os.getenv("OTP_COOLDOWN_SECONDS", "120")),
            resend_max_per_session=int(os.getenv("RESEND_MAX_PER_SESSION", "3")),
            email_max_attempts=int(os.getenv("EMAIL_MAX_ATTEMPTS", "3")),
            otp_max_attempts=int(os.getenv("OTP_MAX_ATTEMPTS", "3")),
            # matching (на будущее)
            min_jaccard=float(os.getenv("MIN_JACCARD", "0.3")),
            cooldown_weeks=int(os.getenv("COOLDOWN_WEEKS", "1")),
            match_day=os.getenv("MATCH_DAY", "fri"),
            match_utc_hour=int(os.getenv("MATCH_UTC_HOUR", "12")),
            # misc
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            tz_default=os.getenv("TZ_DEFAULT", "UTC"),
            banned_words=_parse_list(os.getenv("BANNED_WORDS", "")),
        )
