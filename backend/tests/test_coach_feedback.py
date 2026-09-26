from decimal import Decimal

from app.services.coach_feedback import SCHEMA, clean, heuristic_feedback, join_names, tier_for, weakest_passage
from tests.test_ai import walk_objects


def context(**overrides):
    base = {
        "piece": "Etude in G-sharp minor",
        "take": {"duration_sec": 120, "full_run_through": True, "verification": False},
        "tempo_match": None,
        "techniques": [
            {"name": "Double thirds", "share": 1.0, "your_tier": "A"},
            {"name": "Trills", "share": 0.6, "your_tier": "D"},
        ],
        "hardest_passages": [
            {"bars": "bars 1–8", "label": "Opening", "difficulty": 9.8, "techniques": ["Double thirds"], "cue": "Slow hands."},
            {"bars": "bars 33–44", "label": "Trill section", "difficulty": 9.4, "techniques": ["Trills"], "cue": None},
        ],
        "recent_notes": [],
    }
    return {**base, **overrides}


def test_tiers_and_names():
    assert [tier_for(Decimal(v)) for v in ("9.0", "7.2", "5.5", "3.5", "1.5")] == ["S", "A", "B", "C", "D"]
    assert tier_for(None) is None
    assert join_names(["Trills"]) == "trills"
    assert join_names(["Double thirds", "Trills", "Octaves"]) == "double thirds, trills and octaves"


def test_weakest_passage_beats_hardest_passage():
    assert weakest_passage(context())["label"] == "Trill section"


def test_heuristic_feedback_leads_with_the_weak_technique():
    feedback = heuristic_feedback(context())
    assert feedback["focus"][0]["passage"] == "Trill section (bars 33–44)"
    assert "trills" in feedback["focus"][0]["why"]
    assert feedback["focus"][0]["drill"]
    assert "full run-through" in feedback["summary"]


def test_clean_keeps_three_complete_items():
    raw = {"summary": " Good. ", "focus": [{"passage": "A", "why": "w", "drill": "d"}] * 5 + [{"passage": "", "drill": "x"}], "next_session": "n"}
    cleaned = clean(raw)
    assert cleaned["summary"] == "Good."
    assert len(cleaned["focus"]) == 3


def test_schema_is_strict():
    for obj in walk_objects(SCHEMA):
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])
