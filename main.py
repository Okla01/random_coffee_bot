# main.py
"""
Точка входа. Запускает aiogram-поллинг.
"""

import asyncio

from app.bot import run_bot

if __name__ == "__main__":
    asyncio.run(run_bot())
