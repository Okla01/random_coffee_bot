# app/utils/security.py
"""
Утилиты безопасности: генерация OTP, валидация e-mail, бан-слова, нормализация интересов.
"""

from __future__ import annotations

import secrets
import re
from typing import Iterable, List


def generate_otp(length: int = 6) -> str:
    """Генерирует криптографически стойкий OTP-код фиксированной длины."""
    return "".join(secrets.choice("0123456789") for _ in range(length))


def validate_email(
    email: str, regex: re.Pattern[str], allowed_domains: set[str]
) -> tuple[bool, str | None]:
    """
    Валидация e-mail:
    - соответствие regex;
    - домен входит в ALLOWED_DOMAINS (если задан).
    """
    if not regex.match(email):
        return False, "Некорректный формат e‑mail."
    if allowed_domains:
        try:
            domain = email.split("@", 1)[1].lower()
        except Exception:
            return False, "Некорректный формат e‑mail."
        if domain not in {d.lower() for d in allowed_domains}:
            return False, f"Домен @{domain} не разрешён."
    return True, None


def contains_banned_words(
    text: str, banned_words: Iterable[str]
) -> tuple[bool, str | None]:
    """Проверка наличия бан-слов (без учёта регистра), возвращает (есть_запрет, слово)."""
    low = text.lower()
    for w in banned_words:
        w = w.strip().lower()
        if w and w in low:
            return True, w
    return False, None


def normalize_interests(
    raw: str, banned_words: Iterable[str]
) -> tuple[List[str] | None, str | None]:
    """
    Нормализует строку интересов:
    - сплит по запятым/точкам с запятой/переводам строки;
    - тримит;
    - проверяет длину (каждый пункт 1..50 символов);
    - убирает дубли (без учёта регистра);
    - фильтрует бан-слова.
    """
    if not raw.strip():
        return [], None
    parts = re.split(r"[,\n;]+", raw)
    interests = [p.strip() for p in parts if p.strip()]
    if len(interests) > 30:
        return None, "Слишком много значений (макс. 30)."
    for interest in interests:
        if not (1 <= len(interest) <= 50):
            return None, f"Интерес «{interest}» недопустимой длины"
        has_banned, word = contains_banned_words(interest, banned_words)
        if has_banned:
            return None, f"Интерес «{interest}» содержит недопустимое слово"
    # удаляем дубликаты, сохраняя порядок
    seen = set()
    result: List[str] = []
    for it in interests:
        if it.lower() not in seen:
            seen.add(it.lower())
            result.append(it)
    # итоговая длина строк
    if sum(len(x) for x in result) > 300:
        return None, "Суммарная длина интересов превышает 300 символов."
    return result, None
