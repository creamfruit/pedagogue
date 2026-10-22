import re
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator, Optional
from urllib.parse import urljoin

from . import config
from .licences import is_allowed, parse_licence, rejection_reason
from .models import Candidate, Rejection
from .polite import PoliteClient

SITE = "https://www.mutopiaproject.org"
LISTING = f"{SITE}/cgibin/make-table.cgi"
LISTING_PARAMS = {
    "searchingfor": "",
    "Composer": "",
    "Instrument": "Piano",
    "Style": "",
    "collection": "",
    "id": "",
    "solo": "1",
    "recent": "",
    "timelength": "1",
    "timeunit": "week",
    "lilyversion": "",
    "preview": "1",
}
SOLO_PIANO = "for piano"
LIFESPAN = re.compile(r"\(\s*(?:c\.|ca\.|fl\.)?\s*(\d{3,4})?\s*[–—-]\s*(?:c\.|ca\.)?\s*(\d{3,4})?\s*\)\s*$")
INFO_ID = re.compile(r"piece-info\.cgi\?id=(\d+)")
HEADER_PAIR = re.compile(r'(\w+)\s*=\s*"((?:[^"\\]|\\.)*)"', re.S)
NEXT_LINK = re.compile(r'href="(make-table\.cgi\?[^"]*)">\s*Next\s*\d*\s*</a>', re.I)


@dataclass
class Cell:
    text: str
    links: list


class ListingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[Cell]]] = []
        self._table: Optional[list] = None
        self._row: Optional[list] = None
        self._cell: Optional[dict] = None
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "table" and "result-table" in (values.get("class") or ""):
            self._table = []
            self._depth = 1
        elif self._table is not None:
            if tag == "table":
                self._depth += 1
            elif tag == "tr":
                self._row = []
                self._row_class = values.get("class") or ""
            elif tag == "td" and self._row is not None:
                self._cell = {"text": [], "links": []}
            elif tag == "a" and self._cell is not None and values.get("href"):
                self._cell["links"].append([values["href"], ""])
            elif tag in {"img", "object"} and self._cell is not None:
                self._cell["text"].append("")

    def handle_endtag(self, tag):
        if self._table is None:
            return
        if tag == "td" and self._cell is not None and self._row is not None:
            text = " ".join("".join(self._cell["text"]).split())
            self._row.append(Cell(text, [tuple(link) for link in self._cell["links"]]))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if "preview" not in getattr(self, "_row_class", "") and self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table":
            self._depth -= 1
            if self._depth == 0:
                self.tables.append(self._table)
                self._table = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"].append(data)
            if self._cell["links"]:
                self._cell["links"][-1][1] += data


@dataclass
class Entry:
    mutopia_id: int
    title: str
    composer: str
    born: Optional[int]
    died: Optional[int]
    opus: str
    instrument: str
    year: str
    style: str
    arranger: str
    source_note: str
    licence_text: str
    date_added: str
    ly_url: str
    midi_url: str
    folder_url: str


def clean(text: str) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


def split_composer(text: str) -> tuple[str, Optional[int], Optional[int]]:
    value = clean(text)
    value = re.sub(r"^by\s+", "", value, flags=re.I)
    found = LIFESPAN.search(value)
    if not found:
        return value, None, None
    name = value[: found.start()].strip()
    born = int(found.group(1)) if found.group(1) else None
    died = int(found.group(2)) if found.group(2) else None
    return name, born, died


def link_to(cell_list: list[Cell], suffix: str) -> str:
    for cell in cell_list:
        for href, _ in cell.links:
            if href.lower().endswith(suffix):
                return href
    return ""


def parse_table(rows: list[list[Cell]]) -> Optional[Entry]:
    if len(rows) < 4:
        return None
    first, second, third, downloads = rows[0], rows[1], rows[2], rows[3]
    if len(first) < 2 or len(second) < 1 or len(third) < 3:
        return None
    info = next((INFO_ID.search(href) for cell in third for href, _ in cell.links if INFO_ID.search(href)), None)
    if info is None:
        return None
    licence_cell = next((cell for cell in third if any("legal.html" in href for href, _ in cell.links)), None)
    name, born, died = split_composer(first[1].text)
    return Entry(
        mutopia_id=int(info.group(1)),
        title=clean(first[0].text),
        composer=name,
        born=born,
        died=died,
        opus=clean(first[2].text) if len(first) > 2 else "",
        instrument=clean(second[0].text),
        year=clean(second[1].text) if len(second) > 1 else "",
        style=clean(second[2].text) if len(second) > 2 else "",
        arranger=clean(second[3].text) if len(second) > 3 else "",
        source_note=clean(third[0].text),
        licence_text=clean(licence_cell.text) if licence_cell else "",
        date_added=clean(third[-1].text),
        ly_url=link_to(downloads, ".ly") or link_to(downloads, "-lys.zip"),
        midi_url=link_to(downloads, ".mid"),
        folder_url=next((href for cell in downloads for href, _ in cell.links if href.endswith("/")), ""),
    )


def parse_listing(html: str) -> tuple[list[Entry], Optional[str]]:
    parser = ListingParser()
    parser.feed(html)
    entries = [entry for entry in (parse_table(rows) for rows in parser.tables) if entry is not None]
    following = NEXT_LINK.search(html)
    return entries, (following.group(1).replace("&amp;", "&") if following else None)


def crawl(client: PoliteClient, *, max_pages: Optional[int] = None) -> Iterator[Entry]:
    url: Optional[str] = LISTING
    params: Optional[dict] = {**LISTING_PARAMS, "startat": "0"}
    pages = 0
    seen = set()
    while url is not None and (max_pages is None or pages < max_pages):
        reply = client.get(url, params=params, max_age=config.CATALOGUE_MAX_AGE_SECONDS)
        if not reply.ok:
            break
        entries, following = parse_listing(reply.text)
        pages += 1
        for entry in entries:
            if entry.mutopia_id not in seen:
                seen.add(entry.mutopia_id)
                yield entry
        if following is None or not entries:
            break
        url, params = urljoin(f"{SITE}/cgibin/", following), None


def parse_ly_header(text: str) -> dict:
    start = re.search(r"\\header\s*\{", text)
    if start is None:
        return {}
    depth, index = 1, start.end()
    while index < len(text) and depth:
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
        index += 1
    body = text[start.end() : index - 1]
    return {key: value.replace('\\"', '"').strip() for key, value in HEADER_PAIR.findall(body)}


def candidate_from(entry: Entry) -> tuple[Optional[Candidate], Optional[Rejection]]:
    def reject(stage: str, reason: str) -> tuple[None, Rejection]:
        return None, Rejection("mutopia", str(entry.mutopia_id), entry.title, entry.composer, stage, reason)

    if clean(entry.instrument).lower() != SOLO_PIANO:
        return reject("instrument", f"not solo piano ({entry.instrument or 'unknown'})")
    licence = parse_licence(entry.licence_text)
    if licence is None:
        return reject("licence", rejection_reason(entry.licence_text))
    if not is_allowed(licence):
        return reject("licence", f"licence not allowed ({licence.name})")
    if not entry.ly_url or not entry.midi_url:
        return reject("files", "no LilyPond source or MIDI file")
    return (
        Candidate(
            source="mutopia",
            source_id=str(entry.mutopia_id),
            title=entry.title,
            composer=entry.composer,
            source_url=f"{SITE}/cgibin/piece-info.cgi?id={entry.mutopia_id}",
            licence=licence,
            licence_text=entry.licence_text,
            instrument="Piano",
            born=entry.born,
            died=entry.died,
            attribution="",
            catalog_number=entry.opus,
            year=entry.year,
            style=entry.style,
            files={("lys" if entry.ly_url.endswith(".zip") else "ly"): entry.ly_url, "mid": entry.midi_url},
            extra={"arranger": entry.arranger, "published": entry.source_note, "added": entry.date_added},
        ),
        None,
    )


def verify_header(candidate: Candidate, header: dict) -> Optional[str]:
    declared = header.get("license") or header.get("copyright") or ""
    stated = parse_licence(declared)
    if stated is None:
        return f"LilyPond header has no clear licence ({declared or 'none given'})"
    if stated.code != candidate.licence.code or stated.version != candidate.licence.version:
        return f"licence differs between the catalogue ({candidate.licence.name}) and the file ({stated.name})"
    return None


def apply_header(candidate: Candidate, header: dict) -> Candidate:
    maintainer = header.get("maintainer", "").strip()
    candidate.attribution = maintainer
    candidate.extra["header"] = {key: header[key] for key in ("title", "composer", "opus", "source", "style", "date", "mutopiacomposer", "mutopiainstrument", "maintainer", "license", "copyright") if key in header}
    if header.get("composer"):
        candidate.extra["composer_full"] = header["composer"]
    return candidate


LILYPOND_SUFFIXES = {".ly", ".ily"}


def unpack_sources(archive: Path, folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    root = folder.resolve()
    written = []
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if member.is_dir() or Path(member.filename).suffix.lower() not in LILYPOND_SUFFIXES:
                continue
            target = (folder / member.filename).resolve()
            if root not in target.parents:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(member))
            written.append(target)
    return written


def main_source(paths: list[Path], stem: str) -> Optional[Path]:
    scored = []
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        header = parse_ly_header(text)
        if not header:
            continue
        rank = (("mutopiacomposer" in header) + ("license" in header) + (path.stem == stem), len(text))
        scored.append((rank, path))
    return max(scored)[1] if scored else None


def fetch_files(client: PoliteClient, candidate: Candidate, folder: Path) -> tuple[dict, Optional[str], Optional[dict]]:
    folder.mkdir(parents=True, exist_ok=True)
    if "ly" in candidate.files:
        url = candidate.files["ly"]
        source = client.download(url, folder / url.rsplit("/", 1)[-1])
        main = source
    else:
        url = candidate.files["lys"]
        archive = client.download(url, folder / url.rsplit("/", 1)[-1])
        stem = archive.name.removesuffix("-lys.zip")
        main = main_source(unpack_sources(archive, folder / "lys"), stem)
        if main is None:
            return {}, "the LilyPond archive holds no file with a header", None
    header = parse_ly_header(main.read_text(encoding="utf-8", errors="replace"))
    problem = verify_header(candidate, header)
    if problem:
        return {}, problem, header
    midi_url = candidate.files["mid"]
    midi = client.download(midi_url, folder / midi_url.rsplit("/", 1)[-1])
    return {"ly": main.as_posix(), "mid": midi.as_posix()}, None, header
