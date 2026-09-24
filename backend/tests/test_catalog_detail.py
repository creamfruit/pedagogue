import pytest

from app.services.catalog import LinkExplainer, PieceOverviewService, difficulty_band


class FakeTechnique:
    def __init__(self, tid, name, mechanic=None, fault=None, load=1.0, category="dexterity"):
        self.id = tid
        self.name = name
        self.mechanic = mechanic
        self.common_fault = fault
        self.load_factor = load
        self.category = category
        self.description = None


class FakeLink:
    def __init__(self, technique, weight):
        self.technique = technique
        self.technique_id = technique.id
        self.weight = weight


class FakePassage:
    def __init__(self, pid, start, end, label, score, links, description="", cue=""):
        self.id = pid
        self.start_measure = start
        self.end_measure = end
        self.label = label
        self.difficulty_score = score
        self.description = description
        self.practice_cue = cue
        self.technique_links = links

    @property
    def measure_span(self):
        if self.start_measure == self.end_measure:
            return f"bar {self.start_measure}"
        return f"bars {self.start_measure}–{self.end_measure}"

    @property
    def length(self):
        return self.end_measure - self.start_measure + 1


class FakeComposer:
    def __init__(self, name, born=None, died=None):
        self.id = 1
        self.name = name
        self.nationality = "Polish"
        self.birth_year = born
        self.death_year = died
        self.bio = "bio"
        self.fun_fact = "fact"
        self.signature_sound = "sound"
        self.era = None

    @property
    def lifespan(self):
        return f"{self.birth_year}–{self.death_year or ''}" if self.birth_year else ""

    @property
    def byline(self):
        return " · ".join(x for x in [self.name, self.nationality, self.lifespan] if x)


class FakePiece:
    def __init__(self, pid, title, difficulty, links, passages=(), year=None):
        self.id = pid
        self.title = title
        self.difficulty_score = difficulty
        self.mechanical_load = difficulty
        self.technique_links = links
        self.passages = list(passages)
        self.year_composed = year
        self.composer = FakeComposer("Frederic Chopin", 1810, 1849)
        self.genre = None
        self.genre_id = None
        self.duration_sec = 130
        self.catalog_number = "Op. 25 No. 6"
        self.key_signature = "G-sharp minor"
        self.tempo_marking = "Allegro"
        self.mood = "Glittering"
        self.scene = "scene"
        self.historical_note = "history"
        self.fun_fact = "fun"
        self.syllabus_grade = None
        self.external_source = None
        self.requires_verification = False
        self.is_custom = False
        self.load_profile = None
        self.movements = []
        self.parent_piece = None

    @property
    def era_name(self):
        return "Romantic"

    @property
    def duration_label(self):
        minutes, seconds = divmod(self.duration_sec, 60)
        if minutes and seconds:
            return f"{minutes} min {seconds} sec"
        return f"{minutes} min" if minutes else f"{seconds} sec"

    @property
    def hardest_techniques(self):
        return sorted(
            self.technique_links,
            key=lambda link: float(link.weight) * float(link.technique.load_factor),
            reverse=True,
        )

    @property
    def hardest_passages(self):
        scored = [p for p in self.passages if p.difficulty_score is not None]
        return sorted(scored, key=lambda p: p.difficulty_score, reverse=True)


THIRDS = FakeTechnique(1, "Double thirds", "Fixed frame, alternating pairs.", "Pushing from the fingers alone.", 1.7, "double_notes")
TRILLS = FakeTechnique(2, "Trills", "Small forearm rotation.", "Lifting the fingers high.", 1.25, "trills")
SCALES = FakeTechnique(3, "Rapid scales", "Thumb under a moving hand.", "Accenting the thumb note.", 1.1, "dexterity")


def test_difficulty_bands():
    assert difficulty_band(None) == "unrated"
    assert difficulty_band(20.0) == "beginner"
    assert difficulty_band(40.0) == "early intermediate"
    assert difficulty_band(60.0) == "intermediate"
    assert difficulty_band(75.0) == "late intermediate"
    assert difficulty_band(85.0) == "advanced"
    assert difficulty_band(95.0) == "virtuoso"


def test_overview_orders_sections_hardest_first():
    passages = [
        FakePassage(1, 1, 8, "Opening", 9.0, [FakeLink(THIRDS, 1.0)]),
        FakePassage(2, 33, 44, "Trill section", 9.4, [FakeLink(THIRDS, 1.0), FakeLink(TRILLS, 0.8)]),
        FakePassage(3, 61, 69, "Close", 9.2, [FakeLink(THIRDS, 1.0)]),
    ]
    piece = FakePiece(1, "Etude in G-sharp minor", 92.0, [FakeLink(THIRDS, 1.0), FakeLink(TRILLS, 0.6)], passages)
    data = PieceOverviewService.render(PieceOverviewService.__new__(PieceOverviewService), piece)

    assert [s["measure_span"] for s in data["sections"]] == ["bars 33–44", "bars 61–69", "bars 1–8"]
    assert data["sections"][0]["techniques"] == ["Double thirds", "Trills"]
    assert data["difficulty_band"] == "virtuoso"
    assert data["duration_label"] == "2 min 10 sec"
    assert data["composer"]["byline"].startswith("Frederic Chopin")


def test_overview_ranks_techniques_by_weighted_load():
    piece = FakePiece(1, "X", 9.0, [FakeLink(SCALES, 0.9), FakeLink(THIRDS, 0.7)])
    data = PieceOverviewService.render(PieceOverviewService.__new__(PieceOverviewService), piece)
    assert [t["name"] for t in data["techniques"]] == ["Double thirds", "Rapid scales"]


def explainer():
    return LinkExplainer.__new__(LinkExplainer)


def test_technique_body_names_the_shared_mechanic():
    a = FakePiece(1, "Double Thirds", 9.2, [FakeLink(THIRDS, 1.0), FakeLink(TRILLS, 0.6)],
                  [FakePassage(1, 1, 8, "Opening", 9.0, [FakeLink(THIRDS, 1.0)])])
    b = FakePiece(2, "Feux Follets", 9.8, [FakeLink(THIRDS, 0.9), FakeLink(SCALES, 0.7)],
                  [FakePassage(2, 7, 20, "Opening", 9.7, [FakeLink(THIRDS, 0.95)])])

    body = explainer().technique_body(a, b)
    assert "Double thirds" in body["headline"] or "double thirds" in body["headline"]
    assert "100%" in body["summary"] and "90%" in body["summary"]
    assert body["summary"].count("Fixed frame") == 1
    names = [t["name"] for t in body["shared_techniques"]]
    assert names == ["Double thirds"]
    assert len(body["shared_sections"]) == 2


def test_technique_body_drops_weak_overlap():
    a = FakePiece(1, "A", 5.0, [FakeLink(THIRDS, 0.9)])
    b = FakePiece(2, "B", 5.0, [FakeLink(THIRDS, 0.1)])
    body = explainer().technique_body(a, b)
    assert body["shared_techniques"] == []
    assert body["headline"] == "Loosely related"


def test_composer_body_handles_same_year():
    a = FakePiece(1, "A", 9.8, [], year=1852)
    b = FakePiece(2, "B", 9.1, [], year=1852)
    body = explainer().composer_body(a, b)
    assert "Both written in 1852" in body["facts"]
    assert "Difficulty gap: 0.7 points" in body["facts"]


def test_composer_body_reports_a_year_apart():
    a = FakePiece(1, "A", 8.0, [], year=1835)
    b = FakePiece(2, "B", 8.0, [], year=1836)
    body = explainer().composer_body(a, b)
    assert "Written 1835 and 1836, a year apart" in body["facts"]


def test_era_genre_body_uses_the_shared_era():
    a = FakePiece(1, "A", 8.0, [])
    b = FakePiece(2, "B", 7.0, [])
    body = explainer().era_genre_body(a, b)
    assert body["headline"] == "Both Romantic"
    assert "Romantic" in body["summary"]


def test_gap_handles_missing_scores():
    a = FakePiece(1, "A", None, [])
    b = FakePiece(2, "B", 7.0, [])
    assert LinkExplainer.gap(a, b) == "unknown"


@pytest.mark.parametrize("bad", ["vibes", "", "TECHNIQUE!"])
def test_unknown_link_type_is_rejected(bad):
    from app.models.models import LinkType

    with pytest.raises(ValueError):
        LinkType(bad)
