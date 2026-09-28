"""Живые настройки бота: название валюты, поддержка, чат и канал.

Значения лежат в базе и меняются админ-командами на лету, поэтому здесь не
обычные строки, а объекты, которые читают базу в момент подстановки в текст.
Благодаря этому f"{CURRENCY}" в любом файле всегда даёт актуальное название.
"""

from database import get_setting, set_setting
import config


class Live:
    """Строка, которая берёт текущее значение из базы при каждом обращении."""

    def __init__(self, key: str, default: str):
        self.key = key
        self.default = default

    def get(self) -> str:
        value = get_setting(self.key)
        return value if value else self.default

    def set(self, value: str):
        set_setting(self.key, value)

    def __str__(self) -> str:
        return self.get()

    def __repr__(self) -> str:
        return self.get()

    def __format__(self, spec) -> str:
        return format(self.get(), spec)

    def __eq__(self, other) -> bool:
        return self.get() == other

    def __hash__(self):
        return hash(self.get())

    def __add__(self, other) -> str:
        return self.get() + other

    def __radd__(self, other) -> str:
        return other + self.get()

    def __len__(self) -> int:
        return len(self.get())


# Название валюты — меняется командой /changevalyut
CURRENCY = Live("currency", config.CURRENCY)
