"""Резервные копии базы: при каждом запуске и раз в час.

Копия снимается средствами SQLite, поэтому её можно делать на живой базе —
файл не побьётся, даже если в этот момент идёт игра.
"""

import asyncio
import os
import sqlite3
import time

from database import DB_NAME, BASE_DIR, get_db

BACKUP_DIR = os.path.join(BASE_DIR, "backups")

# Сколько копий храним, остальные удаляются
KEEP = 20

# Как часто снимать копию, секунд
EVERY = 60 * 60


def make_backup(tag: str = "") -> str:
    os.makedirs(BACKUP_DIR, exist_ok=True)

    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    name = f"gram_{stamp}{('_' + tag) if tag else ''}.db"
    path = os.path.join(BACKUP_DIR, name)

    src = get_db()
    dst = sqlite3.connect(path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    cleanup()
    return path


def cleanup():
    """Оставляем только последние KEEP копий."""
    if not os.path.isdir(BACKUP_DIR):
        return

    files = sorted(
        (f for f in os.listdir(BACKUP_DIR) if f.endswith(".db")),
        key=lambda f: os.path.getmtime(os.path.join(BACKUP_DIR, f)),
        reverse=True,
    )

    for old in files[KEEP:]:
        try:
            os.remove(os.path.join(BACKUP_DIR, old))
        except OSError:
            pass


async def backup_task():
    """Фоновая задача: копия базы раз в час."""
    while True:
        await asyncio.sleep(EVERY)
        try:
            make_backup()
        except Exception as e:
            print(f"Ошибка бэкапа: {e}")
