"""Картинка-капча для бонуса: код из букв и цифр на светлом фоне.

Код — 6 символов: буквы вперемешку с цифрами, регистр случайный.
Цифр обычно нет или одна, две выпадают редко.
Похожие символы (0, O, 1, I, l) не используем — их путают при вводе.
"""

import random
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 🔤 АЛФАВИТ КОДА
# ==========================================
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz"
DIGITS = "23456789"

CODE_LENGTH = 6
# Сколько цифр в коде: чаще всего одна или ни одной
DIGIT_COUNTS = (0, 1, 2)
DIGIT_WEIGHTS = (40, 45, 15)

# ==========================================
# 🎨 ВИД КАРТИНКИ
# ==========================================
WIDTH = 640
HEIGHT = 250

BG_COLOR = (244, 245, 249)
TEXT_COLOR = (24, 33, 56)

FONT_SIZE = 105
# Шире этой доли картинки код не растягиваем
MAX_TEXT_WIDTH = 0.88

LINES = 22
DOTS = 60

# Рисуем в двойном размере и ужимаем — линии и буквы выходят без «лесенки»
SCALE = 2

FONT_PATHS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/Library/Fonts/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
)


def new_code() -> str:
    """Случайный код из букв и цифр."""
    digits = random.choices(DIGIT_COUNTS, weights=DIGIT_WEIGHTS)[0]

    symbols = [random.choice(DIGITS) for _ in range(digits)]
    symbols += [random.choice(LETTERS) for _ in range(CODE_LENGTH - digits)]

    # Цифры должны стоять где угодно, а не только в конце
    random.shuffle(symbols)
    return "".join(symbols)


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _noise_color() -> tuple:
    """Тонкие серо-голубые линии и точки — светлее текста, читать не мешают."""
    grey = random.randint(170, 205)
    return (grey, grey + random.randint(3, 12), grey + random.randint(8, 20))


def draw_code(code: str) -> BytesIO:
    """Картинка с кодом: текст по центру, поверх — линии и точки."""
    width, height = WIDTH * SCALE, HEIGHT * SCALE

    image = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(image)

    # Точки под текстом, чтобы не рябило на буквах
    for _ in range(DOTS):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        size = random.choice((1, 2, 3))
        draw.ellipse((x, y, x + size, y + size), fill=_noise_color())

    font = _load_font(FONT_SIZE * SCALE)

    # Длинные коды ужимаем, чтобы влезли в картинку
    left, top, right, bottom = draw.textbbox((0, 0), code, font=font)
    limit = width * MAX_TEXT_WIDTH
    if right - left > limit:
        font = _load_font(int(FONT_SIZE * SCALE * limit / (right - left)))
        left, top, right, bottom = draw.textbbox((0, 0), code, font=font)

    x = (width - (right - left)) / 2 - left
    y = (height - (bottom - top)) / 2 - top
    draw.text((x, y), code, font=font, fill=TEXT_COLOR)

    # Линии поверх текста — так их не срезать простым поиском по цвету
    for _ in range(LINES):
        start = (random.randint(-80, width + 80), random.randint(0, height))
        end = (random.randint(-80, width + 80), random.randint(0, height))
        draw.line((start, end), fill=_noise_color(), width=SCALE)

    image = image.resize((WIDTH, HEIGHT), Image.LANCZOS)

    photo = BytesIO()
    image.save(photo, format="PNG")
    photo.seek(0)
    return photo
