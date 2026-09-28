from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

RENDER_DPI = 150
MAX_PAGES = 40
DARK = 150


@dataclass
class Staff:
    top: int
    bottom: int
    spacing: float
    left: int
    right: int
    lines: list[int]


@dataclass
class Bar:
    page: int
    system: int
    x0: int
    x1: int
    y0: int
    y1: int
    ink: float = 0.0
    number: int = 0


@dataclass
class System:
    page: int
    staves: list[Staff]
    bars: list[Bar] = field(default_factory=list)

    @property
    def top(self) -> int:
        return self.staves[0].top

    @property
    def bottom(self) -> int:
        return self.staves[-1].bottom

    @property
    def spacing(self) -> float:
        return float(np.median([staff.spacing for staff in self.staves]))


@dataclass
class DensePassage:
    start: int
    end: int
    page: int
    relative: float
    boxes: list[tuple[int, int, int, int, int]]


@dataclass
class PdfLayout:
    pages: int
    bars: list[Bar]
    systems: list[System]
    passages: list[DensePassage]
    images: list[np.ndarray]
    readable: bool

    @property
    def bar_count(self) -> int:
        return len(self.bars)


def render_pages(data: bytes, dpi: int = RENDER_DPI, max_pages: int = MAX_PAGES) -> list[np.ndarray]:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(data)
    pages = []
    for index in range(min(len(document), max_pages)):
        image = document[index].render(scale=dpi / 72, grayscale=True).to_pil().convert("L")
        pages.append(np.asarray(image, dtype=np.uint8))
    document.close()
    return pages


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    runs = []
    start = None
    for index, value in enumerate(mask):
        if value and start is None:
            start = index
        elif not value and start is not None:
            runs.append((start, index - 1))
            start = None
    if start is not None:
        runs.append((start, len(mask) - 1))
    return runs


def _near(lines: list[float], target: float, tolerance: float) -> Optional[int]:
    best, best_gap = None, tolerance
    for index, value in enumerate(lines):
        gap = abs(value - target)
        if gap <= best_gap:
            best, best_gap = index, gap
    return best


def find_staves(dark: np.ndarray, image: Optional[np.ndarray] = None, threshold: Optional[int] = None) -> list[Staff]:
    height, width = dark.shape
    if image is not None and threshold is not None:
        kernel = 7
        padded = np.pad(image.astype(np.float32), ((0, 0), (kernel // 2, kernel // 2)), mode="edge")
        summed = np.cumsum(padded, axis=1)
        summed = np.concatenate([np.zeros((height, 1), dtype=np.float32), summed], axis=1)
        smooth = (summed[:, kernel:] - summed[:, :-kernel]) / kernel
        dark = dark | (smooth[:, :width] < min(threshold + 45, 235))
    margin = int(width * 0.04)
    up = np.zeros_like(dark)
    down = np.zeros_like(dark)
    up[3:] = dark[:-3]
    down[:-3] = dark[3:]
    thin = dark & ~(up & down)
    rows = thin[:, margin: width - margin].mean(axis=1)
    if rows.max() < 0.3:
        return []
    threshold = max(0.3, rows.max() * 0.45)
    lines = [(a + b) / 2 for a, b in _runs(rows > threshold) if b - a <= 5]
    staves: list[Staff] = []
    used: set[int] = set()
    index = 0
    while index < len(lines):
        if index in used:
            index += 1
            continue
        found = None
        for second in range(index + 1, min(index + 4, len(lines))):
            spacing = lines[second] - lines[index]
            if not 5 <= spacing <= 60:
                continue
            tolerance = max(2.0, spacing * 0.18)
            picks = [index, second]
            for step in (2, 3, 4):
                hit = _near(lines, lines[index] + step * spacing, tolerance)
                if hit is None or hit in used:
                    picks = None
                    break
                picks.append(hit)
            if picks:
                found = picks
                break
        if not found:
            index += 1
            continue
        group = [lines[i] for i in found]
        spacing = float(np.median(np.diff(group)))
        rows_idx = [int(round(y)) for y in group]
        covered = dark[rows_idx, :].sum(axis=0) >= 4
        spans = [run for run in _runs(covered) if run[1] - run[0] > width * 0.2]
        if spans:
            staves.append(Staff(rows_idx[0], rows_idx[-1], spacing, spans[0][0], spans[-1][1], rows_idx))
            used.update(found)
            index = max(found) + 1
        else:
            index += 1
    return staves


def group_systems(page: int, dark: np.ndarray, staves: list[Staff]) -> list[System]:
    systems: list[System] = []
    current: list[Staff] = []
    for staff in staves:
        if current:
            previous = current[-1]
            gap = staff.top - previous.bottom
            joined = False
            if 0 < gap < previous.spacing * 30 and len(current) < 3:
                start = max(min(previous.left, staff.left) - int(previous.spacing), 0)
                stop = min(start + int(previous.spacing * 3), dark.shape[1])
                region = dark[previous.top: staff.bottom + 1, start:stop]
                joined = bool(region.size and (region.mean(axis=0) >= 0.9).any())
            if not joined:
                systems.append(System(page, current))
                current = []
        current.append(staff)
    if current:
        systems.append(System(page, current))
    return systems


def _isolated(dark: np.ndarray, system: System, x0: int, x1: int) -> bool:
    spacing = system.spacing
    reach = max(2, int(spacing * 0.45))
    line_rows = {row for staff in system.staves for line in staff.lines for row in range(line - 1, line + 2)}
    rows = [row for staff in system.staves for row in range(staff.top, staff.bottom + 1) if row not in line_rows]
    if not rows:
        return True
    left = dark[rows, max(x0 - reach, 0): max(x0 - 1, 1)]
    right = dark[rows, x1 + 2: x1 + reach + 1]
    busy = 0.0
    for side in (left, right):
        if side.size:
            busy = max(busy, float(side.any(axis=1).mean()))
    return busy < 0.2


def find_barlines(dark: np.ndarray, system: System) -> list[int]:
    spacing = system.spacing
    left = min(staff.left for staff in system.staves)
    right = max(staff.right for staff in system.staves)
    per_staff = np.ones(right - left + 1, dtype=bool)
    for staff in system.staves:
        column = dark[staff.top: staff.bottom + 1, left: right + 1].mean(axis=0)
        per_staff &= column >= 0.9
    connected = per_staff.copy()
    for upper, lower in zip(system.staves, system.staves[1:]):
        gap = dark[upper.bottom: lower.top + 1, left: right + 1].mean(axis=0)
        connected &= gap >= 0.9

    def collect(mask: np.ndarray, strict: bool) -> list[float]:
        found = []
        for a, b in _runs(mask):
            if b - a + 1 <= max(3, spacing * 0.8) and (strict is False or _isolated(dark, system, left + a, left + b)):
                found.append((left + a + left + b) / 2)
        return found

    inner = lambda xs: [x for x in xs if x > left + spacing * 1.5]
    candidates = collect(connected, False) if len(system.staves) > 1 else []
    if len(system.staves) == 1:
        candidates = collect(per_staff, True)
    merged: list[float] = []
    for x in candidates:
        if merged and x - merged[-1] < spacing * 1.3:
            merged[-1] = x
        else:
            merged.append(x)
    barlines = [int(x) for x in inner(merged)]
    if not barlines or right - barlines[-1] > spacing * 2:
        barlines.append(right)
    return barlines


def measure_ink(dark: np.ndarray, system: System, x0: int, x1: int, y0: int, y1: int) -> float:
    region = dark[y0:y1, x0:x1].astype(np.float32)
    if region.size == 0:
        return 0.0
    for staff in system.staves:
        for line in staff.lines:
            for row in range(line - 1, line + 2):
                local = row - y0
                if 0 <= local < region.shape[0]:
                    region[local, :] = 0
    spacing = system.spacing
    return float(region.sum()) / max((x1 - x0) * spacing, 1.0)


def ink_threshold(image: np.ndarray) -> int:
    histogram = np.bincount(image.ravel(), minlength=256).astype(np.float64)
    total = histogram.sum()
    levels = np.arange(256)
    weight = np.cumsum(histogram)
    mean = np.cumsum(histogram * levels)
    overall = mean[-1]
    between = np.zeros(256)
    valid = (weight > 0) & (weight < total)
    between[valid] = (overall * weight[valid] / total - mean[valid]) ** 2 / (weight[valid] * (total - weight[valid]))
    return int(min(max(int(np.argmax(between)), 110), 215))


def deskew(image: np.ndarray) -> np.ndarray:
    from PIL import Image

    picture = Image.fromarray(image)
    small = picture.resize((max(image.shape[1] // 2, 1), max(image.shape[0] // 2, 1)))
    threshold = ink_threshold(image)

    def score(angle: float) -> float:
        rotated = np.asarray(small.rotate(angle, resample=Image.BILINEAR, fillcolor=255)).astype(np.float64)
        rows = (255.0 - rotated).mean(axis=1)
        return float(rows.var())

    flat = score(0.0)
    best_angle, best_score = 0.0, flat
    for angle in np.arange(-2.0, 2.01, 0.2):
        if abs(angle) < 1e-9:
            continue
        value = score(float(angle))
        if value > best_score:
            best_angle, best_score = float(angle), value
    if best_angle != 0.0:
        for angle in (best_angle - 0.1, best_angle + 0.1):
            value = score(angle)
            if value > best_score:
                best_angle, best_score = angle, value
    if best_score < flat * 1.02:
        return image
    return np.asarray(picture.rotate(best_angle, resample=Image.BILINEAR, fillcolor=255))


def analyse_pages(images: list[np.ndarray]) -> PdfLayout:
    bars: list[Bar] = []
    systems: list[System] = []
    images = [deskew(image) for image in images]
    for page_index, image in enumerate(images):
        threshold = ink_threshold(image)
        dark = image < threshold
        page_systems = group_systems(page_index, dark, find_staves(dark, image, threshold))
        for position, system in enumerate(page_systems):
            spacing = system.spacing
            above = page_systems[position - 1].bottom if position > 0 else 0
            below = page_systems[position + 1].top if position + 1 < len(page_systems) else image.shape[0]
            y0 = max(int((system.top + above) / 2), system.top - int(spacing * 5), 0)
            y1 = min(int((system.bottom + below) / 2), system.bottom + int(spacing * 5), image.shape[0])
            barlines = find_barlines(dark, system)
            start = min(staff.left for staff in system.staves)
            for number, x in enumerate(barlines):
                x0 = start if number == 0 else barlines[number - 1]
                ink_start = x0 + int(spacing * 6) if number == 0 else x0 + 2
                bar = Bar(page_index, len(systems), x0, x, y0, y1)
                if x - ink_start > spacing:
                    bar.ink = measure_ink(dark, system, ink_start, x - 1, y0, y1)
                system.bars.append(bar)
                bars.append(bar)
            systems.append(system)
    for index, bar in enumerate(bars, start=1):
        bar.number = index
    readable = len(bars) >= 4 and len(systems) >= 2
    passages = pick_dense(bars) if readable else []
    return PdfLayout(len(images), bars, systems, passages, images, readable)


def pick_dense(bars: list[Bar], limit: Optional[int] = None) -> list[DensePassage]:
    inks = np.array([bar.ink for bar in bars], dtype=np.float64)
    positive = inks[inks > 0]
    if positive.size < 4:
        return []
    baseline = float(np.median(positive))
    relative = inks / max(baseline, 1e-6)
    limit = limit or max(2, min(6, len(bars) // 30 + 2))
    width = 4 if len(bars) >= 24 else 2
    windows = []
    for start in range(0, len(bars) - width + 1):
        window = relative[start: start + width]
        windows.append((float(window.mean()), start))
    windows.sort(reverse=True)
    taken: list[tuple[int, int]] = []
    chosen: list[DensePassage] = []
    for score, start in windows:
        if score < 1.25 or len(chosen) >= limit:
            break
        end = start + width - 1
        if any(not (end < a - 1 or start > b + 1) for a, b in taken):
            continue
        while end + 1 < len(bars) and relative[end + 1] >= score * 0.9 and end - start < 7:
            end += 1
        while start > 0 and relative[start - 1] >= score * 0.9 and end - start < 7:
            start -= 1
        if any(not (end < a - 1 or start > b + 1) for a, b in taken):
            continue
        taken.append((start, end))
        span = bars[start: end + 1]
        boxes: dict[int, list[int]] = {}
        for bar in span:
            box = boxes.setdefault(bar.system, [bar.page, bar.x0, bar.y0, bar.x1, bar.y1])
            box[1] = min(box[1], bar.x0)
            box[3] = max(box[3], bar.x1)
        chosen.append(
            DensePassage(
                start=span[0].number,
                end=span[-1].number,
                page=span[0].page + 1,
                relative=round(float(relative[start: end + 1].mean()), 2),
                boxes=[tuple(box) for box in boxes.values()],
            )
        )
    return sorted(chosen, key=lambda passage: -passage.relative)


def crop_png(layout: PdfLayout, passage: DensePassage, max_width: int = 1400) -> bytes:
    from PIL import Image

    parts = []
    for page, x0, y0, x1, y1 in passage.boxes:
        image = layout.images[page]
        pad = 6
        parts.append(image[max(y0, 0): y1, max(x0 - pad, 0): min(x1 + pad, image.shape[1])])
    width = max(part.shape[1] for part in parts)
    height = sum(part.shape[0] for part in parts) + 8 * (len(parts) - 1)
    canvas = np.full((height, width), 255, dtype=np.uint8)
    offset = 0
    for part in parts:
        canvas[offset: offset + part.shape[0], : part.shape[1]] = part
        offset += part.shape[0] + 8
    picture = Image.fromarray(canvas)
    if picture.width > max_width:
        picture = picture.resize((max_width, int(picture.height * max_width / picture.width)))
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def analyse_pdf(data: bytes) -> PdfLayout:
    return analyse_pages(render_pages(data))
