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
    "asap": {"name": "ASAP dataset (MusicXML scores)", "license": "CC BY-NC-SA 4.0", "url": "https://github.com/fosfrancesco/asap-dataset"},
    "chopin-fe": {"name": "Chopin first editions, Chopin Institute", "license": "CC BY 4.0", "url": "https://github.com/pl-wnifc/humdrum-chopin-first-editions"},
    "beethoven": {"name": "Beethoven piano sonatas, Craig Sapp", "license": "see repository", "url": "https://github.com/craigsapp/beethoven-piano-sonatas"},
    "mozart": {"name": "Mozart piano sonatas, Craig Sapp", "license": "see repository", "url": "https://github.com/craigsapp/mozart-piano-sonatas"},
    "haydn": {"name": "Haydn piano sonatas, Craig Sapp", "license": "see repository", "url": "https://github.com/craigsapp/haydn-piano-sonatas"},
    "scarlatti": {"name": "Scarlatti keyboard sonatas, Craig Sapp", "license": "see repository", "url": "https://github.com/craigsapp/scarlatti-keyboard-sonatas"},
    "joplin": {"name": "Joplin, Craig Sapp", "license": "CC BY-NC-SA 4.0", "url": "https://github.com/craigsapp/joplin"},
    "hummel": {"name": "Hummel preludes, Craig Sapp", "license": "see repository", "url": "https://github.com/craigsapp/hummel-preludes"},
    "bach-wtc": {"name": "Bach Well-Tempered Clavier, Humdrum", "license": "see repository", "url": "https://github.com/humdrum-tools/bach-wtc"},
    "inventions": {"name": "Bach inventions, Humdrum", "license": "see repository", "url": "https://github.com/humdrum-tools/inventions"},
}

BEETHOVEN_OPUS = {
    1: "Op. 2 No. 1", 2: "Op. 2 No. 2", 3: "Op. 2 No. 3", 4: "Op. 7", 5: "Op. 10 No. 1", 6: "Op. 10 No. 2", 7: "Op. 10 No. 3",
    8: "Op. 13", 9: "Op. 14 No. 1", 10: "Op. 14 No. 2", 11: "Op. 22", 12: "Op. 26", 13: "Op. 27 No. 1", 14: "Op. 27 No. 2",
    15: "Op. 28", 16: "Op. 31 No. 1", 17: "Op. 31 No. 2", 18: "Op. 31 No. 3", 19: "Op. 49 No. 1", 20: "Op. 49 No. 2",
    21: "Op. 53", 22: "Op. 54", 23: "Op. 57", 24: "Op. 78", 25: "Op. 79", 26: "Op. 81a", 27: "Op. 90", 28: "Op. 101",
    29: "Op. 106", 30: "Op. 109", 31: "Op. 110", 32: "Op. 111",
}
BEETHOVEN_NICKNAMES = {8: "Pathétique", 14: "Moonlight", 15: "Pastoral", 17: "Tempest", 21: "Waldstein", 23: "Appassionata", 26: "Les Adieux", 29: "Hammerklavier"}

ASAP_META = {
    "Balakirev/Islamey": ("Mily Balakirev", "Islamey, Oriental Fantasy", "Op. 18", None),
    "Brahms/Six_Pieces_op_118/2": ("Johannes Brahms", "Intermezzo in A major", "Op. 118 No. 2", None),
    "Chopin/Ballades/1": ("Frederic Chopin", "Ballade No. 1 in G minor", "Op. 23", None),
    "Chopin/Ballades/2": ("Frederic Chopin", "Ballade No. 2 in F major", "Op. 38", None),
    "Chopin/Ballades/3": ("Frederic Chopin", "Ballade No. 3 in A-flat major", "Op. 47", None),
    "Chopin/Ballades/4": ("Frederic Chopin", "Ballade No. 4 in F minor", "Op. 52", None),
    "Chopin/Barcarolle": ("Frederic Chopin", "Barcarolle in F-sharp major", "Op. 60", None),
    "Chopin/Berceuse_op_57": ("Frederic Chopin", "Berceuse in D-flat major", "Op. 57", None),
    "Chopin/Polonaises/53": ("Frederic Chopin", "Polonaise in A-flat major, Heroic", "Op. 53", None),
    "Chopin/Scherzos/20": ("Frederic Chopin", "Scherzo No. 1 in B minor", "Op. 20", None),
    "Chopin/Scherzos/31": ("Frederic Chopin", "Scherzo No. 2 in B-flat minor", "Op. 31", None),
    "Chopin/Scherzos/39": ("Frederic Chopin", "Scherzo No. 3 in C-sharp minor", "Op. 39", None),
    "Chopin/Sonata_2/1st_no_repeat": ("Frederic Chopin", "Piano Sonata No. 2 in B-flat minor", "Op. 35", (1, "Grave – Doppio movimento")),
    "Chopin/Sonata_2/2nd": ("Frederic Chopin", "Piano Sonata No. 2 in B-flat minor", "Op. 35", (2, "Scherzo")),
    "Chopin/Sonata_2/3rd": ("Frederic Chopin", "Piano Sonata No. 2 in B-flat minor", "Op. 35", (3, "Marche funèbre")),
    "Chopin/Sonata_2/4th": ("Frederic Chopin", "Piano Sonata No. 2 in B-flat minor", "Op. 35", (4, "Finale: Presto")),
    "Chopin/Sonata_3/2nd": ("Frederic Chopin", "Piano Sonata No. 3 in B minor", "Op. 58", (2, "Scherzo: Molto vivace")),
    "Chopin/Sonata_3/3rd": ("Frederic Chopin", "Piano Sonata No. 3 in B minor", "Op. 58", (3, "Largo")),
    "Chopin/Sonata_3/4th": ("Frederic Chopin", "Piano Sonata No. 3 in B minor", "Op. 58", (4, "Finale: Presto non tanto")),
    "Debussy/Images_Book_1/1_Reflets_dans_lEau": ("Claude Debussy", "Images, Book 1: Reflets dans l'eau", "L. 110 No. 1", None),
    "Debussy/Pour_le_Piano/1": ("Claude Debussy", "Pour le piano: Prélude", "L. 95 No. 1", None),
    "Glinka/The_Lark": ("Mikhail Glinka", "The Lark (arr. Balakirev)", None, None),
    "Liszt/Annees_de_pelerinage_2/1_Gondoliera": ("Franz Liszt", "Venezia e Napoli: Gondoliera", "S. 162 No. 1", None),
    "Liszt/Ballade_2": ("Franz Liszt", "Ballade No. 2 in B minor", "S. 171", None),
    "Liszt/Concert_Etude_S145/1": ("Franz Liszt", "Concert Étude No. 1, Waldesrauschen", "S. 145 No. 1", None),
    "Liszt/Concert_Etude_S145/2": ("Franz Liszt", "Concert Étude No. 2, Gnomenreigen", "S. 145 No. 2", None),
    "Liszt/Gran_Etudes_de_Paganini/2_La_campanella": ("Franz Liszt", "Grandes études de Paganini No. 3, La Campanella", "S. 141 No. 3", None),
    "Liszt/Gran_Etudes_de_Paganini/6_Theme_and_Variations": ("Franz Liszt", "Grandes études de Paganini No. 6, Theme and Variations", "S. 141 No. 6", None),
    "Liszt/Hungarian_Rhapsodies/6": ("Franz Liszt", "Hungarian Rhapsody No. 6", "S. 244 No. 6", None),
    "Liszt/Mephisto_Waltz": ("Franz Liszt", "Mephisto Waltz No. 1", "S. 514", None),
    "Liszt/Sonata": ("Franz Liszt", "Piano Sonata in B minor", "S. 178", None),
    "Liszt/Transcendental_Etudes/1": ("Franz Liszt", "Transcendental Étude No. 1, Preludio", "S. 139 No. 1", None),
    "Liszt/Transcendental_Etudes/3": ("Franz Liszt", "Transcendental Étude No. 3, Paysage", "S. 139 No. 3", None),
    "Liszt/Transcendental_Etudes/4": ("Franz Liszt", "Transcendental Étude No. 4, Mazeppa", "S. 139 No. 4", None),
    "Liszt/Transcendental_Etudes/5": ("Franz Liszt", "Transcendental Étude No. 5, Feux follets", "S. 139 No. 5", None),
    "Liszt/Transcendental_Etudes/9": ("Franz Liszt", "Transcendental Étude No. 9, Ricordanza", "S. 139 No. 9", None),
    "Liszt/Transcendental_Etudes/10": ("Franz Liszt", "Transcendental Étude No. 10 in F minor", "S. 139 No. 10", None),
    "Liszt/Transcendental_Etudes/11": ("Franz Liszt", "Transcendental Étude No. 11, Harmonies du soir", "S. 139 No. 11", None),
    "Mozart/Fantasie_475": ("Wolfgang Amadeus Mozart", "Fantasia in C minor", "K. 475", None),
    "Prokofiev/Toccata": ("Sergei Prokofiev", "Toccata in D minor", "Op. 11", None),
    "Rachmaninoff/Preludes_op_23/4": ("Sergei Rachmaninoff", "Prelude in D major", "Op. 23 No. 4", None),
    "Rachmaninoff/Preludes_op_23/6": ("Sergei Rachmaninoff", "Prelude in E-flat major", "Op. 23 No. 6", None),
    "Rachmaninoff/Preludes_op_32/5": ("Sergei Rachmaninoff", "Prelude in G major", "Op. 32 No. 5", None),
    "Rachmaninoff/Preludes_op_32/10": ("Sergei Rachmaninoff", "Prelude in B minor", "Op. 32 No. 10", None),
    "Ravel/Gaspard_de_la_Nuit/1_Ondine": ("Maurice Ravel", "Gaspard de la nuit: I. Ondine", "M. 55 No. 1", None),
    "Ravel/Miroirs/3_Une_Barque": ("Maurice Ravel", "Miroirs: III. Une barque sur l'océan", "M. 43 No. 3", None),
    "Ravel/Miroirs/4_Alborada_del_gracioso": ("Maurice Ravel", "Miroirs: IV. Alborada del gracioso", "M. 43 No. 4", None),
    "Ravel/Pavane": ("Maurice Ravel", "Pavane pour une infante défunte", "M. 19", None),
    "Schubert/Impromptu_op.90_D.899/1": ("Franz Schubert", "Impromptu in C minor", "D. 899 No. 1", None),
    "Schubert/Impromptu_op.90_D.899/2": ("Franz Schubert", "Impromptu in E-flat major", "D. 899 No. 2", None),
    "Schubert/Impromptu_op.90_D.899/3": ("Franz Schubert", "Impromptu in G-flat major", "D. 899 No. 3", None),
    "Schubert/Impromptu_op.90_D.899/4": ("Franz Schubert", "Impromptu in A-flat major", "D. 899 No. 4", None),
    "Schubert/Impromptu_op142/1": ("Franz Schubert", "Impromptu in F minor", "D. 935 No. 1", None),
    "Schubert/Impromptu_op142/3": ("Franz Schubert", "Impromptu in B-flat major", "D. 935 No. 3", None),
    "Schubert/Moment_Musical_no_1": ("Franz Schubert", "Moment musical No. 1 in C major", "D. 780 No. 1", None),
    "Schubert/Moment_musical_no_3": ("Franz Schubert", "Moment musical No. 3 in F minor", "D. 780 No. 3", None),
    "Schubert/Piano_Sonatas/664-1": ("Franz Schubert", "Piano Sonata in A major", "D. 664", (1, "Allegro moderato")),
    "Schubert/Piano_Sonatas/664-2": ("Franz Schubert", "Piano Sonata in A major", "D. 664", (2, "Andante")),
    "Schubert/Piano_Sonatas/664-3": ("Franz Schubert", "Piano Sonata in A major", "D. 664", (3, "Allegro")),
    "Schubert/Piano_Sonatas/894-2": ("Franz Schubert", "Piano Sonata in G major", "D. 894", (2, "Andante")),
    "Schubert/Wanderer_fantasie": ("Franz Schubert", "Wanderer Fantasy in C major", "D. 760", None),
    "Schumann/Arabeske": ("Robert Schumann", "Arabeske in C major", "Op. 18", None),
    "Schumann/Toccata": ("Robert Schumann", "Toccata in C major", "Op. 7", None),
    "Scriabin/Etudes_op_8/11": ("Alexander Scriabin", "Étude in B-flat minor", "Op. 8 No. 11", None),
    "Scriabin/Sonatas/5": ("Alexander Scriabin", "Piano Sonata No. 5", "Op. 53", None),
    "Bach/Italian_concerto": ("Johann Sebastian Bach", "Italian Concerto in F major", "BWV 971", (1, "Allegro")),
}
KREISLERIANA = ["Äußerst bewegt", "Sehr innig und nicht zu rasch", "Sehr aufgeregt", "Sehr langsam", "Sehr lebhaft", "Sehr langsam", "Sehr rasch"]
CHOPIN_ETUDE_KEYS = {
    (10, 1): "C major", (10, 2): "A minor", (10, 3): "E major", (10, 4): "C-sharp minor", (10, 5): "G-flat major",
    (10, 7): "C major", (10, 8): "F major", (10, 10): "A-flat major", (10, 12): "C minor", (25, 1): "A-flat major",
    (25, 2): "F minor", (25, 4): "A minor", (25, 5): "E minor", (25, 8): "D-flat major", (25, 10): "B minor",
    (25, 11): "A minor", (25, 12): "C minor",
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


def beethoven_meta(kern_root):
    meta = {}
    for path in sorted((kern_root / "beethoven-piano-sonatas" / "kern").glob("sonata*-*.krn")):
        found = re.match(r"sonata(\d+)-(\d+)", path.stem)
        number, movement = int(found.group(1)), int(found.group(2))
        refs, key = kern_refs(path)
        base = (refs.get("OTL") or [f"Piano Sonata No. {number}"])[0].replace("no.", "No.")
        base = re.sub(r"\s*\([^)]*\)", "", base).strip()
        nickname = BEETHOVEN_NICKNAMES.get(number)
        parent_title = f"{base}, {nickname}" if nickname else base
        movement_name = clean_movement(" ".join(refs.get("OMD") or [""]))
        meta[(number, movement)] = (parent_title, BEETHOVEN_OPUS.get(number), key_name(key), movement_name, path, nickname)
    return meta


def collect(asap_root, kern_root, chopin_root):
    specs = []
    beethoven = beethoven_meta(kern_root)
    mozart = {}
    for path in sorted((kern_root / "mozart-piano-sonatas" / "kern").glob("sonata*-*.krn")):
        found = re.match(r"sonata(\d+)-(\d+)", path.stem)
        refs, key = kern_refs(path)
        k_number = next((re.sub(r"<[^>]+>", "", v).replace("K1", "K.").replace("K ", "K. ") for v in refs.get("SCT1", []) if v), None)
        k_number = re.sub(r"^K\.?\s*1?\s*", "K. ", k_number) if k_number else None
        title = (refs.get("OTL") or [""])[0]
        mozart[(int(found.group(1)), int(found.group(2)))] = (title, k_number, key_name(key), clean_movement((refs.get("OMD") or [""])[0]), path)

    for xml in sorted(asap_root.rglob("xml_score.musicxml")):
        rel = str(xml.parent.relative_to(asap_root))
        if re.search(r"_no_|_repeat$|no_repeat|no_trio", rel) and not rel.endswith("1st_no_repeat"):
            continue
        if rel in ASAP_META:
            composer, title, catalog, movement = ASAP_META[rel]
            if movement:
                specs.append(spec("asap", xml, composer, f"{title}, {catalog}: {roman(movement[0])}. {movement[1]}", catalog, movement=movement, parent=title))
            else:
                specs.append(spec("asap", xml, composer, title, catalog))
            continue
        parts = rel.split("/")
        if parts[0] == "Bach" and parts[1] in ("Prelude", "Fugue"):
            bwv = int(parts[2].split("_")[1])
            book = "I" if bwv <= 869 else "II"
            specs.append(spec("asap", xml, "Johann Sebastian Bach", f"{parts[1]} from The Well-Tempered Clavier {book}", f"BWV {bwv}"))
        elif parts[0] == "Beethoven":
            number, movement = [int(x) for x in re.findall(r"\d+", parts[2])[:2]]
            info = beethoven.get((number, movement))
            if info:
                parent_title, opus, key, movement_name, _path, nickname = info
                specs.append(spec("asap", xml, "Ludwig van Beethoven", f"{parent_title}, {opus}: {roman(movement)}. {movement_name}", opus, key, (movement, movement_name), parent_title, nickname))
        elif parts[0] == "Mozart" and parts[1] == "Piano_Sonatas":
            number, movement = [int(x) for x in re.findall(r"\d+", parts[2])[:2]]
            info = mozart.get((number, movement))
            if info:
                title, k_number, key, movement_name, _path = info
                specs.append(spec("asap", xml, "Wolfgang Amadeus Mozart", f"{title}, {k_number}: {roman(movement)}. {movement_name}", k_number, key, (movement, movement_name), title))
        elif parts[0] == "Haydn":
            number, movement = [int(x) for x in re.findall(r"\d+", parts[2])[:2]]
            title = f"Keyboard Sonata Hob. XVI:{number}"
            specs.append(spec("asap", xml, "Franz Joseph Haydn", f"{title}: {roman(movement)}", f"Hob. XVI:{number}", movement=(movement, ""), parent=title))
        elif parts[0] == "Chopin" and parts[1].startswith("Etudes_op_"):
            opus, number = int(parts[1].split("_")[-1]), int(parts[2])
            key = CHOPIN_ETUDE_KEYS.get((opus, number))
            specs.append(spec("asap", xml, "Frederic Chopin", f"Étude in {key}" if key else "Étude", f"Op. {opus} No. {number}", key))
        elif parts[0] == "Schumann" and parts[1] == "Kreisleriana":
            number = int(parts[2].split("_")[0])
            specs.append(spec("asap", xml, "Robert Schumann", f"Kreisleriana, Op. 16: {roman(number)}. {KREISLERIANA[number - 1]}", "Op. 16", movement=(number, KREISLERIANA[number - 1]), parent="Kreisleriana"))

    for (number, movement), (parent_title, opus, key, movement_name, path, nickname) in sorted(beethoven.items()):
        specs.append(spec("beethoven", path, "Ludwig van Beethoven", f"{parent_title}, {opus}: {roman(movement)}. {movement_name}", opus, key, (movement, movement_name), parent_title, nickname))
    for (number, movement), (title, k_number, key, movement_name, path) in sorted(mozart.items()):
        specs.append(spec("mozart", path, "Wolfgang Amadeus Mozart", f"{title}, {k_number}: {roman(movement)}. {movement_name}", k_number, key, (movement, movement_name), title))
    for path in sorted((kern_root / "haydn-piano-sonatas" / "kern").glob("*.krn")):
        refs, key = kern_refs(path)
        found = re.match(r"sonata(\d+)-(\d+)", path.stem)
        catalog = (refs.get("SCT") or [None])[0]
        movement = int(found.group(2)) if found else 1
        title = (refs.get("OTL") or [path.stem])[0]
        name = clean_movement((refs.get("OMD") or [""])[0])
        specs.append(spec("haydn", path, "Franz Joseph Haydn", f"{title}, {catalog}: {roman(movement)}. {name}", catalog, key_name(key), (movement, name), f"{title}"))
    for path in sorted((kern_root / "scarlatti-keyboard-sonatas" / "kern").glob("*.krn")):
        refs, key = kern_refs(path)
        cats = refs.get("SCT") or []
        k_cat = next((c for c in cats if c.startswith("K")), None)
        if k_cat:
            k_cat = re.sub(r"K\.?\s*0*", "K. ", k_cat)
        specs.append(spec("scarlatti", path, "Domenico Scarlatti", (refs.get("OTL") or [path.stem])[0], k_cat, key_name(key)))
    for path in sorted((kern_root / "joplin" / "kern").glob("*.krn")):
        refs, key = kern_refs(path)
        specs.append(spec("joplin", path, "Scott Joplin", (refs.get("OTL") or [path.stem])[0], None, key_name(key)))
    for path in sorted((kern_root / "hummel-preludes" / "kern").glob("*.krn")):
        refs, key = kern_refs(path)
        title = (refs.get("OTL") or [path.stem])[0].replace("op.", "Op.").replace("no.", "No.")
        found = re.search(r"Op\. (\d+), No\. (\d+)", title)
        specs.append(spec("hummel", path, "Johann Nepomuk Hummel", title.split(",")[0], f"Op. {found.group(1)} No. {found.group(2)}" if found else None, key_name(key)))
    for path in sorted((kern_root / "bach-wtc" / "kern").glob("wtc*.krn")):
        refs, key = kern_refs(path)
        cat = (refs.get("SCT") or [""])[0].replace("BWV ", "")
        bwv = re.sub(r"[a-z]$", "", cat)
        kind = "Fugue" if re.match(r"wtc\df", path.stem) else "Prelude"
        book = "I" if path.stem.startswith("wtc1") else "II"
        key_text = key_name(key)
        specs.append(spec("bach-wtc", path, "Johann Sebastian Bach", f"{kind} in {key_text} from The Well-Tempered Clavier {book}" if key_text else f"{kind} from The Well-Tempered Clavier {book}", f"BWV {bwv}", key_text))
    for path in sorted((kern_root / "inventions" / "kern").glob("*.krn")):
        refs, key = kern_refs(path)
        cat = (refs.get("SCT") or [""])[0]
        kind = "Sinfonia" if "sinfo" in path.stem.lower() or int(re.sub(r"\D", "", cat) or 0) >= 787 else "Invention"
        number = re.sub(r"\D", "", (refs.get("ONM") or refs.get("OTL") or [""])[0]) or ""
        if not cat and number:
            cat = f"BWV {(787 if kind == 'Sinfonia' else 772) + int(number) - 1}"
        specs.append(spec("inventions", path, "Johann Sebastian Bach", f"{kind} No. {number} in {key_name(key)}", cat, key_name(key)))

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


PRIORITY = ["asap", "beethoven", "mozart", "haydn", "chopin-fe", "bach-wtc", "inventions", "scarlatti", "joplin", "hummel"]


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
    parser.add_argument("--asap", type=Path, required=True)
    parser.add_argument("--kern", type=Path, required=True)
    parser.add_argument("--chopin", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    specs = collect(args.asap, args.kern, args.chopin)
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
