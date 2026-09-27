import json
from pathlib import Path

from app.seed import TECHNIQUES

LIBRARY = Path(__file__).resolve().parents[2] / "frontend" / "public" / "excerpts"


def load_index():
    return json.loads((LIBRARY / "index.json").read_text(encoding="utf-8"))


def test_every_technique_has_a_real_excerpt():
    index = load_index()
    names = {name for name, _category, _factor in TECHNIQUES}
    assert names <= set(index["techniques"])


def test_every_excerpt_ships_its_score_and_notes():
    index = load_index()
    for excerpt in index["excerpts"].values():
        assert (LIBRARY / excerpt["score"]).is_file()
        assert excerpt["events"], excerpt["id"]
        assert excerpt["bars"][0] <= excerpt["bars"][1]
        assert 21 <= min(event[2] for event in excerpt["events"])
        assert max(event[2] for event in excerpt["events"]) <= 108


def test_cross_checked_excerpts_agree_with_their_second_source():
    index = load_index()
    for excerpt in index["excerpts"].values():
        for check in excerpt["checks"]:
            if not excerpt.get("manual_check"):
                assert check["match"] >= 0.9, (excerpt["id"], check)
