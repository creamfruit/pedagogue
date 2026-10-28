import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from . import config

SVG_TIMEOUT_SECONDS = 150
LILYPOND_FLOOR = (2, 18)

FILTER_ENGRAVER = r"""
#(define (bar-filter-engraver from to)
  (lambda (context)
    (make-engraver
      ((start-translation-timestep engraver)
        (let ((bar (ly:context-property context 'currentBarNumber)))
          (ly:context-set-property! context 'skipTypesetting (not (and (>= bar from) (<= bar to)))))))))
\layout { \context { \Score \consists #(bar-filter-engraver %(start)d %(end)d)
  barNumberVisibility = #(lambda (barnum measure-pos) (> barnum 1))
  \override BarNumber.break-visibility = #all-visible } }
"""
PLAIN_PAPER = r"""
\paper { bookTitleMarkup = ##f scoreTitleMarkup = ##f oddHeaderMarkup = ##f evenHeaderMarkup = ##f oddFooterMarkup = ##f evenFooterMarkup = ##f }
"""
VERSION = re.compile(r'\\version\s+"(\d+)\.(\d+)[^"]*"')
FIRST_BLOCK = re.compile(r"\\(?:score|book|bookpart)\s*\{")


class RenderUnavailable(Exception):
    pass


def lilypond_binary() -> Optional[str]:
    candidate = config.LILYPOND_BIN
    if Path(candidate).exists():
        return str(candidate)
    return shutil.which(candidate)


def crop_source(text: str, start: int, end: int) -> Optional[str]:
    version = VERSION.search(text)
    first = FIRST_BLOCK.search(text)
    if version is None or first is None:
        return None
    with_filter = text[: version.end()] + "\n" + FILTER_ENGRAVER % {"start": start, "end": end} + text[version.end() :]
    block = FIRST_BLOCK.search(with_filter)
    return with_filter[: block.start()] + PLAIN_PAPER + with_filter[block.start() :]


def source_version(text: str) -> Optional[tuple]:
    found = VERSION.search(text)
    return (int(found.group(1)), int(found.group(2))) if found else None


def upgrade_source(path: Path, binary: str) -> bool:
    folder = Path(binary).parent
    script = folder / "convert-ly.py"
    runner = folder / "python.exe"
    command = [str(runner), str(script), "-e", str(path)] if script.exists() and runner.exists() else ["convert-ly", "-e", str(path)]
    try:
        subprocess.run(command, capture_output=True, timeout=SVG_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return True


def render_lilypond(source: Path, start: int, end: int, include_dir: Optional[Path] = None) -> Optional[str]:
    binary = lilypond_binary()
    if binary is None:
        raise RenderUnavailable("LilyPond was not found; set LILYPOND_BIN")
    text = Path(source).read_text(encoding="utf-8", errors="replace")
    with tempfile.TemporaryDirectory(prefix="crop-") as scratch:
        folder = Path(scratch)
        target = folder / "crop.ly"
        version = source_version(text)
        if version is not None and version < LILYPOND_FLOOR:
            target.write_text(text, encoding="utf-8")
            upgrade_source(target, binary)
            text = target.read_text(encoding="utf-8", errors="replace")
        cropped = crop_source(text, start, end)
        if cropped is None:
            return None
        target.write_text(cropped, encoding="utf-8")
        command = [binary, "--svg", "-dcrop", "-dno-point-and-click", "-I", str(include_dir or Path(source).parent), "-o", str(folder / "crop"), str(target)]
        try:
            done = subprocess.run(command, capture_output=True, timeout=SVG_TIMEOUT_SECONDS, check=False, cwd=folder)
        except subprocess.TimeoutExpired:
            return None
        result = folder / "crop.cropped.svg"
        if done.returncode != 0 or not result.exists():
            return None
        svg = result.read_text(encoding="utf-8", errors="replace")
        return svg if "<path" in svg or "<tspan" in svg else None


def render_musicxml(path: Path, numbers: list, start: int, end: int) -> Optional[str]:
    import verovio

    if start not in numbers or end not in numbers:
        return None
    toolkit = verovio.toolkit()
    toolkit.setOptions(
        {
            "pageWidth": 1900,
            "pageHeight": 6000,
            "scale": 45,
            "adjustPageHeight": True,
            "header": "none",
            "footer": "none",
            "mnumInterval": 1,
            "svgViewBox": True,
        }
    )
    if not toolkit.loadFile(str(path)):
        return None
    toolkit.select({"measureRange": f"{numbers.index(start) + 1}-{numbers.index(end) + 1}"})
    toolkit.redoLayout()
    svg = toolkit.renderToSVG(1)
    return svg if "<svg" in svg else None


def excerpt_from_notes(data, start: int, end: int):
    from music21 import clef, meter, note, chord, stream

    bars = {number: (begin, length) for number, begin, length in data.bars}
    if start not in bars or end not in bars:
        return None
    origin = bars[start][0]
    finish = bars[end][0] + bars[end][1]
    signature = next((label for bar, label in reversed(data.metres) if bar <= start), None) or "4/4"
    score = stream.Score()
    for hand, symbol in ((0, clef.TrebleClef()), (1, clef.BassClef())):
        part = stream.Part()
        part.insert(0, symbol)
        part.insert(0, meter.TimeSignature(signature))
        hits = [hit for hit in data.hits if hit.hand == hand and origin - 1e-6 <= hit.onset < finish]
        hits.sort(key=lambda hit: hit.onset)
        for index, hit in enumerate(hits):
            following = hits[index + 1].onset if index + 1 < len(hits) else finish
            length = max(min(hit.duration, following - hit.onset, finish - hit.onset), 0.0625)
            element = note.Note(hit.pitches[0], quarterLength=length) if len(hit.pitches) == 1 else chord.Chord(list(hit.pitches), quarterLength=length)
            part.insert(hit.onset - origin, element)
        part.makeRests(fillGaps=True, inPlace=True)
        part.makeMeasures(inPlace=True)
        for offset, measure in enumerate(part.getElementsByClass(stream.Measure)):
            measure.number = start + offset
        score.insert(0, part)
    return score


def render_from_notes(data, start: int, end: int) -> Optional[str]:
    import verovio

    excerpt = excerpt_from_notes(data, start, end)
    if excerpt is None:
        return None
    with tempfile.TemporaryDirectory(prefix="excerpt-") as scratch:
        path = Path(scratch) / "excerpt.musicxml"
        excerpt.write("musicxml", fp=str(path))
        toolkit = verovio.toolkit()
        toolkit.setOptions({"pageWidth": 1900, "pageHeight": 6000, "scale": 45, "adjustPageHeight": True, "header": "none", "footer": "none", "mnumInterval": 1, "svgViewBox": True})
        if not toolkit.loadFile(str(path)):
            return None
        svg = toolkit.renderToSVG(1)
        return svg if "<svg" in svg else None
