from datetime import date
from decimal import Decimal

import pytest

from app.services.coach import CATEGORY_DRILLS, PlanBuilder, PolyrhythmTrainer
from app.services.performance import PerformanceService, ReadinessScorer
from app.services.practice import LiveListeningCoach, LoadGuard, week_start
from app.services.progression import cosine, coverage, gap_fit
from app.models.models import DrillType, LoadSeverity, TechniqueCategory


class FakePiece:
    def __init__(self, title, difficulty, duration=0):
        self.title = title
        self.difficulty_score = Decimal(str(difficulty))
        self.duration_sec = duration


class FakeAssessment:
    def __init__(self, accuracy, stability, restarts=0, slip=False):
        self.accuracy_score = Decimal(str(accuracy)) if accuracy is not None else None
        self.tempo_stability = Decimal(str(stability)) if stability is not None else None
        self.restart_count = restarts
        self.memory_slip = slip


def test_cosine_identity_and_orthogonal():
    a = {1: 1.0, 2: 0.5}
    assert cosine(a, a) == pytest.approx(1.0)
    assert cosine(a, {3: 1.0}) == 0.0
    assert cosine(a, {}) == 0.0
    assert cosine({}, a) == 0.0


def test_cosine_is_symmetric_and_bounded():
    a = {1: 0.9, 2: 0.3, 3: 0.6}
    b = {1: 0.4, 3: 0.8, 4: 0.2}
    assert cosine(a, b) == pytest.approx(cosine(b, a))
    assert 0.0 <= cosine(a, b) <= 1.0


def test_coverage_counts_only_meaningful_weights():
    target = {1: 1.0, 2: 1.0}
    assert coverage(target, {1: 0.9, 2: 0.9}) == pytest.approx(1.0)
    assert coverage(target, {1: 0.9}) == pytest.approx(0.5)
    assert coverage(target, {1: 0.1}) == pytest.approx(0.0)
    assert coverage({}, {1: 1.0}) == 0.0


def test_gap_fit_rejects_harder_pieces():
    assert gap_fit(0.0) == 0.0
    assert gap_fit(-2.0) == 0.0


def test_gap_fit_peaks_at_ideal_gap():
    assert gap_fit(15.0) == pytest.approx(1.0)
    assert gap_fit(15.0) > gap_fit(4.0)
    assert gap_fit(15.0) > gap_fit(50.0)


def test_readiness_scoring_bounds():
    perfect = ReadinessScorer.compute([FakeAssessment(1.0, 1.0)])
    assert perfect["overall_score"] == 100.0
    terrible = ReadinessScorer.compute([FakeAssessment(0.0, 0.0, restarts=10, slip=True)])
    assert terrible["overall_score"] == 0.0
    assert ReadinessScorer.compute([])["overall_score"] is None


def test_readiness_penalises_slips_and_restarts():
    clean = ReadinessScorer.compute([FakeAssessment(0.9, 0.9)])["overall_score"]
    restarted = ReadinessScorer.compute([FakeAssessment(0.9, 0.9, restarts=1)])["overall_score"]
    slipped = ReadinessScorer.compute([FakeAssessment(0.9, 0.9, slip=True)])["overall_score"]
    assert restarted < clean
    assert slipped < restarted


def test_readiness_counts_aggregate():
    metrics = ReadinessScorer.compute(
        [FakeAssessment(0.9, 0.9, restarts=1), FakeAssessment(0.8, 0.8, restarts=2, slip=True)]
    )
    assert metrics["restart_count"] == 3
    assert metrics["memory_slip_count"] == 1


def test_program_verdict_tracks_weakest_link():
    assert PerformanceService.overall_verdict([]) == "no program set"
    strong = [{"overall_score": 92.0}, {"overall_score": 88.0}]
    assert PerformanceService.overall_verdict(strong) == "whole program is stage ready"
    mixed = [{"overall_score": 92.0}, {"overall_score": 74.0}]
    assert "nearly there" in PerformanceService.overall_verdict(mixed)
    weak = [{"overall_score": 92.0}, {"overall_score": 40.0}]
    assert PerformanceService.overall_verdict(weak) == "not ready, the weakest piece needs real work"
    partial = [{"overall_score": 92.0}, {"overall_score": None}]
    assert "unscored" in PerformanceService.overall_verdict(partial)


def test_load_severity_thresholds():
    assert LoadGuard.severity_for(0.9) == LoadSeverity.INFO
    assert LoadGuard.severity_for(1.19) == LoadSeverity.INFO
    assert LoadGuard.severity_for(1.2) == LoadSeverity.CAUTION
    assert LoadGuard.severity_for(1.49) == LoadSeverity.CAUTION
    assert LoadGuard.severity_for(1.5) == LoadSeverity.REST
    assert LoadGuard.severity_for(6.0) == LoadSeverity.REST


def test_load_message_never_claims_comfort_when_over():
    over = LoadGuard.message_for(LoadSeverity.INFO, Decimal("130"), Decimal("120"))
    assert "comfortably" not in over
    under = LoadGuard.message_for(LoadSeverity.INFO, Decimal("90"), Decimal("120"))
    assert "comfortably" in under


def test_week_start_is_monday():
    assert week_start(date(2026, 9, 21)).weekday() == 0
    assert week_start(date(2026, 9, 27)) == date(2026, 9, 21)
    assert week_start(date(2026, 9, 21)) == date(2026, 9, 21)


def test_live_coach_flags_rushing_dragging_and_tension():
    coach = LiveListeningCoach(target_bpm=120)
    assert any("rushing" in c for c in coach.ingest({"bpm": 140})["cues"])
    assert any("dragging" in c for c in coach.ingest({"bpm": 100})["cues"])
    assert coach.ingest({"bpm": 121})["cues"] == []
    assert any("tension" in c for c in coach.ingest({"tension": 0.9})["cues"])
    assert any("accuracy" in c for c in coach.ingest({"accuracy": 0.5})["cues"])


def test_live_coach_report_scales_tension():
    coach = LiveListeningCoach(target_bpm=100)
    for _ in range(3):
        coach.ingest({"bpm": 100, "accuracy": 0.95, "tension": 0.6})
    report = coach.report()
    assert report["frames"] == 3
    assert report["perceived_tension"] == 3
    assert report["average"]["bpm"] == 100.0
    assert LiveListeningCoach.tension_scale(None) is None
    assert LiveListeningCoach.tension_scale(0.0) == 1
    assert LiveListeningCoach.tension_scale(1.0) == 5


def test_movement_ordering_puts_gentlest_first():
    movements = [
        FakePiece("I Moderato", 9.5, 660),
        FakePiece("II Adagio", 8.2, 690),
        FakePiece("III Allegro", 9.2, 700),
    ]
    ordered = PlanBuilder.order_movements(movements)
    assert ordered[0].title == "II Adagio"
    assert [m.title for m in ordered] == ["II Adagio", "III Allegro", "I Moderato"]


def test_movement_ordering_handles_single_movement():
    single = [FakePiece("Solo", 5.0)]
    assert PlanBuilder.order_movements(single) == single
    assert PlanBuilder.order_movements([]) == []


def test_days_for_scales_with_difficulty():
    assert PlanBuilder.days_for(Decimal("9.5")) > PlanBuilder.days_for(Decimal("3.0"))
    assert PlanBuilder.days_for(None) >= 2
    assert PlanBuilder.days_for(Decimal("0.1")) >= 2


def test_polyrhythm_accuracy_rewards_tight_playing():
    tight = PolyrhythmTrainer.accuracy_from([5.0, -4.0, 3.0], 80)
    loose = PolyrhythmTrainer.accuracy_from([150.0, -180.0, 160.0], 80)
    assert tight > loose
    assert 0.0 <= loose <= 1.0
    assert tight > 0.9
    assert PolyrhythmTrainer.accuracy_from([], 80) is None


def test_every_technique_category_maps_to_a_drill():
    for category in TechniqueCategory:
        assert CATEGORY_DRILLS.get(category), f"{category} has no drill mapping"
        assert all(isinstance(d, DrillType) for d in CATEGORY_DRILLS[category])


def test_level_curve_is_monotonic_and_anchored():
    from app.models.models import level_for_xp, xp_for_level

    assert level_for_xp(0) == 1
    assert level_for_xp(-50) == 1
    previous = 1
    for xp in range(0, 60000, 137):
        level = level_for_xp(xp)
        assert level >= previous
        previous = level
    for level in range(1, 25):
        floor = xp_for_level(level)
        assert level_for_xp(floor) == level
        assert level_for_xp(max(floor - 1, 0)) == max(level - 1, 1)


def test_learning_reward_scales_with_difficulty():
    from app.services.economy import learning_reward

    easy_xp, easy_gold = learning_reward(Decimal("3.0"))
    hard_xp, hard_gold = learning_reward(Decimal("9.5"))
    assert hard_xp > easy_xp * 2
    assert hard_gold > easy_gold * 2
    assert learning_reward(None)[0] > 0


def test_graded_reward_is_massive_and_rises_with_score():
    from app.services.economy import graded_reward, learning_reward

    pass_xp, pass_gold = graded_reward(Decimal("9.3"), Decimal("80"))
    great_xp, great_gold = graded_reward(Decimal("9.3"), Decimal("98"))
    assert great_gold > pass_gold
    assert great_xp > pass_xp
    assert pass_gold > learning_reward(Decimal("9.3"))[1] * 2


def test_practice_reward_is_capped():
    from app.services.economy import PRACTICE_MINUTE_CAP, practice_reward

    assert practice_reward(0) == (0, 0)
    assert practice_reward(-20) == (0, 0)
    capped = practice_reward(10_000)
    assert capped == practice_reward(PRACTICE_MINUTE_CAP)


def test_achievement_rules_gate_on_metrics():
    from app.services.economy import AchievementEngine

    empty = {"learned": 0, "repertoire": 0, "submissions": 0, "best_grade": 0.0,
             "hardest_learned": 0.0, "best_polyrhythm": 0.0, "level": 1, "lifetime_gold": 0}
    assert not AchievementEngine.qualifies("first_piece", empty)
    assert not AchievementEngine.qualifies("unknown_code", empty)

    loaded = {"learned": 21, "repertoire": 30, "submissions": 4, "best_grade": 99.0,
              "hardest_learned": 98.0, "best_polyrhythm": 0.95, "level": 11, "lifetime_gold": 5000}
    for code in ["first_piece", "first_learned", "five_learned", "twenty_learned", "first_submission",
                 "first_pass", "grade_ninety", "flawless", "grade_eight_club", "virtuoso",
                 "polyrhythm_steady", "level_five", "level_ten", "first_fortune"]:
        assert AchievementEngine.qualifies(code, loaded), code


def test_grading_threshold_constants_are_coherent():
    from app.models.models import GRADED_DIFFICULTY_THRESHOLD, GRADED_PASS_SCORE

    assert 0 < GRADED_DIFFICULTY_THRESHOLD < 100
    assert 0 < GRADED_PASS_SCORE <= 100
