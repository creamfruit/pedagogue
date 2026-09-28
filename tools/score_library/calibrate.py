import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

FEATURES = ["p90", "p50", "peak", "minutes", "nps_peak", "tech_peak"]


def row(entry):
    from app.services.score_library import feature_row

    return feature_row(entry["features"])


def title_for_lookup(entry):
    title = entry["title"]
    if entry.get("parent") and entry.get("movement"):
        number = entry["movement"][0]
        roman = ["I", "II", "III", "IV", "V", "VI", "VII"][number - 1] if 1 <= number <= 7 else str(number)
        title = f"{entry['parent']}: {roman}. {entry['movement'][1]}"
    return title


CHOPIN_OPUS_GENRE = {}
for _genre, _numbers in {
    "Rondo": [1, 16], "Rondo à la mazur": [5], "Mazurka": [6, 7, 17, 24, 30, 33, 41, 50, 56, 59, 63, 67, 68],
    "Nocturne": [9, 15, 27, 32, 37, 48, 55, 62], "Étude": [10, 25], "Variations brillantes": [12], "Waltz": [18, 34, 42, 64, 69, 70],
    "Bolero": [19], "Scherzo": [20, 31, 39, 54], "Andante spianato et Grande polonaise brillante": [22], "Ballade": [23, 38, 47, 52],
    "Polonaise": [26, 40, 44, 53, 71], "Prelude": [28, 45], "Impromptu": [29, 36, 51], "Fantaisie-Impromptu": [66],
    "Tarantelle": [43], "Allegro de concert": [46], "Fantaisie": [49], "Berceuse": [57], "Barcarolle": [60], "Polonaise-Fantaisie": [61],
}.items():
    for _number in _numbers:
        CHOPIN_OPUS_GENRE[_number] = _genre


def chopin_title(entry):
    found = re.match(r"Op\. (\d+)", entry.get("catalog") or "")
    if not found or entry.get("parent"):
        return entry["title"]
    genre = CHOPIN_OPUS_GENRE.get(int(found.group(1)))
    if not genre:
        return entry["title"]
    return f"{genre} in {entry['key']}" if entry.get("key") and genre not in ("Andante spianato et Grande polonaise brillante",) else genre


def clean(entries):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_library import clean_movement, roman

    for entry in entries:
        if entry.get("movement"):
            number, name = entry["movement"]
            name = clean_movement(name)
            entry["movement"] = [number, name]
            if entry.get("parent"):
                head = entry["title"].split(f": {roman(number)}.")[0].split(f": {roman(number)}")[0]
                entry["title"] = f"{head}: {roman(number)}. {name}" if name else f"{head}: {roman(number)}"
        entry["title"] = entry["title"].replace(" in None", f" in {entry['key']}" if entry.get("key") else "").replace(", None:", ":")
        found = re.match(r"^(Prelude|Fugue) from (The Well-Tempered Clavier .*)$", entry["title"])
        if found and entry.get("key"):
            entry["title"] = f"{found.group(1)} in {entry['key']} from {found.group(2)}"
        if entry["source"] == "chopin-fe":
            entry["title"] = chopin_title(entry)
        entry["title"] = re.sub(r"^Mazourka(?: No\. \d+\.)?", "Mazurka", entry["title"])
        if entry["title"] in ("Mazurka", "Nocturne", "Waltz", "Polonaise", "Prelude", "Étude", "Impromptu", "Scherzo") and entry.get("key"):
            entry["title"] = f"{entry['title']} in {entry['key']}"
        for passage in entry.get("passages", []):
            passage["label"] = passage["label"].replace("Dense passage", "Busiest bars").replace("dense passage", "busiest bars")
            passage["description"] = passage["description"].replace("the busiest texture in the piece", "the thickest, busiest writing in the piece")
        entry["title"] = " ".join(entry["title"].replace("\\n", " ").split())


def reference_for(entry, lookup):
    if entry["composer"].endswith("Bach") and entry["title"].startswith("Fugue"):
        return None, None
    full = lookup(title_for_lookup(entry), entry["composer"], entry.get("catalog"))
    if full is None or not entry.get("movement"):
        return full, None
    whole = lookup(entry.get("parent") or entry["title"], entry["composer"], entry.get("catalog"))
    if whole is not None and whole is full:
        return None, whole
    return full, None


def main():
    from app.services.repertoire_reference import lookup

    parser = argparse.ArgumentParser()
    parser.add_argument("library", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.library.read_text())
    entries = payload["entries"]
    clean(entries)
    numbered = {(e["composer"], e["catalog"].split(" No.")[0]) for e in entries if e.get("catalog") and " No. " in e["catalog"]}
    kept, seen = [], set()
    for entry in entries:
        if entry["source"] == "chopin-fe" and entry.get("catalog") and (entry["composer"], entry["catalog"]) in numbered:
            continue
        title = entry["title"]
        if re.match(r"^[A-Za-z]{2,5}-\d", title) or re.match(r"^\d{3}-", title) or "Grand Duo" in title:
            continue
        ident = (entry["composer"], title.rstrip(".").lower(), entry.get("catalog"))
        if ident in seen:
            continue
        seen.add(ident)
        kept.append(entry)
    entries[:] = kept
    payload["entries"] = kept

    known_x, known_y, placed, caps = [], [], {}, {}
    for index, entry in enumerate(entries):
        reference, whole = reference_for(entry, lookup)
        if reference is not None:
            placed[index] = reference.difficulty
            known_x.append(row(entry))
            known_y.append(reference.difficulty)
        elif whole is not None:
            caps[index] = whole.difficulty
    x, y = np.array(known_x), np.array(known_y)
    ridge = 2.0 * np.eye(x.shape[1])
    ridge[0, 0] = 0.0
    weights = np.linalg.solve(x.T @ x + ridge, x.T @ y)
    predicted = x @ weights
    error = float(np.sqrt(np.mean((predicted - y) ** 2)))
    print(f"calibrated on {len(y)} reference pieces, rmse {error:.1f}")

    for index, entry in enumerate(entries):
        if index in placed:
            entry["difficulty"] = placed[index]
            entry["difficulty_basis"] = "reference"
        else:
            value = float(np.array(row(entry)) @ weights)
            if index in caps:
                value = min(max(value, 0.6 * caps[index]), caps[index])
            entry["difficulty"] = round(min(max(value, 5.0), 94.0), 1)
            entry["difficulty_basis"] = "score"
    payload["calibration"] = {"pieces": len(y), "rmse": round(error, 1), "weights": [round(float(w), 4) for w in weights]}
    args.library.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    ranked = sorted(entries, key=lambda e: -e["difficulty"])
    for entry in ranked[:12] + ranked[-8:]:
        print(f"{entry['difficulty']:5.1f} {entry['difficulty_basis']:9} {entry['composer']}: {entry['title']}")


if __name__ == "__main__":
    main()
