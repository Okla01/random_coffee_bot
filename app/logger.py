# app/logger.py
"""
Единая настройка логирования без вывода чувствительных данных.
"""

from __future__ import annotations

import logging


def setup_logging(level: str = "INFO") -> None:
    """Настраивает консольный логгер."""
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(level.upper())
    handler = logging.StreamHandler()
    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(handler)
