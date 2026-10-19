import argparse
import json
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]

SOURCES = {
    "chopin-fe": {
        "name": "First Editions of Fryderyk Chopin's Music, Fryderyk Chopin Institute",
        "license": "CC BY 4.0",
        "url": "https://github.com/pl-wnifc/humdrum-chopin-first-editions",
        "attribution": "First Editions of Fryderyk Chopin's Music. Copyright 2017-2021 The Fryderyk Chopin Institute (https://nifc.pl). Website: https://chopinscores.org",
        "commercial": True,
    },
}

CHOPIN_GENRES = {
    "etude": "Étude", "mazurk": "Mazurka", "mazourk": "Mazurka", "nocturn": "Nocturne", "valse": "Waltz", "waltz": "Waltz", "polonais": "Polonaise",
    "prelud": "Prelude", "impromptu": "Impromptu", "ballad": "Ballade", "scherzo": "Scherzo", "rondo": "Rondo",
    "sonat": "Piano Sonata", "variation": "Variations", "fantaisie": "Fantaisie", "fantasy": "Fantaisie", "berceuse": "Berceuse",
    "barcarol": "Barcarolle", "bolero": "Bolero", "tarantel": "Tarantelle", "allegro de concert": "Allegro de concert",
    "ecossais": "Écossaises", "concerto": "Piano Concerto", "krakowiak": "Krakowiak", "trio": "Piano Trio",
}


def clean_movement(name):
    name = re.sub(r"\[[^\]]*\]\s*=\s*[\d.]+", "", name or "")
    name = re.sub(r"\(\s*\)", "", name)
    name = " ".join(name.replace("\\n", " ").split()).strip(" .,;:-")
    words = name.split()
    if words and all(word.isupper() for word in words if word.isalpha()):
        name = name.capitalize()
    else:
        name = " ".join(word.capitalize() if word.isupper() and len(word) > 2 else word for word in words)
    return name


def roman(n):
    return ROMAN[n - 1] if 1 <= n <= len(ROMAN) else str(n)


def kern_refs(path):
    refs = {}
    key = None
    with open(path, encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if line.startswith("!!!"):
                name, _, value = line[3:].partition(":")
                refs.setdefault(name.strip(), []).append(value.strip())
            elif key is None and line.startswith("*"):
                found = re.search(r"\*([A-Ga-g][#-]?):", line)
                if found:
                    key = found.group(1)
    return refs, key


def key_name(token):
    if not token:
        return None
    note = token[0].upper()
    accidental = {"#": "-sharp", "-": "-flat"}.get(token[1:2], "")
    return f"{note}{accidental} {'major' if token[0].isupper() else 'minor'}"


def person(name):
    if "," in name:
        last, first = [part.strip() for part in name.split(",", 1)]
        name = f"{first} {last}"
    return name.replace("Fryderyk", "Frederic").replace("Frédéric", "Frederic")


def spec(source, path, composer, title, catalog, key=None, movement=None, parent=None, nickname=None):
    return {
        "source": source, "path": str(path), "composer": composer, "title": title, "catalog": catalog, "key": key,
        "movement": movement, "parent": parent, "nickname": nickname,
    }


def collect(chopin_root):
    specs = []
    seen_chopin = set()
    skip_opus = {2, 3, 8, 11, 13, 14, 21, 65, 74}
    sonata_opus = {4: "Piano Sonata No. 1 in C minor", 35: "Piano Sonata No. 2 in B-flat minor", 58: "Piano Sonata No. 3 in B minor"}
    for path in sorted((chopin_root / "kern").glob("*.krn")):
        if any(word in path.stem for word in ("violin", "violoncello", "cello", "piano")):
            continue
        refs, key = kern_refs(path)
        otl = (refs.get("OTL") or [path.stem])[0]
        ops = (refs.get("OPS") or [""])[0]
        found = re.match(r"^(\d{3})(?:_[\dA-Za-z-]+)?-[^-]+-[^-]+(?:-(\d{3}))?", path.stem)
        opus = int(found.group(1)) if found else None
        number = int(found.group(2)) if found and found.group(2) else None
        genre = next((name for word, name in CHOPIN_GENRES.items() if word in otl.lower()), otl.title())
        if opus in skip_opus or genre in ("Piano Trio", "Piano Concerto"):
            continue
        if opus in sonata_opus and number:
            ident = ("op", opus, number)
            if ident in seen_chopin:
                continue
            seen_chopin.add(ident)
            parent = sonata_opus[opus]
            specs.append(spec("chopin-fe", path, "Frederic Chopin", f"{parent}, Op. {opus}: {roman(number)}", f"Op. {opus}", key_name(key), (number, ""), parent))
            continue
        if opus is None:
            catalog = None
            ident = ("title", otl.lower())
        else:
            catalog = f"Op. {opus}" + (f" No. {number}" if number else "")
            ident = ("op", opus, number)
        if ident in seen_chopin:
            continue
        seen_chopin.add(ident)
        key_text = key_name(key)
        title = f"{genre} in {key_text}" if key_text else genre
        specs.append(spec("chopin-fe", path, "Frederic Chopin", title, catalog, key_text))
    return specs


def identity(item):
    from app.services.work_titles import match_text

    catalog = match_text(item.get("catalog") or "").strip()
    movement = item["movement"][0] if item.get("movement") else 0
    surname = item["composer"].split()[-1].lower()
    title = match_text(item["title"]).strip() if not catalog else ""
    kind = ""
    if surname == "bach" and catalog.startswith("bwv 8") and not item.get("movement"):
        kind = "fugue" if "fugue" in item["title"].lower() else "prelude"
    return (surname, catalog, movement, title, kind)


PRIORITY = [name for name, source in SOURCES.items() if source["commercial"]]


def run_one(item):
    from app.services.score_analysis import analyse_file

    started = time.time()
    try:
        report = analyse_file(Path(item["path"]).read_bytes(), item["path"])
    except Exception as error:
        return item, None, f"{type(error).__name__}: {error}"
    return item, report, round(time.time() - started, 1)


def as_entry(item, report):
    return {
        "composer": item["composer"],
        "title": item["title"],
        "catalog": item["catalog"],
        "key": item["key"] or report.key,
        "parent": item["parent"],
        "movement": item["movement"],
        "nickname": item["nickname"],
        "source": item["source"],
        "bars": report.measures,
        "duration_sec": int(report.duration_sec),
        "tempo_bpm": round(report.quarter_bpm),
        "techniques": report.techniques,
        "estimated_difficulty": report.estimated_difficulty,
        "features": {key: round(value, 3) for key, value in report.features.items()},
        "passages": [
            {
                "start": p.start, "end": p.end, "label": p.label, "description": p.description, "cue": p.cue,
                "techniques": p.techniques, "relative": p.difficulty,
            }
            for p in report.passages
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chopin", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    specs = [item for item in collect(args.chopin) if item["source"] in PRIORITY]
    specs.sort(key=lambda item: PRIORITY.index(item["source"]))
    unique, seen = [], {}
    for item in specs:
        ident = identity(item)
        if ident in seen:
            kept = seen[ident]
            if not kept["key"] and item["key"]:
                kept["key"] = item["key"]
                if " in " not in kept["title"] and kept["composer"].endswith("Bach"):
                    kept["title"] = item["title"]
            if kept["movement"] and item["movement"] and not kept["movement"][1] and item["movement"][1]:
                kept["movement"] = item["movement"]
            continue
        seen[ident] = item
        unique.append(item)
    if args.limit:
        unique = unique[: args.limit]
    print(f"{len(specs)} files, {len(unique)} distinct works", flush=True)

    entries, failures = [], []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_one, item) for item in unique]
        for index, future in enumerate(as_completed(futures), start=1):
            item, report, note = future.result()
            if report is None or report.measures < 2 or report.notes < 20:
                failures.append((item["path"], note))
            else:
                entries.append(as_entry(item, report))
            if index % 25 == 0:
                print(f"{index}/{len(unique)}", flush=True)
    entries.sort(key=lambda e: (e["composer"], e["parent"] or e["title"], (e["movement"] or [0])[0]))
    payload = {"version": 1, "sources": SOURCES, "entries": entries}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {len(entries)} entries, {len(failures)} failures")
    for path, note in failures[:40]:
        print("  fail", path, note)


if __name__ == "__main__":
    main()
