# app/utils/email_sender.py
"""
Отправка OTP-писем через SMTP (TLS), по параметрам из конфигурации.
Не логируем тело/код письма, только статус доставки.
"""

from __future__ import annotations

from email.message import EmailMessage

import aiosmtplib

from ..config import Settings


async def send_otp_email(settings: Settings, to_email: str, otp_code: str) -> None:
    """
    Отправляет проверочный код на e-mail по TLS 1.2+.
    Ошибки отдаём наверх — пусть ловятся на уровне хендлеров.
    """
    import ssl

    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to_email
    msg["Subject"] = "Код подтверждения для Random Coffee"
    msg.set_content(
        f"Ваш код подтверждения: {otp_code}\n"
        f"Срок действия: {settings.otp_ttl_seconds} секунд.\n"
        "Если вы не запрашивали код — просто игнорируйте это письмо."
    )

    # Создаём TLS-контекст с принудительным TLS 1.2+
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        start_tls=True,
        tls_context=ctx,  # Используем созданный контекст
        username=settings.smtp_user,
        password=settings.smtp_password,
        timeout=20,
    )
