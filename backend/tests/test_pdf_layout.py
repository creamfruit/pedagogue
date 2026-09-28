import io

import numpy as np
from PIL import Image, ImageDraw

from app.services.pdf_layout import analyse_pages, crop_png, render_pages

SPACING = 10
BUSY_BAR = 6


def staff(draw, top, left, right):
    for line in range(5):
        y = top + line * SPACING
        draw.line([left, y, right, y], fill=0, width=1)


def page(systems=3, bars=4, busy=None, angle=0.0):
    image = Image.new("L", (1240, 1754), 255)
    draw = ImageDraw.Draw(image)
    left, right = 80, 1160
    bar_index = 0
    for system in range(systems):
        top = 150 + system * 300
        staff(draw, top, left, right)
        staff(draw, top + 90, left, right)
        draw.line([left, top, left, top + 130], fill=0, width=2)
        width = (right - left - 60) / bars
        for bar in range(bars):
            x0 = left + 60 + bar * width
            x1 = x0 + width
            draw.line([x1, top, x1, top + 130], fill=0, width=2)
            count = 22 if busy is not None and bar_index == busy else 4
            for note in range(count):
                x = x0 + 10 + note * (width - 20) / count
                for y in (top + 15 + (note % 3) * 5, top + 105 - (note % 2) * 5):
                    draw.ellipse([x, y, x + 9, y + 7], fill=0)
                    draw.line([x + 9, y + 3, x + 9, y - 25], fill=0, width=1)
            bar_index += 1
    if angle:
        image = image.rotate(angle, fillcolor=255)
    return np.asarray(image)


def test_counts_bars_and_finds_the_busiest_one():
    layout = analyse_pages([page(busy=BUSY_BAR), page()])
    assert layout.readable
    assert layout.bar_count == 24
    assert len(layout.systems) == 6
    assert layout.passages
    first = layout.passages[0]
    assert first.start <= BUSY_BAR + 1 <= first.end
    assert first.page == 1
    png = crop_png(layout, first)
    assert png.startswith(b"\x89PNG")


def test_survives_a_slightly_crooked_scan():
    layout = analyse_pages([page(busy=2, angle=0.7), page(angle=-0.5)])
    assert 20 <= layout.bar_count <= 28


def test_blank_pages_are_not_readable():
    blank = np.full((1754, 1240), 255, dtype=np.uint8)
    layout = analyse_pages([blank])
    assert not layout.readable
    assert layout.passages == []


def test_render_pages_reads_a_real_pdf():
    buffer = io.BytesIO()
    Image.fromarray(page()).convert("RGB").save(buffer, format="PDF", resolution=150)
    pages = render_pages(buffer.getvalue())
    assert len(pages) == 1
    assert pages[0].ndim == 2
