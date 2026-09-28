"""Защита от второго запущенного бота.

Если запустить main.py дважды, оба процесса забирают обновления у Telegram и
каждый отвечает — игроки видят ответ два раза. Здесь мы занимаем локальный
порт: второй процесс его занять не сможет и честно скажет об этом.
"""

import socket

# Порт ничего не слушает по делу, он просто метка "бот уже работает"
LOCK_PORT = 47821

_lock = None


def acquire() -> bool:
    """True — мы единственный экземпляр. False — бот уже запущен."""
    global _lock

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", LOCK_PORT))
        sock.listen(1)
    except OSError:
        sock.close()
        return False

    _lock = sock
    return True


def release():
    global _lock
    if _lock:
        _lock.close()
        _lock = None
