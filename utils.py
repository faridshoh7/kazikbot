def fmt(num: int) -> str:
    """1234567 -> '1 234 567'"""
    return f"{int(num):,}".replace(",", " ")


def mention(user_id: int, name: str) -> str:
    """Голубая кликабельная ссылка на игрока."""
    import html
    safe = html.escape(name or "Игрок")
    return f'<a href="tg://user?id={user_id}">{safe}</a>'


def coef_text(value: float) -> str:
    """1.28 -> 'x1,28'"""
    return "x" + f"{value:.2f}".replace(".", ",")


def profile_link(user_id: int, name: str, username: str) -> str:
    """Имя ссылкой на профиль: по @username, если он есть, иначе обычным тегом."""
    import html

    if username:
        safe = html.escape(name or username)
        return f'<a href="https://t.me/{username}">{safe}</a>'
    return mention(user_id, name)
