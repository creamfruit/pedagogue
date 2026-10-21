from __future__ import annotations

import io
import random
import unicodedata

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1200
HEIGHT = 630

TOP = (16, 32, 57)
MIDDLE = (10, 17, 32)
BOTTOM = (4, 8, 15)
PANEL = (16, 26, 43)
LINE = (47, 68, 104)
TEXT = (228, 238, 238)
DIM = (159, 179, 184)
ACCENT = (206, 233, 226)
GOOD = (127, 209, 176)
WARN = (232, 194, 106)
HOT = (229, 143, 143)


def band_colour(score: float) -> tuple[int, int, int]:
    if score >= 60:
        return HOT
    if score >= 30:
        return WARN
    return GOOD


def plain(text: str) -> str:
    swapped = (text or "").replace("·", "-").replace("–", "-").replace("—", "-").replace("’", "'").replace("♯", "-sharp").replace("♭", "-flat")
    return unicodedata.normalize("NFKD", swapped).encode("ascii", "ignore").decode("ascii")


def font(size: int):
    return ImageFont.load_default(size=size)


def backdrop(seed: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), MIDDLE)
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        mix = y / HEIGHT
        if mix < 0.45:
            ratio = mix / 0.45
            colour = tuple(round(TOP[i] + (MIDDLE[i] - TOP[i]) * ratio) for i in range(3))
        else:
            ratio = (mix - 0.45) / 0.55
            colour = tuple(round(MIDDLE[i] + (BOTTOM[i] - MIDDLE[i]) * ratio) for i in range(3))
        draw.line([(0, y), (WIDTH, y)], fill=colour)
    generator = random.Random(seed)
    for _ in range(70):
        x, y = generator.random() * WIDTH, generator.random() * HEIGHT
        radius = 0.6 + generator.random() * 1.4
        shade = round(60 + generator.random() * 120)
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(shade, shade + 20, shade + 18))
    return image


def wrap(draw: ImageDraw.ImageDraw, text: str, face, width: int, lines: int) -> list[str]:
    words = text.split()
    out: list[str] = []
    line = ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=face) <= width or not line:
            line = trial
        else:
            out.append(line)
            line = word
    if line:
        out.append(line)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1].rstrip(" .,;:") + "…"
    return out


def piece_card(*, title: str, composer: str, score: float, band: str, hardest: str, techniques: list[str], footer: str = "pedagogue", seed: int = 1) -> bytes:
    title, composer, band, hardest, footer = plain(title), plain(composer), plain(band), plain(hardest), plain(footer)
    techniques = [plain(name) for name in techniques]
    image = backdrop(seed)
    draw = ImageDraw.Draw(image)
    draw.text((60, 44), "PEDAGOGUE", font=font(28), fill=ACCENT)
    draw.text((WIDTH - 60, 50), "HOW HARD IS IT?", font=font(20), fill=DIM, anchor="ra")
    draw.line([(60, 92), (WIDTH - 60, 92)], fill=LINE, width=2)

    title_face = font(54)
    y = 120
    for line in wrap(draw, title, title_face, 700, 3):
        draw.text((60, y), line, font=title_face, fill=TEXT)
        y += 66
    if composer:
        draw.text((60, y + 6), composer, font=font(32), fill=DIM)

    colour = band_colour(score)
    left, top, right, bottom = 790, 130, WIDTH - 60, 470
    draw.rounded_rectangle([left, top, right, bottom], radius=20, fill=PANEL, outline=LINE, width=2)
    draw.text((left + 36, top + 28), f"{score:g}", font=font(120), fill=colour)
    draw.text((left + 36, top + 168), "out of 100", font=font(28), fill=DIM)
    if band:
        draw.text((right - 36, top + 172), band, font=font(30), fill=colour, anchor="ra")
    bar_left, bar_right, bar_top = left + 36, right - 36, bottom - 64
    draw.rounded_rectangle([bar_left, bar_top, bar_right, bar_top + 20], radius=10, fill=BOTTOM)
    fill_width = max(20, round((bar_right - bar_left) * min(max(score, 0), 100) / 100))
    for x in range(fill_width):
        ratio = x / max(1, bar_right - bar_left)
        stops = (GOOD, WARN, HOT)
        position = ratio * 2
        index = min(1, int(position))
        mix = position - index
        colour_at = tuple(round(stops[index][i] + (stops[index + 1][i] - stops[index][i]) * mix) for i in range(3))
        draw.line([(bar_left + x, bar_top + 4), (bar_left + x, bar_top + 16)], fill=colour_at)

    base = 400
    if hardest:
        draw.text((60, base), "HARDEST SECTION", font=font(18), fill=DIM)
        draw.text((60, base + 26), wrap(draw, hardest, font(30), 700, 1)[0], font=font(30), fill=TEXT)
    x = 60
    for name in techniques[:3]:
        face = font(24)
        width = round(draw.textlength(name, font=face)) + 36
        if x + width > 730:
            break
        draw.rounded_rectangle([x, base + 90, x + width, base + 132], radius=21, outline=LINE, width=2)
        draw.text((x + 18, base + 97), name, font=face, fill=TEXT)
        x += width + 12
    draw.text((WIDTH // 2, HEIGHT - 34), footer, font=font(22), fill=DIM, anchor="mm")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
