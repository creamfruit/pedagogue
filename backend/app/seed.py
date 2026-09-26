import asyncio

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import dispose_engine, session_scope
from app.models.models import (
    Achievement,
    Composer,
    Cosmetic,
    CosmeticKind,
    Era,
    Genre,
    GenreFamily,
    LinkType,
    Passage,
    PassageSource,
    PassageTechnique,
    Piece,
    PieceLinkNote,
    PieceLoadProfile,
    PieceTechnique,
    Technique,
    TechniqueCategory,
)
from app.seed_lore import COMPOSER_LORE, LINK_NOTES, PASSAGES, PIECE_LORE, TECHNIQUE_LORE
from app.services.difficulty import compute_mechanical_load, scale100

ERAS = [
    ("Baroque", 1600, 1750),
    ("Classical", 1730, 1820),
    ("Romantic", 1800, 1910),
    ("Impressionist", 1875, 1925),
    ("Modern", 1900, 1975),
    ("Contemporary", 1975, None),
]

GENRES = [
    ("Etude", GenreFamily.CLASSICAL),
    ("Nocturne", GenreFamily.CLASSICAL),
    ("Sonata", GenreFamily.CLASSICAL),
    ("Concerto", GenreFamily.CLASSICAL),
    ("Prelude", GenreFamily.CLASSICAL),
    ("Ballade", GenreFamily.CLASSICAL),
    ("Ballet", GenreFamily.CLASSICAL),
    ("Waltz", GenreFamily.CLASSICAL),
    ("Jazz standard", GenreFamily.JAZZ),
    ("Film score", GenreFamily.FILM_GAME),
    ("Game soundtrack", GenreFamily.FILM_GAME),
]

TECHNIQUES = [
    ("Double thirds", TechniqueCategory.DOUBLE_NOTES, 1.70),
    ("Double sixths", TechniqueCategory.DOUBLE_NOTES, 1.60),
    ("Broken octaves", TechniqueCategory.OCTAVES, 1.50),
    ("Blocked octaves", TechniqueCategory.OCTAVES, 1.80),
    ("Wide leaps", TechniqueCategory.LEAPS, 1.30),
    ("Repeated chords", TechniqueCategory.CHORDS, 1.65),
    ("Rapid scales", TechniqueCategory.DEXTERITY, 1.10),
    ("Arpeggio figuration", TechniqueCategory.DEXTERITY, 1.15),
    ("Repeated notes", TechniqueCategory.REPEATED_NOTES, 1.35),
    ("Trills", TechniqueCategory.TRILLS, 1.25),
    ("Tenth stretches", TechniqueCategory.STRETCHES, 1.55),
    ("Three against two", TechniqueCategory.POLYRHYTHM, 1.20),
    ("Four against three", TechniqueCategory.POLYRHYTHM, 1.40),
    ("Melody over accompaniment", TechniqueCategory.VOICING, 1.10),
    ("Inner voice projection", TechniqueCategory.VOICING, 1.30),
    ("Half pedalling", TechniqueCategory.PEDALING, 1.05),
    ("Sustained endurance", TechniqueCategory.ENDURANCE, 1.45),
]

COMPOSERS = [
    ("Johann Sebastian Bach", 1685, 1750, "German", "Baroque"),
    ("Wolfgang Amadeus Mozart", 1756, 1791, "Austrian", "Classical"),
    ("Ludwig van Beethoven", 1770, 1827, "German", "Classical"),
    ("Frederic Chopin", 1810, 1849, "Polish", "Romantic"),
    ("Franz Liszt", 1811, 1886, "Hungarian", "Romantic"),
    ("Johannes Brahms", 1833, 1897, "German", "Romantic"),
    ("Claude Debussy", 1862, 1918, "French", "Impressionist"),
    ("Sergei Rachmaninoff", 1873, 1943, "Russian", "Romantic"),
    ("Maurice Ravel", 1875, 1937, "French", "Impressionist"),
    ("Alexander Scriabin", 1872, 1915, "Russian", "Romantic"),
    ("Pyotr Ilyich Tchaikovsky", 1840, 1893, "Russian", "Romantic"),
]

MOVEMENT_WORKS = [
    (
        "Piano Concerto No. 2 in C minor",
        "Sergei Rachmaninoff",
        "Op. 18",
        "C minor",
        "Concerto",
        9.4,
        [
            ("Moderato", 1, 9.5, 660,
             [("Blocked octaves", 0.8), ("Tenth stretches", 0.8), ("Sustained endurance", 0.9)]),
            ("Adagio sostenuto", 2, 8.2, 690,
             [("Melody over accompaniment", 0.8), ("Four against three", 0.6), ("Half pedalling", 0.6)]),
            ("Allegro scherzando", 3, 9.2, 700,
             [("Rapid scales", 0.8), ("Blocked octaves", 0.7), ("Sustained endurance", 0.8)]),
        ],
    ),
]

LOAD_PROFILES = [
    ("Etude in G-sharp minor, Double Thirds", 2.10, 12, 1.20, 13.5, 1.85),
    ("Prelude in C-sharp minor", 3.40, 15, 6.80, 8.2, 1.70),
    ("Prelude in G minor", 4.10, 14, 5.20, 11.0, 1.75),
    ("Hungarian Rhapsody No. 2", 6.20, 13, 3.40, 12.4, 1.90),
    ("Transcendental Etude No. 5, Feux Follets", 1.80, 13, 0.90, 14.8, 1.95),
]

PIECES = [
    ("Invention No. 1 in C major", "Johann Sebastian Bach", "BWV 772", "C major", "Prelude", 3.0, 90,
     [("Rapid scales", 0.4), ("Inner voice projection", 0.6)]),
    ("Prelude in C major, WTC I", "Johann Sebastian Bach", "BWV 846", "C major", "Prelude", 3.5, 130,
     [("Arpeggio figuration", 0.8)]),
    ("Sonata in C major, K. 545, I", "Wolfgang Amadeus Mozart", "K. 545", "C major", "Sonata", 4.0, 240,
     [("Rapid scales", 0.7), ("Melody over accompaniment", 0.5)]),
    ("Fur Elise", "Ludwig van Beethoven", "WoO 59", "A minor", "Prelude", 4.0, 180,
     [("Arpeggio figuration", 0.5), ("Repeated notes", 0.4)]),
    ("Sonata No. 14, Moonlight, I", "Ludwig van Beethoven", "Op. 27 No. 2", "C-sharp minor", "Sonata", 4.5, 330,
     [("Melody over accompaniment", 0.7), ("Arpeggio figuration", 0.6), ("Half pedalling", 0.5)]),
    ("Sonata No. 14, Moonlight, III", "Ludwig van Beethoven", "Op. 27 No. 2", "C-sharp minor", "Sonata", 8.0, 420,
     [("Arpeggio figuration", 0.9), ("Repeated chords", 0.6), ("Sustained endurance", 0.7)]),
    ("Nocturne in E-flat major", "Frederic Chopin", "Op. 9 No. 2", "E-flat major", "Nocturne", 5.5, 270,
     [("Melody over accompaniment", 0.9), ("Half pedalling", 0.6), ("Wide leaps", 0.4)]),
    ("Etude in C minor, Revolutionary", "Frederic Chopin", "Op. 10 No. 12", "C minor", "Etude", 8.0, 160,
     [("Rapid scales", 0.9), ("Sustained endurance", 0.7), ("Arpeggio figuration", 0.6)]),
    ("Etude in G-sharp minor, Double Thirds", "Frederic Chopin", "Op. 25 No. 6", "G-sharp minor", "Etude", 9.2, 120,
     [("Double thirds", 1.0), ("Trills", 0.6), ("Sustained endurance", 0.5)]),
    ("Etude in A minor, Winter Wind", "Frederic Chopin", "Op. 25 No. 11", "A minor", "Etude", 9.3, 220,
     [("Rapid scales", 0.9), ("Sustained endurance", 0.8), ("Wide leaps", 0.5)]),
    ("Ballade No. 1 in G minor", "Frederic Chopin", "Op. 23", "G minor", "Ballade", 8.8, 570,
     [("Wide leaps", 0.7), ("Blocked octaves", 0.6), ("Sustained endurance", 0.8), ("Rapid scales", 0.7)]),
    ("Liebestraum No. 3", "Franz Liszt", "S. 541", "A-flat major", "Nocturne", 7.5, 280,
     [("Melody over accompaniment", 0.8), ("Wide leaps", 0.6), ("Arpeggio figuration", 0.7)]),
    ("Transcendental Etude No. 5, Feux Follets", "Franz Liszt", "S. 139 No. 5", "B-flat major", "Etude", 9.8, 230,
     [("Double thirds", 0.9), ("Wide leaps", 0.8), ("Rapid scales", 0.7), ("Trills", 0.5)]),
    ("Hungarian Rhapsody No. 2", "Franz Liszt", "S. 244 No. 2", "C-sharp minor", "Ballade", 9.0, 600,
     [("Blocked octaves", 0.9), ("Repeated notes", 0.6), ("Wide leaps", 0.7)]),
    ("Transcendental Etude No. 12, Chasse-neige", "Franz Liszt", "S. 139 No. 12", "B-flat minor", "Etude", 9.1, 300,
     [("Trills", 0.9), ("Inner voice projection", 0.8), ("Sustained endurance", 0.9), ("Rapid scales", 0.6)]),
    ("Rhapsody in G minor", "Johannes Brahms", "Op. 79 No. 2", "G minor", "Ballade", 7.8, 340,
     [("Three against two", 0.8), ("Blocked octaves", 0.5), ("Inner voice projection", 0.6)]),
    ("Intermezzo in A major", "Johannes Brahms", "Op. 118 No. 2", "A major", "Nocturne", 6.8, 330,
     [("Inner voice projection", 0.9), ("Melody over accompaniment", 0.7), ("Half pedalling", 0.6),
      ("Three against two", 0.4)]),
    ("Clair de lune", "Claude Debussy", "L. 75 No. 3", "D-flat major", "Prelude", 6.5, 300,
     [("Half pedalling", 0.8), ("Melody over accompaniment", 0.7), ("Four against three", 0.5)]),
    ("Arabesque No. 1", "Claude Debussy", "L. 66 No. 1", "E major", "Prelude", 5.5, 250,
     [("Three against two", 0.8), ("Arpeggio figuration", 0.6)]),
    ("Prelude in C-sharp minor", "Sergei Rachmaninoff", "Op. 3 No. 2", "C-sharp minor", "Prelude", 7.0, 250,
     [("Repeated chords", 0.9), ("Tenth stretches", 0.7), ("Sustained endurance", 0.6)]),
    ("Prelude in G minor", "Sergei Rachmaninoff", "Op. 23 No. 5", "G minor", "Prelude", 8.5, 260,
     [("Repeated chords", 0.8), ("Blocked octaves", 0.7), ("Tenth stretches", 0.6)]),
    ("Jeux d'eau", "Maurice Ravel", "M. 30", "E major", "Prelude", 8.8, 300,
     [("Double thirds", 0.6), ("Arpeggio figuration", 0.9), ("Wide leaps", 0.6)]),
    ("Etude in D-sharp minor", "Alexander Scriabin", "Op. 8 No. 12", "D-sharp minor", "Etude", 8.9, 150,
     [("Blocked octaves", 0.8), ("Wide leaps", 0.8), ("Sustained endurance", 0.7)]),
    ("Pas de deux, The Nutcracker", "Pyotr Ilyich Tchaikovsky", "Op. 71", "G major", "Ballet", 8.8, 330,
     [("Double sixths", 0.9), ("Blocked octaves", 0.7), ("Melody over accompaniment", 0.7),
      ("Sustained endurance", 0.6)]),
    ("Mephisto Waltz No. 1", "Franz Liszt", "S. 514", "A major", "Waltz", 9.5, 660,
     [("Wide leaps", 0.9), ("Blocked octaves", 0.8), ("Repeated chords", 0.6), ("Sustained endurance", 0.8)]),
]


ACHIEVEMENTS = [
    ("first_piece", "First light", "Add your first piece to the repertoire.", 60, 40, 1),
    ("first_learned", "Learnt one", "Mark your first piece as learnt.", 150, 120, 2),
    ("five_learned", "Five under the fingers", "Learn five pieces.", 400, 350, 3),
    ("twenty_learned", "Repertoire builder", "Learn twenty pieces.", 1500, 1400, 4),
    ("first_submission", "On the record", "Submit your first recording, score or notes.", 90, 70, 5),
    ("first_pass", "Graded", "Pass a graded run-through at 80 or above.", 300, 500, 6),
    ("grade_ninety", "Ninety club", "Score 90 or above on a graded run-through.", 600, 900, 7),
    ("flawless", "Flawless", "Score 98 or above on a graded run-through.", 1800, 2600, 8),
    ("grade_eight_club", "Grade eight club", "Learn a piece rated 8 or harder.", 700, 650, 9),
    ("virtuoso", "Virtuoso", "Learn a piece rated 9.5 or harder.", 2600, 3200, 10),
    ("polyrhythm_steady", "Two against three", "Hit 90 percent accuracy on a polyrhythm drill.", 250, 200, 11),
    ("level_five", "Rising", "Reach level five.", 0, 400, 12),
    ("level_ten", "Seasoned", "Reach level ten.", 0, 1200, 13),
    ("first_fortune", "First fortune", "Earn 1000 gold in total.", 200, 0, 14),
]

COSMETICS = [
    ("star_amber", CosmeticKind.STAR_COLOR, "Amber giant", "The house star. Warm and steady.", 0, 1,
     {"mode": "fixed", "color": "#f0a13c"}, 1),
    ("star_era", CosmeticKind.STAR_COLOR, "Era spectrum", "Stars take the colour of their era.", 0, 1,
     {"mode": "era"}, 2),
    ("star_ice", CosmeticKind.STAR_COLOR, "Ice field", "Cold blue-white supergiants.", 850, 2,
     {"mode": "fixed", "color": "#9fd4f0"}, 3),
    ("star_emerald", CosmeticKind.STAR_COLOR, "Emerald drift", "Rare green-tinted stars.", 1400, 3,
     {"mode": "fixed", "color": "#5fd9a4"}, 4),
    ("star_violet", CosmeticKind.STAR_COLOR, "Violet nursery", "Young, hot, violet.", 1900, 4,
     {"mode": "fixed", "color": "#a98cf5"}, 5),
    ("star_difficulty", CosmeticKind.STAR_COLOR, "Heat map", "Cool for easy, white hot for brutal.", 3200, 5,
     {"mode": "difficulty"}, 6),

    ("glow_soft", CosmeticKind.GLOW, "Soft bloom", "A gentle halo.", 0, 1, {"scale": 1.0, "core": 0.42}, 1),
    ("glow_none", CosmeticKind.GLOW, "Hard points", "No halo. Pinpoint stars.", 400, 1,
     {"scale": 0.0, "core": 0.5}, 2),
    ("glow_nova", CosmeticKind.GLOW, "Nova", "Wide, bright bloom.", 1600, 3, {"scale": 1.9, "core": 0.5}, 3),
    ("glow_corona", CosmeticKind.GLOW, "Corona", "Enormous halo with a tight core.", 3600, 6,
     {"scale": 2.8, "core": 0.34}, 4),

    ("nebula_void", CosmeticKind.NEBULA, "The void", "Pitch black. Nothing but stars.", 0, 1,
     {"layers": []}, 1),
    ("nebula_ember", CosmeticKind.NEBULA, "Ember cloud", "Warm amber gas drifting behind the stars.", 1100, 2,
     {"layers": [{"x": 22, "y": 30, "r": 70, "color": "240,161,60", "alpha": 0.1},
                 {"x": 78, "y": 68, "r": 62, "color": "232,115,74", "alpha": 0.08}]}, 2),
    ("nebula_rose", CosmeticKind.NEBULA, "Rose filament", "Deep rose and magenta.", 1500, 3,
     {"layers": [{"x": 30, "y": 70, "r": 76, "color": "224,90,120", "alpha": 0.12},
                 {"x": 72, "y": 26, "r": 58, "color": "169,140,245", "alpha": 0.09}]}, 3),
    ("nebula_aurora", CosmeticKind.NEBULA, "Aurora", "Green and teal curtains.", 2400, 4,
     {"layers": [{"x": 18, "y": 24, "r": 72, "color": "95,217,164", "alpha": 0.11},
                 {"x": 66, "y": 74, "r": 80, "color": "127,168,201", "alpha": 0.1}]}, 4),
    ("nebula_deep_field", CosmeticKind.NEBULA, "Deep field", "Faint galaxies in every direction.", 5200, 7,
     {"layers": [{"x": 50, "y": 50, "r": 96, "color": "150,160,220", "alpha": 0.08},
                 {"x": 16, "y": 78, "r": 54, "color": "240,161,60", "alpha": 0.07},
                 {"x": 84, "y": 20, "r": 60, "color": "224,90,120", "alpha": 0.07}]}, 5),

    ("link_hairline", CosmeticKind.LINK_STYLE, "Hairline", "Thin, quiet connectors.", 0, 1,
     {"width": 1.0, "alpha": 1.0, "dash": None}, 1),
    ("link_beam", CosmeticKind.LINK_STYLE, "Ion beam", "Thicker, brighter lines.", 900, 2,
     {"width": 2.1, "alpha": 1.35, "dash": None}, 2),
    ("link_dashed", CosmeticKind.LINK_STYLE, "Survey lines", "Dashed, like a star chart.", 900, 2,
     {"width": 1.2, "alpha": 1.1, "dash": [5, 5]}, 3),
    ("link_ghost", CosmeticKind.LINK_STYLE, "Ghost", "Barely there.", 650, 1,
     {"width": 0.8, "alpha": 0.5, "dash": None}, 4),
]


async def seed_catalog_detail() -> None:
    async with session_scope() as session:
        techniques = {
            t.name: t for t in (await session.execute(select(Technique))).scalars().all()
        }
        for name, (description, mechanic, fault) in TECHNIQUE_LORE.items():
            technique = techniques.get(name)
            if technique is None:
                continue
            technique.description = description
            technique.mechanic = mechanic
            technique.common_fault = fault

        composers = {
            c.name: c for c in (await session.execute(select(Composer))).scalars().all()
        }
        eras = {e.name: e for e in (await session.execute(select(Era))).scalars().all()}
        for name, birth, death, nation, era in COMPOSERS:
            if name in composers or era not in eras:
                continue
            composer = Composer(
                name=name, birth_year=birth, death_year=death, nationality=nation, era_id=eras[era].id
            )
            session.add(composer)
            composers[name] = composer

        genres = {g.name: g for g in (await session.execute(select(Genre))).scalars().all()}
        for name, family in GENRES:
            if name not in genres:
                genre = Genre(name=name, family=family)
                session.add(genre)
                genres[name] = genre
        await session.flush()

        for name, (bio, fact, sound) in COMPOSER_LORE.items():
            composer = composers.get(name)
            if composer is None:
                continue
            composer.bio = bio
            composer.fun_fact = fact
            composer.signature_sound = sound

        pieces = {p.title: p for p in (await session.execute(select(Piece))).scalars().all()}
        load_factors = {name: float(technique.load_factor) for name, technique in techniques.items()}
        added = 0
        for title, composer_name, catalog, key, genre_name, difficulty, duration, links in PIECES:
            if title in pieces:
                continue
            composer = composers.get(composer_name)
            genre = genres.get(genre_name)
            if composer is None or genre is None:
                continue
            piece = Piece(
                title=title,
                composer_id=composer.id,
                genre_id=genre.id,
                catalog_number=catalog,
                key_signature=key,
                difficulty_score=scale100(difficulty),
                mechanical_load=compute_mechanical_load(links, load_factors),
                duration_sec=duration,
            )
            session.add(piece)
            await session.flush()
            for technique_name, weight in links:
                technique = techniques.get(technique_name)
                if technique is None:
                    continue
                session.add(
                    PieceTechnique(piece_id=piece.id, technique_id=technique.id, weight=weight)
                )
            pieces[title] = piece
            added += 1
        if added:
            print(f"added {added} new catalog piece(s)")

        lored = 0
        for title, (year, tempo, mood, scene, history, fact) in PIECE_LORE.items():
            piece = pieces.get(title)
            if piece is None:
                continue
            piece.year_composed = year
            piece.tempo_marking = tempo
            piece.mood = mood
            piece.scene = scene
            piece.historical_note = history
            piece.fun_fact = fact
            lored += 1

        existing = await session.execute(
            select(Passage)
            .where(Passage.source == PassageSource.CATALOG)
            .options(selectinload(Passage.technique_links), selectinload(Passage.assessments))
        )
        stored = {(passage.piece_id, passage.label): passage for passage in existing.scalars().all()}
        kept: set[int] = set()

        sections = 0
        for title, rows in PASSAGES.items():
            piece = pieces.get(title)
            if piece is None:
                continue
            for label, start, end, difficulty, description, cue, links in rows:
                passage = stored.get((piece.id, label))
                if passage is None:
                    passage = Passage(piece_id=piece.id, label=label, source=PassageSource.CATALOG)
                    session.add(passage)
                passage.start_measure = start
                passage.end_measure = end
                passage.difficulty_score = difficulty
                passage.description = description
                passage.practice_cue = cue
                passage.technique_links = [
                    PassageTechnique(technique_id=techniques[name].id, weight=weight)
                    for name, weight in links
                    if name in techniques
                ]
                await session.flush()
                kept.add(passage.id)
                sections += 1

        seeded_piece_ids = {pieces[title].id for title in PASSAGES if title in pieces}
        for passage in stored.values():
            if passage.piece_id in seeded_piece_ids and passage.id not in kept and not passage.assessments:
                await session.delete(passage)
        await session.flush()

        notes = {
            (n.low_piece_id, n.high_piece_id, n.link_type): n
            for n in (await session.execute(select(PieceLinkNote))).scalars().all()
        }
        written = 0
        for a_title, b_title, kind, headline, summary in LINK_NOTES:
            a, b = pieces.get(a_title), pieces.get(b_title)
            if a is None or b is None:
                continue
            low, high = PieceLinkNote.order_pair(a.id, b.id)
            link_type = LinkType(kind)
            record = notes.get((low, high, link_type))
            if record is None:
                session.add(
                    PieceLinkNote(
                        low_piece_id=low,
                        high_piece_id=high,
                        link_type=link_type,
                        headline=headline,
                        summary=summary,
                    )
                )
            else:
                record.headline = headline
                record.summary = summary
            written += 1

        print(
            f"catalog detail: {lored} pieces given context, {sections} marked sections, "
            f"{written} link notes, {len(TECHNIQUE_LORE)} techniques and "
            f"{len(COMPOSER_LORE)} composers annotated"
        )


async def seed_progression() -> None:
    async with session_scope() as session:
        rows = await session.execute(select(Achievement))
        known = {row.code: row for row in rows.scalars().all()}
        added = 0
        for code, name, description, xp, gold, order in ACHIEVEMENTS:
            record = known.get(code)
            if record is None:
                session.add(
                    Achievement(
                        code=code,
                        name=name,
                        description=description,
                        xp_reward=xp,
                        gold_reward=gold,
                        sort_order=order,
                    )
                )
                added += 1
            else:
                record.name = name
                record.description = description
                record.xp_reward = xp
                record.gold_reward = gold
                record.sort_order = order
        print(f"achievements: {added} added, {len(ACHIEVEMENTS) - added} refreshed")

        rows = await session.execute(select(Cosmetic))
        owned = {row.code: row for row in rows.scalars().all()}
        added = 0
        for code, kind, name, description, price, min_level, payload, order in COSMETICS:
            record = owned.get(code)
            if record is None:
                session.add(
                    Cosmetic(
                        code=code,
                        kind=kind,
                        name=name,
                        description=description,
                        price_gold=price,
                        min_level=min_level,
                        payload=payload,
                        sort_order=order,
                    )
                )
                added += 1
            else:
                record.kind = kind
                record.name = name
                record.description = description
                record.price_gold = price
                record.min_level = min_level
                record.payload = payload
                record.sort_order = order
        print(f"cosmetics: {added} added, {len(COSMETICS) - added} refreshed")


async def seed() -> None:
    async with session_scope() as session:
        existing = await session.execute(select(Era).limit(1))
        if existing.scalar_one_or_none() is not None:
            print("catalog already seeded")
            return

        eras = {name: Era(name=name, start_year=start, end_year=end) for name, start, end in ERAS}
        session.add_all(eras.values())

        genres = {name: Genre(name=name, family=family) for name, family in GENRES}
        session.add_all(genres.values())

        techniques = {
            name: Technique(name=name, category=category, load_factor=factor)
            for name, category, factor in TECHNIQUES
        }
        session.add_all(techniques.values())
        await session.flush()

        composers = {
            name: Composer(
                name=name, birth_year=birth, death_year=death, nationality=nation, era_id=eras[era].id
            )
            for name, birth, death, nation, era in COMPOSERS
        }
        session.add_all(composers.values())
        await session.flush()

        load_factors = {name: float(technique.load_factor) for name, technique in techniques.items()}
        for title, composer, catalog, key, genre, difficulty, duration, links in PIECES:
            piece = Piece(
                title=title,
                composer_id=composers[composer].id,
                genre_id=genres[genre].id,
                catalog_number=catalog,
                key_signature=key,
                difficulty_score=scale100(difficulty),
                mechanical_load=compute_mechanical_load(links, load_factors),
                duration_sec=duration,
            )
            session.add(piece)
            await session.flush()
            for technique_name, weight in links:
                session.add(
                    PieceTechnique(piece_id=piece.id, technique_id=techniques[technique_name].id, weight=weight)
                )

        by_title: dict[str, Piece] = {}
        for title, composer, catalog, key, genre, difficulty, movements in MOVEMENT_WORKS:
            all_links = [link for _, _, _, _, links in movements for link in links]
            parent = Piece(
                title=title,
                composer_id=composers[composer].id,
                genre_id=genres[genre].id,
                catalog_number=catalog,
                key_signature=key,
                difficulty_score=scale100(difficulty),
                mechanical_load=compute_mechanical_load(all_links, load_factors),
            )
            session.add(parent)
            await session.flush()
            for mv_title, number, mv_difficulty, duration, links in movements:
                movement = Piece(
                    title=f"{title}, {mv_title}",
                    composer_id=composers[composer].id,
                    genre_id=genres[genre].id,
                    catalog_number=catalog,
                    key_signature=key,
                    difficulty_score=scale100(mv_difficulty),
                    mechanical_load=compute_mechanical_load(links, load_factors),
                    duration_sec=duration,
                    parent_piece_id=parent.id,
                    movement_number=number,
                )
                session.add(movement)
                await session.flush()
                for technique_name, weight in links:
                    session.add(
                        PieceTechnique(
                            piece_id=movement.id,
                            technique_id=techniques[technique_name].id,
                            weight=weight,
                        )
                    )

        catalog_rows = await session.execute(select(Piece))
        for piece in catalog_rows.scalars().all():
            by_title[piece.title] = piece
        for title, octave, stretch, chords, nps, index in LOAD_PROFILES:
            piece = by_title.get(title)
            if piece is None:
                continue
            session.add(
                PieceLoadProfile(
                    piece_id=piece.id,
                    octave_density=octave,
                    max_stretch_semitones=stretch,
                    repeated_chord_density=chords,
                    notes_per_second_peak=nps,
                    load_index=index,
                )
            )

        print(
            f"seeded {len(ERAS)} eras, {len(GENRES)} genres, "
            f"{len(TECHNIQUES)} techniques, {len(COMPOSERS)} composers, "
            f"{len(PIECES)} pieces plus {len(MOVEMENT_WORKS)} multi-movement work(s), "
            f"{len(LOAD_PROFILES)} load profiles"
        )


async def main() -> None:
    await seed()
    await seed_catalog_detail()
    await seed_progression()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
