from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from app.services.work_titles import match_text

LADDER_VERSION = "reference-ladder-1"

T3 = "Double thirds"
T6 = "Double sixths"
BO = "Broken octaves"
OC = "Blocked octaves"
LP = "Wide leaps"
RC = "Repeated chords"
SC = "Rapid scales"
AR = "Arpeggio figuration"
RN = "Repeated notes"
TR = "Trills"
ST = "Tenth stretches"
P32 = "Three against two"
P43 = "Four against three"
MEL = "Melody over accompaniment"
INV = "Inner voice projection"
PED = "Half pedalling"
END = "Sustained endurance"


@dataclass(frozen=True)
class Reference:
    composer: str
    alternatives: tuple[tuple[str, ...], ...]
    difficulty: float
    techniques: tuple[tuple[str, float], ...]
    title: Optional[str] = None
    key: Optional[str] = None
    year: Optional[int] = None
    history: Optional[str] = None
    fact: Optional[str] = None

    @property
    def score(self) -> Decimal:
        return Decimal(str(round(self.difficulty, 1)))


def _phrase(text: str) -> str:
    return match_text(text).strip()


def ref(composer: str, match, difficulty: float, techniques, **extra) -> Reference:
    alternatives = tuple(
        tuple(_phrase(part) for part in ((alt,) if isinstance(alt, str) else alt)) for alt in match
    )
    return Reference(_phrase(composer), alternatives, float(difficulty), tuple(techniques), **extra)


TRANSCENDENTAL_HISTORY = (
    "Liszt reworked these studies three times: as a teenage set of exercises in 1826, as the fearsome "
    "Grandes études of 1837, and in their final, more playable form, published in 1852 and dedicated to "
    "his teacher Carl Czerny."
)

TRANSCENDENTAL = [
    (1, "Preludio", "C major", 60, [(AR, 0.8), (SC, 0.7), (OC, 0.5)], None),
    (2, "Molto vivace", "A minor", 88, [(LP, 0.9), (RN, 0.7), (OC, 0.7)], None),
    (3, "Paysage", "F major", 62, [(MEL, 0.8), (INV, 0.7), (PED, 0.6)], None),
    (4, "Mazeppa", "D minor", 95, [(T3, 0.9), (OC, 0.9), (END, 0.9), (LP, 0.7)],
     "It follows Victor Hugo's poem about Mazeppa, tied to a wild horse and carried across the steppe; Liszt later turned the same music into a symphonic poem."),
    (5, "Feux follets", "B-flat major", 96, [(T3, 0.9), (LP, 0.7), (SC, 0.7), (TR, 0.5)],
     "The title means will-o'-the-wisps. The difficulty is in feather-light double notes, not power."),
    (6, "Vision", "G minor", 84, [(AR, 0.9), (OC, 0.7), (MEL, 0.6)], None),
    (7, "Eroica", "E-flat major", 82, [(OC, 0.9), (RC, 0.7), (END, 0.6)], None),
    (8, "Wilde Jagd", "C minor", 92, [(OC, 0.9), (LP, 0.9), (RC, 0.7), (END, 0.8)],
     "Wilde Jagd means the Wild Hunt, the ghostly hunting party of European folklore."),
    (9, "Ricordanza", "A-flat major", 82, [(MEL, 0.9), (AR, 0.8), (TR, 0.5)], None),
    (10, "Allegro agitato molto", "F minor", 92, [(OC, 0.9), (LP, 0.8), (END, 0.9)], None),
    (11, "Harmonies du soir", "D-flat major", 84, [(RC, 0.9), (LP, 0.8), (OC, 0.8), (PED, 0.7), (MEL, 0.6)],
     "The title means evening harmonies. It grows from quiet, bell-like chords to a climax that fills the whole keyboard, then fades back to stillness."),
    (12, "Chasse-neige", "B-flat minor", 88, [(TR, 0.9), (INV, 0.8), (END, 0.9), (SC, 0.6)],
     "Chasse-neige means snow-whirl: tremolos pile up into a blizzard around a slow melody."),
]

ROMANS = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"]

CHOPIN_ETUDES = [
    (10, 1, "C major", 90, [(AR, 1.0), (ST, 0.8), (END, 0.6)], None),
    (10, 2, "A minor", 90, [(SC, 0.9), (INV, 0.8), (END, 0.6)], None),
    (10, 3, "E major", 60, [(MEL, 0.9), (INV, 0.7), (T6, 0.5)], "tristesse"),
    (10, 4, "C-sharp minor", 85, [(SC, 0.9), (AR, 0.8), (END, 0.8)], None),
    (10, 5, "G-flat major", 75, [(LP, 0.8), (SC, 0.7)], "black key"),
    (10, 6, "E-flat minor", 52, [(INV, 0.9), (MEL, 0.7)], None),
    (10, 7, "C major", 82, [(RN, 0.9), (T6, 0.6), (END, 0.6)], "toccata"),
    (10, 8, "F major", 78, [(AR, 0.9), (SC, 0.7)], None),
    (10, 9, "F minor", 65, [(ST, 0.8), (MEL, 0.7)], None),
    (10, 10, "A-flat major", 80, [(T6, 0.8), (LP, 0.7)], None),
    (10, 11, "E-flat major", 80, [(ST, 1.0), (AR, 0.7)], None),
    (10, 12, "C minor", 66, [(SC, 0.9), (END, 0.7), (AR, 0.6)], "revolutionary"),
    (25, 1, "A-flat major", 68, [(AR, 0.9), (MEL, 0.8), (INV, 0.6)], "aeolian harp"),
    (25, 2, "F minor", 70, [(SC, 0.8), (P32, 0.8)], "the bees"),
    (25, 3, "F major", 74, [(LP, 0.7), (INV, 0.7)], "the horseman"),
    (25, 4, "A minor", 72, [(LP, 0.9), (RC, 0.6)], None),
    (25, 5, "E minor", 70, [(INV, 0.9), (MEL, 0.7)], None),
    (25, 6, "G-sharp minor", 93, [(T3, 1.0), (TR, 0.6), (END, 0.5)], None),
    (25, 7, "C-sharp minor", 55, [(MEL, 0.9), (INV, 0.7)], "cello"),
    (25, 8, "D-flat major", 88, [(T6, 1.0), (END, 0.6)], None),
    (25, 9, "G-flat major", 65, [(BO, 0.7), (LP, 0.6)], "butterfly"),
    (25, 10, "B minor", 90, [(OC, 1.0), (END, 0.9)], None),
    (25, 11, "A minor", 91, [(SC, 0.9), (END, 0.8), (LP, 0.5)], "winter wind"),
    (25, 12, "C minor", 80, [(AR, 1.0), (END, 0.8)], "ocean"),
]


def _transcendental() -> list[Reference]:
    entries = []
    for number, name, key, difficulty, techniques, fact in TRANSCENDENTAL:
        match = [("s 139", f"no {number}"), ("s 139", ROMANS[number - 1]), ("transcendante", f"no {number}"),
                 ("transcendental", f"no {number}")]
        if name[0].isupper() and name not in {"Molto vivace", "Allegro agitato molto"}:
            match.append((name,))
        entries.append(
            ref("liszt", match, difficulty, techniques,
                title=f"Transcendental Étude No. {number}, {name}" if name not in {"Molto vivace", "Allegro agitato molto"} else f"Transcendental Étude No. {number} in {key}",
                key=key, year=1852, history=TRANSCENDENTAL_HISTORY, fact=fact)
        )
    return entries


def _chopin_etudes() -> list[Reference]:
    entries = []
    for opus, number, key, difficulty, techniques, nickname in CHOPIN_ETUDES:
        match = [(f"op {opus} no {number}",), (f"op {opus}", ROMANS[number - 1], "etude")]
        if nickname:
            match.append(("etude", nickname))
        entries.append(ref("chopin", match, difficulty, techniques, key=key))
    return entries


LADDER: list[Reference] = [
    ref("balakirev", ["islamey", "op 18"], 98, [(RN, 0.9), (LP, 0.9), (OC, 0.8), (T3, 0.7), (END, 0.9)],
        title="Islamey, Oriental Fantasy", year=1869,
        history="Balakirev wrote Islamey in 1869 after travelling in the Caucasus, building it on a Kabardian dance tune he heard there and a Tatar love song.",
        fact="Nikolai Rubinstein gave the premiere. Ravel later said he wanted Scarbo to be harder than Islamey."),
    ref("ravel", [("gaspard", "scarbo"), ("scarbo",)], 98, [(RN, 0.9), (LP, 0.8), (T3, 0.6), (END, 0.8)],
        title="Gaspard de la nuit: III. Scarbo", year=1908,
        history="Gaspard de la nuit sets three prose poems by Aloysius Bertrand. Scarbo is a goblin who darts, spins and vanishes around a sleeper's room.",
        fact="Ravel set out to write something harder than Balakirev's Islamey."),
    ref("ravel", [("gaspard", "ondine"), ("ondine",)], 88, [(RC, 0.8), (AR, 0.8), (MEL, 0.8), (PED, 0.7)],
        title="Gaspard de la nuit: I. Ondine", year=1908),
    ref("ravel", [("gaspard", "gibet"), ("le gibet",)], 78, [(RN, 0.8), (INV, 0.9), (PED, 0.7)],
        title="Gaspard de la nuit: II. Le Gibet", year=1908),
    ref("ravel", ["gaspard de la nuit", "m 55"], 98, [(RN, 0.9), (LP, 0.8), (AR, 0.8), (END, 0.9)], year=1908),
    ref("ravel", ["jeux d eau", "m 30"], 80, [(AR, 0.9), (T3, 0.6), (LP, 0.6)], year=1901),
    ref("ravel", [("tombeau de couperin", "toccata")], 90, [(RN, 0.9), (END, 0.8), (LP, 0.6)]),
    ref("ravel", ["pavane pour une infante", "m 19"], 45, [(MEL, 0.8), (PED, 0.6)], year=1899),
    ref("ravel", ["sonatine", "m 40"], 58, [(AR, 0.7), (MEL, 0.6)]),
    ref("ravel", ["alborada", ("miroirs", "iv")], 90, [(RN, 0.9), (T3, 0.7), (LP, 0.6)]),
    *_transcendental(),
    ref("liszt", ["campanella", "s 141 no 3"], 90, [(LP, 0.9), (RN, 0.8), (TR, 0.6)],
        title="Grandes études de Paganini No. 3, La Campanella", key="G-sharp minor", year=1851,
        history="The third of Liszt's Paganini studies, published in 1851, turns the bell-like rondo of Paganini's Second Violin Concerto into a study in leaps."),
    ref("liszt", ["hungarian rhapsody no 2", "s 244 no 2", "rhapsodie hongroise no 2", ("ungarische rhapsodie", "no 2")], 82,
        [(OC, 0.9), (RN, 0.6), (LP, 0.7)], key="C-sharp minor", year=1847,
        fact="It became cartoon royalty: Bugs Bunny played it in Rhapsody Rabbit and Tom played it in The Cat Concerto."),
    ref("liszt", ["liebestraum no 3", "s 541 no 3", ("liebestraume", "no 3"), "o lieb"], 58, [(MEL, 0.8), (LP, 0.6), (AR, 0.7)],
        title="Liebestraum No. 3", key="A-flat major", year=1850,
        fact="It began life as a song, O lieb, so lang du lieben kannst, on a poem by Ferdinand Freiligrath."),
    ref("liszt", ["mephisto waltz no 1", "mephisto walzer no 1", "s 514", "tanz in der dorfschenke"], 93,
        [(LP, 0.9), (OC, 0.8), (RC, 0.6), (END, 0.8)], title="Mephisto Waltz No. 1",
        history="Liszt took the scene from Nikolaus Lenau's Faust in which Mephistopheles grabs a fiddle at a village inn and whips the dancers into a frenzy."),
    ref("liszt", ["sonata in b minor", "s 178", ("sonate", "h moll"), ("sonate", "b minor")], 95,
        [(OC, 0.9), (LP, 0.8), (END, 1.0), (INV, 0.6)], title="Piano Sonata in B minor", key="B minor", year=1853,
        fact="Liszt dedicated it to Robert Schumann, who had dedicated his Fantasie in C to Liszt."),
    ref("liszt", ["un sospiro", "s 144 no 3"], 72, [(AR, 0.9), (MEL, 0.9), (LP, 0.5)], key="D-flat major"),
    ref("liszt", [("consolation", "no 3"), "s 172 no 3"], 38, [(MEL, 0.8), (PED, 0.6)], key="D-flat major"),
    ref("liszt", ["don juan", "s 418"], 98, [(OC, 0.9), (LP, 0.9), (T3, 0.7), (END, 1.0)]),
    ref("liszt", ["rhapsodie espagnole", "s 254"], 92, [(OC, 0.9), (LP, 0.8), (RN, 0.7)]),
    ref("liszt", ["apres une lecture du dante", "dante sonata"], 94, [(OC, 1.0), (RC, 0.8), (END, 0.9)]),
    ref("liszt", ["gnomenreigen", "s 145 no 2"], 85, [(RN, 0.8), (LP, 0.7)]),
    ref("liszt", ["waldesrauschen", "s 145 no 1"], 70, [(AR, 0.8), (MEL, 0.8)]),
    *_chopin_etudes(),
    ref("chopin", [("ballade", "op 23"), "ballade no 1"], 70, [(LP, 0.7), (OC, 0.6), (END, 0.8), (SC, 0.7)], key="G minor"),
    ref("chopin", [("ballade", "op 38"), "ballade no 2"], 76, [(OC, 0.7), (LP, 0.7), (INV, 0.6)], key="F major"),
    ref("chopin", [("ballade", "op 47"), "ballade no 3"], 68, [(LP, 0.7), (MEL, 0.7)], key="A-flat major"),
    ref("chopin", [("ballade", "op 52"), "ballade no 4"], 85, [(INV, 0.9), (P32, 0.6), (END, 0.9), (SC, 0.7)], key="F minor"),
    ref("chopin", [("scherzo", "op 20"), "scherzo no 1"], 80, [(LP, 0.8), (END, 0.8)], key="B minor"),
    ref("chopin", [("scherzo", "op 31"), "scherzo no 2"], 74, [(LP, 0.8), (AR, 0.7)], key="B-flat minor"),
    ref("chopin", [("scherzo", "op 39"), "scherzo no 3"], 78, [(OC, 0.8), (AR, 0.7)], key="C-sharp minor"),
    ref("chopin", [("scherzo", "op 54"), "scherzo no 4"], 82, [(RN, 0.7), (LP, 0.7), (END, 0.8)], key="E major"),
    ref("chopin", ["fantaisie impromptu", "op 66"], 62, [(P43, 0.9), (SC, 0.7), (AR, 0.6)], key="C-sharp minor", year=1834,
        fact="Chopin never published it. Julian Fontana brought it out in 1855, six years after Chopin's death."),
    ref("chopin", [("polonaise", "op 53"), "heroic"], 80, [(OC, 0.9), (RC, 0.7), (LP, 0.6)], key="A-flat major"),
    ref("chopin", [("polonaise", "op 44")], 82, [(OC, 0.8), (RC, 0.7), (END, 0.7)], key="F-sharp minor"),
    ref("chopin", [("polonaise", "op 40 no 1"), ("polonaise", "military")], 55, [(RC, 0.8), (OC, 0.6)], key="A major"),
    ref("chopin", ["andante spianato", ("grande polonaise", "op 22")], 82, [(SC, 0.8), (LP, 0.7), (END, 0.7)], key="E-flat major"),
    ref("chopin", ["op 9 no 2", ("nocturne", "e flat major", "op 9")], 46, [(MEL, 0.9), (PED, 0.6), (LP, 0.4)], key="E-flat major"),
    ref("chopin", ["op 48 no 1"], 68, [(RC, 0.7), (OC, 0.6), (MEL, 0.8)], key="C minor"),
    ref("chopin", ["op 27 no 2"], 58, [(MEL, 0.9), (AR, 0.6)], key="D-flat major"),
    ref("chopin", [("nocturne", "c sharp minor", "posth"), "lento con gran espressione", ("nocturne", "b 49")], 38,
        [(MEL, 0.8), (SC, 0.4)], key="C-sharp minor"),
    ref("chopin", ["op 64 no 1", "minute waltz", "valse minute"], 45, [(SC, 0.8), (MEL, 0.5)], key="D-flat major",
        fact="Minute here means small, not sixty seconds: it takes most pianists closer to two minutes."),
    ref("chopin", ["op 64 no 2"], 42, [(SC, 0.6), (MEL, 0.7)], key="C-sharp minor"),
    ref("chopin", ["op 69 no 1"], 35, [(MEL, 0.8)], key="A-flat major"),
    ref("chopin", ["op 18", "grande valse brillante"], 50, [(RN, 0.6), (LP, 0.6)], key="E-flat major"),
    ref("chopin", ["op 34 no 1"], 55, [(LP, 0.7), (SC, 0.6)], key="A-flat major"),
    ref("chopin", [("waltz", "op 42"), ("valse", "op 42")], 60, [(P32, 0.7), (SC, 0.6)], key="A-flat major"),
    ref("chopin", ["op 28 no 4"], 15, [(MEL, 0.7), (INV, 0.5)], key="E minor"),
    ref("chopin", ["op 28 no 7"], 10, [(MEL, 0.6)], key="A major"),
    ref("chopin", ["op 28 no 15", "raindrop"], 38, [(RN, 0.6), (MEL, 0.7)], key="D-flat major"),
    ref("chopin", ["op 28 no 16"], 85, [(SC, 0.9), (END, 0.7)], key="B-flat minor"),
    ref("chopin", ["op 28 no 20"], 25, [(RC, 0.6)], key="C minor"),
    ref("chopin", ["op 28 no 24"], 78, [(AR, 0.8), (SC, 0.7), (LP, 0.6)], key="D minor"),
    ref("chopin", [("sonata", "op 35"), "funeral march"], 82, [(OC, 0.7), (LP, 0.7), (END, 0.8)], key="B-flat minor"),
    ref("chopin", [("sonata", "op 58")], 86, [(SC, 0.8), (END, 0.9), (INV, 0.6)], key="B minor"),
    ref("chopin", ["barcarolle", "op 60"], 80, [(T3, 0.7), (T6, 0.6), (INV, 0.7)], key="F-sharp major"),
    ref("chopin", ["berceuse", "op 57"], 62, [(SC, 0.7), (TR, 0.6)], key="D-flat major"),
    ref("chopin", [("concerto", "op 11")], 88, [(SC, 0.8), (AR, 0.8), (END, 0.9)], key="E minor"),
    ref("chopin", [("concerto", "op 21")], 85, [(SC, 0.8), (AR, 0.7), (END, 0.8)], key="F minor"),
    ref("beethoven", ["fur elise", "woo 59"], 30, [(AR, 0.5), (RN, 0.4)], key="A minor", year=1810),
    ref("beethoven", [("op 27 no 2", "iii"), ("moonlight", "iii"), ("op 27 no 2", "presto agitato")], 68,
        [(AR, 0.9), (RC, 0.6), (END, 0.7)], key="C-sharp minor", year=1801),
    ref("beethoven", [("op 27 no 2", "ii"), ("moonlight", "ii"), ("op 27 no 2", "allegretto")], 38, [(RC, 0.5), (MEL, 0.5)], year=1801),
    ref("beethoven", [("op 27 no 2", "i"), ("moonlight", "i"), ("op 27 no 2", "adagio sostenuto")], 32,
        [(MEL, 0.7), (AR, 0.6), (PED, 0.5)], key="C-sharp minor", year=1801),
    ref("beethoven", ["op 27 no 2", "moonlight"], 68, [(AR, 0.9), (MEL, 0.7), (END, 0.7)], key="C-sharp minor", year=1801),
    ref("beethoven", [("op 13", "i"), ("pathetique", "i"), ("op 13", "grave")], 58, [(RC, 0.7), (OC, 0.6), (SC, 0.6)], key="C minor"),
    ref("beethoven", [("op 13", "ii"), ("pathetique", "ii"), ("op 13", "adagio cantabile")], 35, [(MEL, 0.9), (INV, 0.6)], key="A-flat major"),
    ref("beethoven", [("op 13", "iii"), ("pathetique", "iii"), ("op 13", "rondo")], 50, [(SC, 0.7), (LP, 0.5)], key="C minor"),
    ref("beethoven", ["op 13", "pathetique"], 58, [(RC, 0.7), (BO, 0.6), (SC, 0.6)], key="C minor", year=1798),
    ref("beethoven", ["op 53", "waldstein"], 82, [(RC, 0.8), (SC, 0.7), (TR, 0.7), (END, 0.8)], key="C major", year=1804),
    ref("beethoven", ["op 57", "appassionata"], 86, [(OC, 0.8), (RC, 0.8), (END, 0.9)], key="F minor"),
    ref("beethoven", ["op 106", "hammerklavier"], 97, [(END, 1.0), (LP, 0.8), (TR, 0.7), (INV, 0.8)], key="B-flat major", year=1818,
        fact="Beethoven's own metronome mark for the first movement is so fast that few pianists take it at his tempo."),
    ref("beethoven", ["op 111"], 88, [(TR, 0.9), (END, 0.8), (INV, 0.7)], key="C minor"),
    ref("beethoven", [("op 31 no 2", "iii"), ("tempest", "iii")], 60, [(AR, 0.8), (END, 0.6)], key="D minor"),
    ref("beethoven", ["op 31 no 2", "tempest"], 64, [(AR, 0.8), (MEL, 0.6), (END, 0.6)], key="D minor"),
    ref("beethoven", [("concerto", "op 73"), "emperor"], 85, [(SC, 0.8), (OC, 0.7), (TR, 0.7)], key="E-flat major"),
    ref("mozart", [("k 545", "i")], 30, [(SC, 0.7), (MEL, 0.5)], key="C major", year=1788),
    ref("mozart", ["k 545", "sonata facile"], 32, [(SC, 0.7), (MEL, 0.5)], key="C major", year=1788),
    ref("mozart", ["alla turca", ("k 331", "iii")], 42, [(SC, 0.6), (OC, 0.5)], key="A minor"),
    ref("mozart", ["k 331", "k 300i"], 45, [(SC, 0.6), (MEL, 0.6)], key="A major"),
    ref("mozart", ["k 397", "k 385g"], 38, [(SC, 0.6), (MEL, 0.6)], key="D minor"),
    ref("mozart", ["k 310", "k 300d"], 60, [(SC, 0.7), (RC, 0.6)], key="A minor"),
    ref("mozart", ["k 265", "ah vous dirai je maman"], 35, [(SC, 0.6), (TR, 0.4)], key="C major"),
    ref("mozart", ["k 467"], 72, [(SC, 0.8), (END, 0.6)], key="C major"),
    ref("bach", ["bwv 772", ("invention", "no 1")], 30, [(SC, 0.4), (INV, 0.6)], key="C major"),
    ref("bach", ["bwv 846"], 24, [(AR, 0.8)], key="C major"),
    ref("bach", ["bwv 971", "italian concerto", "italienisches konzert"], 62, [(SC, 0.7), (INV, 0.6)], key="F major", year=1735),
    ref("bach", ["bwv 988", "goldberg"], 88, [(LP, 0.8), (INV, 0.8), (END, 0.9), (TR, 0.6)], key="G major", year=1741),
    ref("bach", ["bwv 903", "chromatic fantasia"], 78, [(SC, 0.8), (AR, 0.8), (INV, 0.7)], key="D minor"),
    ref("bach", ["bwv 826"], 68, [(SC, 0.7), (INV, 0.7)], key="C minor"),
    ref("debussy", ["clair de lune", ("suite bergamasque", "iii"), "l 75 no 3", "l 82 no 3"], 48,
        [(PED, 0.8), (MEL, 0.7), (P32, 0.5)], title="Clair de lune", key="D-flat major",
        fact="The title comes from a Paul Verlaine poem. Debussy began the Suite bergamasque around 1890 but only published it in 1905."),
    ref("debussy", ["arabesque no 1", "l 66 no 1", "premiere arabesque", "l 74 no 1"], 40, [(P32, 0.8), (AR, 0.6)], key="E major"),
    ref("debussy", ["golliwogg", "golliwog"], 45, [(LP, 0.6), (RC, 0.5)]),
    ref("debussy", ["reflets dans l eau"], 72, [(AR, 0.8), (PED, 0.8), (INV, 0.6)]),
    ref("debussy", ["isle joyeuse"], 85, [(TR, 0.7), (AR, 0.8), (END, 0.8)], year=1904),
    ref("debussy", ["feux d artifice"], 88, [(RN, 0.7), (T3, 0.6), (LP, 0.8)]),
    ref("debussy", ["jardins sous la pluie"], 72, [(RN, 0.8), (AR, 0.7)]),
    ref("debussy", ["fille aux cheveux de lin"], 30, [(MEL, 0.7), (PED, 0.6)]),
    ref("debussy", ["gradus ad parnassum"], 50, [(AR, 0.8)]),
    ref("debussy", [("pour le piano", "toccata")], 82, [(RN, 0.8), (END, 0.7)]),
    ref("debussy", ["cathedrale engloutie"], 55, [(RC, 0.7), (PED, 0.9), (OC, 0.5)]),
    ref("rachmaninoff", ["op 3 no 2", ("prelude", "c sharp minor")], 55, [(RC, 0.9), (ST, 0.7), (END, 0.6)], key="C-sharp minor", year=1892,
        fact="He wrote it at nineteen. Audiences demanded it at so many recitals that he came to call it simply It."),
    ref("rachmaninoff", ["op 23 no 5"], 70, [(RC, 0.8), (OC, 0.7), (ST, 0.6)], key="G minor", year=1901),
    ref("rachmaninoff", ["op 32 no 12"], 62, [(RN, 0.7), (MEL, 0.8)], key="G-sharp minor"),
    ref("rachmaninoff", ["op 39 no 5"], 82, [(RC, 0.9), (ST, 0.8), (END, 0.7)], key="E-flat minor"),
    ref("rachmaninoff", ["op 39 no 6"], 84, [(RN, 0.8), (LP, 0.8)], key="A minor"),
    ref("rachmaninoff", [("sonata", "op 36")], 93, [(RC, 0.9), (OC, 0.8), (END, 1.0)], key="B-flat minor"),
    ref("rachmaninoff", [("op 18", "moderato"), ("op 18", "i")], 88, [(OC, 0.8), (ST, 0.8), (END, 0.9)], key="C minor"),
    ref("rachmaninoff", [("op 18", "adagio sostenuto"), ("op 18", "ii")], 72, [(MEL, 0.8), (P43, 0.6), (PED, 0.6)]),
    ref("rachmaninoff", [("op 18", "allegro scherzando"), ("op 18", "iii")], 90, [(SC, 0.8), (OC, 0.7), (END, 0.8)]),
    ref("rachmaninoff", ["op 18", "piano concerto no 2"], 88, [(OC, 0.8), (ST, 0.8), (END, 0.9)], key="C minor", year=1901),
    ref("rachmaninoff", ["op 30", "piano concerto no 3"], 97, [(OC, 0.9), (RC, 0.9), (END, 1.0), (ST, 0.8)], key="D minor", year=1909),
    ref("rachmaninoff", ["op 43", "rhapsody on a theme of paganini"], 92, [(OC, 0.8), (LP, 0.8), (END, 0.8)], year=1934),
    ref("schumann", ["toccata", "op 7"], 92, [(T3, 0.8), (BO, 0.8), (END, 1.0)], key="C major"),
    ref("schumann", ["traumerei", "op 15 no 7"], 25, [(MEL, 0.8), (INV, 0.7)], key="F major"),
    ref("schumann", ["kinderszenen", "op 15"], 35, [(MEL, 0.7), (INV, 0.6)]),
    ref("schumann", [("fantasie", "op 17"), "op 17"], 90, [(LP, 0.9), (END, 0.9), (INV, 0.7)], key="C major"),
    ref("schumann", ["carnaval", "op 9"], 82, [(OC, 0.7), (LP, 0.8), (END, 0.7)]),
    ref("schumann", ["kreisleriana", "op 16"], 86, [(LP, 0.8), (INV, 0.8), (END, 0.8)]),
    ref("schumann", ["etudes symphoniques", "symphonic etudes", "op 13"], 90, [(OC, 0.8), (LP, 0.8), (END, 0.9)]),
    ref("schumann", ["arabeske", "op 18"], 48, [(MEL, 0.7), (INV, 0.6)], key="C major"),
    ref("schumann", ["papillons", "op 2"], 55, [(LP, 0.7), (RC, 0.5)]),
    ref("schumann", [("concerto", "op 54")], 85, [(OC, 0.7), (LP, 0.7), (END, 0.8)], key="A minor"),
    ref("schumann", ["wilder reiter", "wild rider", "op 68 no 8"], 10, [(MEL, 0.5)], key="A minor"),
    ref("schumann", ["album fur die jugend", "op 68"], 20, [(MEL, 0.6)]),
    ref("brahms", ["op 79 no 2"], 62, [(P32, 0.8), (OC, 0.5), (INV, 0.6)], key="G minor"),
    ref("brahms", ["op 118 no 2"], 52, [(INV, 0.9), (MEL, 0.7), (PED, 0.6), (P32, 0.4)], key="A major"),
    ref("brahms", ["op 117 no 1"], 42, [(INV, 0.8), (MEL, 0.7)], key="E-flat major"),
    ref("brahms", ["op 35", ("variations", "paganini")], 95, [(OC, 0.9), (T6, 0.8), (LP, 0.9), (END, 0.8)], key="A minor"),
    ref("brahms", ["op 24", ("variations", "handel")], 88, [(OC, 0.8), (T3, 0.6), (END, 0.9)], key="B-flat major"),
    ref("brahms", [("concerto", "op 15")], 94, [(OC, 0.9), (TR, 0.8), (END, 1.0)], key="D minor"),
    ref("brahms", [("concerto", "op 83")], 96, [(OC, 0.9), (LP, 0.8), (END, 1.0)], key="B-flat major"),
    ref("brahms", ["op 39 no 15"], 20, [(MEL, 0.6)], key="A-flat major"),
    ref("brahms", [("ballade", "op 10 no 1"), "edward"], 50, [(RC, 0.7), (INV, 0.6)], key="D minor"),
    ref("schubert", ["d 899 no 2", "op 90 no 2"], 60, [(SC, 0.8), (LP, 0.6)], key="E-flat major"),
    ref("schubert", ["d 899 no 3", "op 90 no 3"], 45, [(MEL, 0.9), (INV, 0.6)], key="G-flat major"),
    ref("schubert", ["d 899 no 4", "op 90 no 4"], 58, [(AR, 0.8), (MEL, 0.7)], key="A-flat major"),
    ref("schubert", ["d 935 no 3", "op 142 no 3"], 55, [(SC, 0.6), (MEL, 0.6)], key="B-flat major"),
    ref("schubert", ["d 760", "wanderer"], 90, [(RC, 0.9), (OC, 0.8), (END, 0.9)], key="C major"),
    ref("schubert", ["d 780 no 3"], 20, [(MEL, 0.6)], key="F minor"),
    ref("schubert", ["d 960"], 78, [(TR, 0.6), (INV, 0.7), (END, 0.8)], key="B-flat major"),
    ref("mendelssohn", ["rondo capriccioso", "op 14"], 70, [(RN, 0.7), (SC, 0.7)], key="E major"),
    ref("mendelssohn", ["variations serieuses", "op 54"], 80, [(OC, 0.7), (RN, 0.6), (END, 0.8)], key="D minor"),
    ref("mendelssohn", ["op 67 no 4", "spinning song", "spinnerlied"], 65, [(RN, 0.8), (SC, 0.6)], key="C major"),
    ref("grieg", ["op 65 no 6", "troldhaugen"], 58, [(RC, 0.7), (OC, 0.6)], key="D major"),
    ref("grieg", [("concerto", "op 16"), "op 16"], 88, [(OC, 0.9), (RC, 0.7), (END, 0.8)], key="A minor", year=1868),
    ref("grieg", ["op 12 no 1", "arietta"], 18, [(MEL, 0.7)], key="E-flat major"),
    ref("grieg", ["op 54 no 3", "march of the trolls", "trolltog"], 45, [(RC, 0.6), (OC, 0.5)]),
    ref("grieg", ["op 43 no 1", "butterfly", "sommerfugl", "papillon"], 50, [(AR, 0.7), (SC, 0.6)]),
    ref("scriabin", ["op 8 no 12"], 80, [(OC, 0.8), (LP, 0.8), (END, 0.7)], key="D-sharp minor"),
    ref("scriabin", ["op 2 no 1"], 45, [(MEL, 0.7), (INV, 0.6)], key="C-sharp minor"),
    ref("scriabin", ["op 42 no 5"], 85, [(ST, 0.8), (LP, 0.8), (P32, 0.7)], key="C-sharp minor"),
    ref("scriabin", ["op 53", ("sonata", "no 5")], 92, [(LP, 0.9), (RC, 0.8), (END, 0.8)]),
    ref("scriabin", ["vers la flamme", "op 72"], 85, [(RC, 0.9), (TR, 0.7), (END, 0.8)]),
    ref("prokofiev", ["toccata", "op 11"], 92, [(RN, 0.9), (LP, 0.8), (END, 0.9)], key="D minor", year=1912),
    ref("prokofiev", ["op 83", ("sonata", "no 7")], 93, [(RC, 0.9), (OC, 0.8), (END, 0.9)], key="B-flat major", year=1942),
    ref("prokofiev", [("concerto", "op 16"), ("concerto", "no 2")], 97, [(LP, 0.9), (OC, 0.9), (END, 1.0)], key="G minor"),
    ref("prokofiev", [("concerto", "op 26"), ("concerto", "no 3")], 94, [(SC, 0.8), (RC, 0.8), (END, 0.9)], key="C major"),
    ref("tchaikovsky", ["pas de deux"], 88, [(T6, 0.9), (OC, 0.7), (MEL, 0.7), (END, 0.6)]),
    ref("tchaikovsky", [("concerto", "op 23"), ("concerto", "no 1")], 93, [(OC, 1.0), (RC, 0.8), (END, 0.9)], key="B-flat minor", year=1875),
    ref("tchaikovsky", [("seasons", "june"), ("op 37a", "june"), ("op 37b", "june")], 40, [(MEL, 0.8)], key="G minor"),
    ref("tchaikovsky", ["dumka", "op 59"], 70, [(RC, 0.7), (OC, 0.6)], key="C minor"),
    ref("mussorgsky", ["pictures at an exhibition", "tableaux d une exposition", "bilder einer ausstellung"], 90,
        [(RC, 0.9), (OC, 0.8), (END, 0.9)], year=1874),
    ref("stravinsky", ["petrushka", "petrouchka", "petruschka"], 97, [(LP, 1.0), (RC, 0.8), (END, 0.9)], year=1921),
    ref("ligeti", ["escalier du diable"], 97, [(RC, 0.9), (END, 1.0), (LP, 0.7)]),
    ref("ligeti", ["desordre"], 85, [(SC, 0.8), (P43, 0.7)]),
    ref("alkan", ["festin d esope", "op 39 no 12"], 88, [(LP, 0.8), (OC, 0.8), (RN, 0.7)]),
    ref("alkan", ["concerto pour piano seul", "op 39 no 8", "op 39 no 9", "op 39 no 10"], 98, [(OC, 1.0), (LP, 0.9), (END, 1.0)]),
    ref("alkan", ["symphonie pour piano seul", "op 39 no 4", "op 39 no 5", "op 39 no 6", "op 39 no 7"], 95,
        [(OC, 0.9), (RC, 0.8), (END, 0.9)]),
    ref("godowsky", [("chopin",)], 99, [(INV, 1.0), (LP, 0.8), (END, 1.0), (P43, 0.7)]),
    ref("albeniz", ["iberia"], 94, [(LP, 0.9), (RC, 0.8), (INV, 0.7), (END, 0.9)]),
    ref("albeniz", ["asturias", "leyenda"], 55, [(RN, 0.8), (OC, 0.5)]),
    ref("granados", ["quejas", "maja y el ruisenor"], 70, [(INV, 0.8), (MEL, 0.8), (TR, 0.5)]),
    ref("gershwin", ["rhapsody in blue"], 80, [(OC, 0.8), (LP, 0.7), (RC, 0.7)], year=1924),
    ref("gershwin", ["three preludes", "3 preludes"], 50, [(LP, 0.6), (RC, 0.5)]),
    ref("joplin", ["maple leaf rag"], 45, [(LP, 0.8), (OC, 0.5)], year=1899),
    ref("joplin", ["entertainer"], 35, [(LP, 0.7)], year=1902),
    ref("satie", ["gymnopedie"], 12, [(MEL, 0.6), (LP, 0.4)], year=1888),
    ref("satie", ["gnossienne"], 15, [(MEL, 0.6)]),
    ref("clementi", ["op 36 no 1"], 15, [(SC, 0.5)], key="C major"),
    ref("clementi", ["op 36"], 20, [(SC, 0.6)]),
    ref("burgmuller", ["op 100"], 10, [(SC, 0.4)]),
    ref("kapustin", ["op 40 no 3", "toccatina"], 88, [(RC, 0.8), (LP, 0.8), (END, 0.8)]),
    ref("kapustin", ["op 40 no 1"], 85, [(LP, 0.8), (RC, 0.7)]),
    ref("haydn", ["hob xvi 52"], 65, [(SC, 0.7), (RC, 0.6)], key="E-flat major"),
    ref("scarlatti", ["k 141"], 72, [(RN, 0.9), (LP, 0.6)], key="D minor"),
    ref("scarlatti", ["k 380"], 50, [(TR, 0.6), (SC, 0.5)], key="E major"),
    ref("einaudi", ["nuvole bianche"], 25, [(AR, 0.6), (MEL, 0.6)]),
    ref("yiruma", ["river flows in you"], 20, [(AR, 0.6), (MEL, 0.6)]),
    ref("saint saens", [("concerto", "op 22")], 85, [(SC, 0.8), (TR, 0.6), (END, 0.7)], key="G minor"),
]


def lookup(title: Optional[str], composer_name: Optional[str], catalog_number: Optional[str] = None) -> Optional[Reference]:
    if not title or not composer_name:
        return None
    text = match_text(title, catalog_number)
    composer = match_text(composer_name)
    best: Optional[Reference] = None
    best_rank = (0, 0)
    for entry in LADDER:
        if f" {entry.composer} " not in composer:
            continue
        for alternative in entry.alternatives:
            if all(f" {phrase} " in text for phrase in alternative):
                rank = (len(alternative), sum(len(phrase) for phrase in alternative))
                if rank > best_rank:
                    best, best_rank = entry, rank
    return best


COMPOSER_BASELINE = {
    "bach": 45, "handel": 35, "scarlatti": 50, "haydn": 40, "mozart": 40, "clementi": 20, "beethoven": 55,
    "schubert": 50, "mendelssohn": 52, "chopin": 60, "schumann": 60, "liszt": 75, "brahms": 62, "grieg": 40,
    "tchaikovsky": 50, "mussorgsky": 60, "dvorak": 45, "franck": 60, "faure": 50, "saint saens": 62,
    "debussy": 52, "ravel": 68, "satie": 15, "scriabin": 65, "rachmaninoff": 72, "rachmaninov": 72,
    "prokofiev": 72, "shostakovich": 60, "stravinsky": 80, "bartok": 58, "poulenc": 50, "granados": 58,
    "albeniz": 65, "balakirev": 80, "alkan": 85, "godowsky": 90, "busoni": 82, "medtner": 75, "kapustin": 78,
    "ligeti": 85, "messiaen": 82, "gershwin": 55, "joplin": 40, "burgmuller": 10, "czerny": 30, "kabalevsky": 25,
    "einaudi": 22, "yiruma": 18, "tiersen": 25, "hisaishi": 35, "field": 40, "moszkowski": 70, "paderewski": 60,
}

FORM_ADJUSTMENTS = [
    (("transcendental", "transcendante", "execution transcendante"), 15),
    (("paraphrase", "reminiscences", "reminiscence", "concert etude", "etude de concert"), 12),
    (("concerto", "konzert"), 12),
    (("toccata",), 10),
    (("etude", "study", "studie"), 8),
    (("rhapsody", "rhapsodie", "rapsodie"), 8),
    (("polonaise", "scherzo"), 8),
    (("sonata", "sonate"), 5),
    (("variations", "variationen", "fantasie", "fantasia", "fantaisie", "ballade"), 5),
    (("sonatina", "sonatine"), -22),
    (("album", "for children", "pour les enfants", "kinder", "jugend", "little", "petite", "easy", "beginner", "first"), -20),
    (("minuet", "menuet", "musette", "gavotte"), -18),
    (("consolation", "romance", "song without words", "lied ohne worte", "lieder ohne worte", "arietta"), -12),
    (("prelude", "invention", "waltz", "valse", "mazurka", "nocturne"), -6),
]


def estimate_difficulty(title: Optional[str], composer_name: Optional[str]) -> Decimal:
    text = match_text(title)
    composer = match_text(composer_name)
    base = next((value for name, value in COMPOSER_BASELINE.items() if f" {name} " in composer), 50)
    adjustment = 0
    for words, delta in FORM_ADJUSTMENTS:
        if any(f" {_phrase(word)} " in text for word in words):
            adjustment += delta
    return Decimal(str(round(min(max(base + adjustment, 5), 94), 1)))


COMPOSER_TECHNIQUES = {
    "liszt": [(OC, 0.8), (LP, 0.8), (SC, 0.6)],
    "chopin": [(AR, 0.7), (MEL, 0.7), (SC, 0.5)],
    "bach": [(INV, 0.8), (SC, 0.5)],
    "handel": [(SC, 0.6), (TR, 0.5)],
    "scarlatti": [(RN, 0.6), (LP, 0.6), (SC, 0.5)],
    "mozart": [(SC, 0.6), (MEL, 0.5)],
    "haydn": [(SC, 0.6), (TR, 0.5)],
    "clementi": [(SC, 0.6)],
    "beethoven": [(SC, 0.6), (RC, 0.5), (END, 0.5)],
    "schubert": [(MEL, 0.7), (RC, 0.5)],
    "schumann": [(INV, 0.6), (LP, 0.6)],
    "mendelssohn": [(RN, 0.6), (MEL, 0.6)],
    "brahms": [(P32, 0.7), (INV, 0.7)],
    "debussy": [(PED, 0.8), (MEL, 0.5)],
    "ravel": [(AR, 0.7), (RN, 0.5), (PED, 0.6)],
    "rachmaninoff": [(RC, 0.7), (ST, 0.7), (OC, 0.6)],
    "rachmaninov": [(RC, 0.7), (ST, 0.7), (OC, 0.6)],
    "scriabin": [(LP, 0.7), (ST, 0.6)],
    "prokofiev": [(RN, 0.7), (LP, 0.7)],
    "balakirev": [(RN, 0.8), (LP, 0.8)],
    "alkan": [(RN, 0.8), (OC, 0.8)],
    "satie": [(MEL, 0.6), (LP, 0.4)],
    "grieg": [(MEL, 0.6), (RC, 0.5)],
    "tchaikovsky": [(MEL, 0.6), (OC, 0.6)],
    "joplin": [(LP, 0.7)],
    "gershwin": [(LP, 0.6), (RC, 0.5)],
}

FORM_TECHNIQUES = [
    (("nocturne", "romance", "song without words", "consolation", "lied"), [(MEL, 0.9), (PED, 0.6)]),
    (("waltz", "valse", "mazurka", "rag"), [(LP, 0.6)]),
    (("toccata",), [(RN, 0.8), (END, 0.8)]),
    (("etude", "study", "transcendental", "transcendante"), [(END, 0.7)]),
    (("octave", "octaves"), [(OC, 0.9)]),
    (("trill", "trille"), [(TR, 0.8)]),
    (("arpeggio", "arpeggi", "harp"), [(AR, 0.8)]),
    (("fugue", "fuga", "invention", "sinfonia"), [(INV, 0.8)]),
    (("berceuse", "lullaby", "wiegenlied"), [(MEL, 0.8)]),
    (("polonaise", "march", "marche"), [(RC, 0.7), (OC, 0.6)]),
    (("concerto",), [(END, 0.9), (SC, 0.7)]),
    (("harmonies", "cathedral", "cathedrale", "bells", "cloches"), [(RC, 0.8), (PED, 0.7)]),
]


def heuristic_techniques(title: Optional[str], composer_name: Optional[str]) -> list[tuple[str, float]]:
    text = match_text(title)
    composer = match_text(composer_name)
    chosen: dict[str, float] = {}
    for words, links in FORM_TECHNIQUES:
        if any(f" {_phrase(word)} " in text for word in words):
            for name, weight in links:
                chosen[name] = max(chosen.get(name, 0.0), weight)
    defaults = next((links for name, links in COMPOSER_TECHNIQUES.items() if f" {name} " in composer), [(MEL, 0.6), (SC, 0.5)])
    for name, weight in defaults:
        if len(chosen) >= 4:
            break
        chosen.setdefault(name, weight)
    return sorted(chosen.items(), key=lambda item: -item[1])[:5]


COMPOSER_FACTS = {
    "balakirev": (1837, 1910, "Russian", "Romantic"),
    "alkan": (1813, 1888, "French", "Romantic"),
    "godowsky": (1870, 1938, "Polish-American", "Romantic"),
    "schumann": (1810, 1856, "German", "Romantic"),
    "schubert": (1797, 1828, "Austrian", "Romantic"),
    "mendelssohn": (1809, 1847, "German", "Romantic"),
    "grieg": (1843, 1907, "Norwegian", "Romantic"),
    "mussorgsky": (1839, 1881, "Russian", "Romantic"),
    "haydn": (1732, 1809, "Austrian", "Classical"),
    "clementi": (1752, 1832, "Italian", "Classical"),
    "scarlatti": (1685, 1757, "Italian", "Baroque"),
    "handel": (1685, 1759, "German-British", "Baroque"),
    "satie": (1866, 1925, "French", "Impressionist"),
    "faure": (1845, 1924, "French", "Romantic"),
    "saint saens": (1835, 1921, "French", "Romantic"),
    "albeniz": (1860, 1909, "Spanish", "Romantic"),
    "granados": (1867, 1916, "Spanish", "Romantic"),
    "prokofiev": (1891, 1953, "Russian", "Modern"),
    "stravinsky": (1882, 1971, "Russian", "Modern"),
    "bartok": (1881, 1945, "Hungarian", "Modern"),
    "shostakovich": (1906, 1975, "Russian", "Modern"),
    "gershwin": (1898, 1937, "American", "Modern"),
    "joplin": (1868, 1917, "American", "Romantic"),
    "ligeti": (1923, 2006, "Hungarian", "Contemporary"),
    "messiaen": (1908, 1992, "French", "Modern"),
    "kapustin": (1937, 2020, "Russian", "Contemporary"),
    "medtner": (1880, 1951, "Russian", "Romantic"),
    "busoni": (1866, 1924, "Italian", "Romantic"),
    "moszkowski": (1854, 1925, "Polish-German", "Romantic"),
    "burgmuller": (1806, 1874, "German", "Romantic"),
    "field": (1782, 1837, "Irish", "Romantic"),
    "einaudi": (1955, None, "Italian", "Contemporary"),
    "yiruma": (1978, None, "South Korean", "Contemporary"),
    "poulenc": (1899, 1963, "French", "Modern"),
    "franck": (1822, 1890, "Belgian-French", "Romantic"),
    "dvorak": (1841, 1904, "Czech", "Romantic"),
    "kabalevsky": (1904, 1987, "Russian", "Modern"),
}


def composer_facts(name: Optional[str]):
    text = match_text(name)
    return next((facts for surname, facts in COMPOSER_FACTS.items() if f" {surname} " in text), None)
