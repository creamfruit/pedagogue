import random
from datetime import datetime, timedelta, timezone

import pytest

from app.services.keyboard_scoring import (
    MAX_PLAYED_NOTES,
    PlayedNote,
    RefNote,
    ScoringError,
    default_start_tempo,
    group_played,
    group_reference,
    ladder_state,
    next_tempo,
    refreshed_practice_time,
    score_free,
    score_timed,
    score_wait,
)

SCALE = [60, 62, 64, 65, 67, 69, 71, 72]


def melody(pitches=SCALE, per_bar=4, step=1.0):
    return [RefNote(i * step, midi, 1 + i // per_bar) for i, midi in enumerate(pitches)]


def perform(reference, tempo, shift_ms=0.0, scale=1.0, drop=(), replace=None, extra=(), jitter=None):
    beat = 60000.0 / tempo
    replace = replace or {}
    out = []
    for index, note in enumerate(reference):
        if index in drop:
            continue
        time = note.onset * beat * scale + shift_ms
        if jitter:
            time += jitter(index)
        out.append(PlayedNote(time, replace.get(index, note.midi)))
    out.extend(extra)
    return out


def bar(score, number):
    return next(item for item in score.bars if item.bar == number)


def test_a_perfect_run_scores_full_marks_and_is_clean():
    reference = melody()
    score = score_timed(reference, perform(reference, 100), 100)
    assert (score.expected, score.correct, score.wrong, score.missing) == (8, 8, 0, 0)
    assert score.accuracy == 1.0
    assert score.timing == 100.0
    assert score.evenness == 100.0
    assert score.overall == 100.0
    assert score.clean is True
    assert score.achieved_tempo_bpm == pytest.approx(100, abs=0.5)
    assert [item.accuracy for item in score.bars] == [1.0, 1.0]
    assert all(item.late == 0 and item.early == 0 for item in score.bars)


def test_a_wrong_note_costs_accuracy_in_its_own_bar_only():
    reference = melody()
    score = score_timed(reference, perform(reference, 100, replace={5: 70}), 100)
    assert (score.correct, score.wrong, score.missing) == (7, 1, 1)
    assert score.accuracy == pytest.approx(7 / 9, abs=1e-3)
    assert bar(score, 1).accuracy == 1.0
    assert bar(score, 2).accuracy == pytest.approx(3 / 5, abs=1e-3)
    assert (bar(score, 2).wrong, bar(score, 2).missing) == (1, 1)
    assert score.clean is False


def test_a_missing_note_is_counted_without_a_wrong_note():
    reference = melody()
    score = score_timed(reference, perform(reference, 100, drop={2}), 100)
    assert (score.correct, score.wrong, score.missing) == (7, 0, 1)
    assert score.accuracy == pytest.approx(7 / 8, abs=1e-3)
    assert bar(score, 1).missing == 1
    assert score.clean is False


def test_an_extra_note_is_wrong_and_the_rest_still_lines_up():
    reference = melody()
    stray = [PlayedNote(2.5 * 600, 61)]
    score = score_timed(reference, perform(reference, 100, extra=stray), 100)
    assert (score.correct, score.wrong, score.missing) == (8, 1, 0)
    assert score.accuracy == pytest.approx(8 / 9, abs=1e-3)
    assert bar(score, 1).wrong == 1
    assert score.timing == 100.0


def test_a_late_note_is_flagged_and_costs_timing_in_its_bar():
    reference = melody()
    score = score_timed(reference, perform(reference, 120, jitter=lambda i: 300.0 if i == 6 else 0.0), 120)
    assert score.accuracy == 1.0
    assert score.timing == pytest.approx(87.5, abs=0.1)
    assert score.late == 1 and score.early == 0
    assert bar(score, 2).late == 1
    assert bar(score, 2).timing_error_ms == pytest.approx(75.0, abs=0.1)
    assert bar(score, 1).late == 0


def test_an_early_note_is_flagged_as_early():
    reference = melody()
    score = score_timed(reference, perform(reference, 120, jitter=lambda i: -300.0 if i == 1 else 0.0), 120)
    assert score.early == 1 and score.late == 0
    assert bar(score, 1).early == 1


def test_a_small_steady_offset_is_within_tolerance():
    reference = melody()
    score = score_timed(reference, perform(reference, 100, shift_ms=30), 100)
    assert score.timing == 100.0
    assert score.late == 0


def test_every_note_a_little_late_loses_partial_credit():
    reference = melody()
    score = score_timed(reference, perform(reference, 120, shift_ms=150), 120)
    assert score.accuracy == 1.0
    assert score.timing == pytest.approx(50.0, abs=0.1)
    assert score.late == 8
    assert score.evenness == 100.0


def test_latency_compensation_removes_a_constant_device_delay():
    reference = melody()
    played = perform(reference, 120, shift_ms=120)
    assert score_timed(reference, played, 120).timing < 80
    assert score_timed(reference, played, 120, latency_ms=120).timing == 100.0


def test_playing_slower_than_the_tempo_still_matches_every_note():
    reference = melody(SCALE * 2, per_bar=4)
    score = score_timed(reference, perform(reference, 100, scale=1.25), 100)
    assert (score.correct, score.wrong, score.missing) == (16, 0, 0)
    assert score.accuracy == 1.0
    assert score.achieved_tempo_bpm == pytest.approx(80, abs=1)
    assert score.evenness == 100.0
    assert score.timing < 60
    assert score.clean is False
    assert bar(score, 3).tempo_bpm == pytest.approx(80, abs=2)


def test_uneven_playing_scores_lower_evenness_than_steady_playing():
    reference = melody(SCALE * 2, per_bar=4)
    steady = score_timed(reference, perform(reference, 100), 100)
    rushed = score_timed(reference, perform(reference, 100, jitter=lambda i: 90.0 if i % 2 else -90.0), 100)
    assert steady.evenness == 100.0
    assert rushed.evenness < 60
    assert rushed.accuracy == 1.0


def test_random_small_jitter_stays_clean():
    rng = random.Random(7)
    reference = melody(SCALE * 2, per_bar=4)
    score = score_timed(reference, perform(reference, 100, jitter=lambda i: rng.uniform(-25, 25)), 100)
    assert score.accuracy == 1.0
    assert score.timing == 100.0
    assert score.evenness >= 65
    assert score.clean is True


def test_chords_count_as_correct_whatever_the_order_and_small_spread():
    reference = [RefNote(0, 60, 1), RefNote(0, 64, 1), RefNote(0, 67, 1), RefNote(1, 62, 1), RefNote(1, 65, 1), RefNote(1, 69, 1)]
    played = [PlayedNote(25, 67), PlayedNote(0, 60), PlayedNote(12, 64), PlayedNote(630, 69), PlayedNote(600, 62), PlayedNote(610, 65)]
    score = score_timed(reference, played, 100)
    assert (score.expected, score.correct, score.wrong, score.missing) == (6, 6, 0, 0)
    assert score.accuracy == 1.0


def test_a_wrong_note_inside_a_chord_is_one_wrong_and_one_missing():
    reference = [RefNote(0, 60, 1), RefNote(0, 64, 1), RefNote(0, 67, 1)]
    played = [PlayedNote(0, 60), PlayedNote(10, 64), PlayedNote(20, 68)]
    score = score_timed(reference, played, 100)
    assert (score.correct, score.wrong, score.missing) == (2, 1, 1)


def test_repeated_notes_with_one_skipped_are_one_missing():
    reference = [RefNote(i, 60, 1) for i in range(6)]
    score = score_timed(reference, perform(reference, 100, drop={3}), 100)
    assert (score.correct, score.wrong, score.missing) == (5, 0, 1)


def test_playing_nothing_scores_zero_and_marks_everything_missing():
    reference = melody()
    score = score_timed(reference, [], 100)
    assert (score.correct, score.wrong, score.missing) == (0, 0, 8)
    assert score.accuracy == 0.0
    assert score.timing is None and score.evenness is None
    assert score.overall == 0.0
    assert score.clean is False
    assert all(item.accuracy == 0.0 for item in score.bars)


def test_playing_only_the_first_half_marks_the_second_bar_missing():
    reference = melody()
    score = score_timed(reference, perform(reference, 100)[:4], 100)
    assert bar(score, 1).accuracy == 1.0
    assert bar(score, 2).missing == 4 and bar(score, 2).accuracy == 0.0


def test_a_whole_passage_of_wrong_notes_is_not_clean_or_free_points():
    reference = melody()
    score = score_timed(reference, perform(reference, 100, replace={i: 61 for i in range(8)}), 100)
    assert score.correct == 0
    assert score.accuracy == 0.0
    assert score.clean is False


def test_a_long_passage_scores_within_the_limits():
    pitches = [48 + (i * 7) % 36 for i in range(700)]
    reference = melody(pitches, per_bar=4, step=0.5)
    score = score_timed(reference, perform(reference, 120), 120)
    assert score.accuracy == 1.0
    assert len(score.bars) == 175


def test_limits_and_bad_input_are_refused():
    reference = melody()
    with pytest.raises(ScoringError):
        score_timed(reference, [], 10)
    with pytest.raises(ScoringError):
        score_timed([], [PlayedNote(0, 60)], 100)
    with pytest.raises(ScoringError):
        score_timed(reference, [PlayedNote(float(i), 60) for i in range(MAX_PLAYED_NOTES + 1)], 100)
    with pytest.raises(ScoringError):
        score_timed(melody([60] * 801), [], 100)
    with pytest.raises(ScoringError):
        score_free([], 100, beats_per_bar=40)


def test_grouping_keeps_fast_runs_apart_and_merges_a_chord():
    assert len(group_played([PlayedNote(0, 60), PlayedNote(15, 64), PlayedNote(30, 67)])) == 1
    assert len(group_played([PlayedNote(i * 80.0, 60 + i) for i in range(5)])) == 5
    merged = group_reference([RefNote(0, 60, 1), RefNote(0.01, 64, 1), RefNote(1, 62, 1)])
    assert [sorted(event.pitches) for event in merged] == [[60, 64], [62]]


def test_wait_mode_advances_only_on_the_right_notes():
    reference = melody()
    played = [PlayedNote(i * 500.0, midi) for i, midi in enumerate(SCALE)]
    score = score_wait(reference, played)
    assert score.mode == "wait" and score.tempo_bpm is None
    assert (score.correct, score.wrong, score.missing) == (8, 0, 0)
    assert score.timing is None and score.evenness is None
    assert score.clean is True


def test_wait_mode_counts_wrong_presses_and_waits_for_the_right_one():
    reference = melody()
    played = [PlayedNote(0, 60), PlayedNote(500, 61), PlayedNote(900, 63), PlayedNote(1400, 62)] + [
        PlayedNote(2000 + i * 400.0, midi) for i, midi in enumerate(SCALE[2:])
    ]
    score = score_wait(reference, played)
    assert (score.correct, score.wrong, score.missing) == (8, 2, 0)
    assert score.accuracy == pytest.approx(8 / 10, abs=1e-3)
    assert bar(score, 1).wrong == 2
    assert score.clean is False


def test_wait_mode_with_a_chord_needs_every_note_and_ignores_order():
    reference = [RefNote(0, 60, 1), RefNote(0, 64, 1), RefNote(1, 62, 1)]
    played = [PlayedNote(0, 64), PlayedNote(300, 60), PlayedNote(900, 62)]
    score = score_wait(reference, played)
    assert (score.correct, score.wrong, score.missing) == (3, 0, 0)


def test_wait_mode_stopping_early_leaves_the_rest_missing():
    reference = melody()
    played = [PlayedNote(i * 500.0, midi) for i, midi in enumerate(SCALE[:3])]
    score = score_wait(reference, played)
    assert (score.correct, score.missing) == (3, 5)
    assert bar(score, 2).missing == 4
    assert score.clean is False


def test_wait_mode_ignores_notes_after_the_end():
    reference = melody(SCALE[:2], per_bar=4)
    played = [PlayedNote(0, 60), PlayedNote(400, 62), PlayedNote(800, 90)]
    score = score_wait(reference, played)
    assert score.wrong == 0 and score.clean is True


def grid(count, tempo, subdivision, jitter=None):
    step = 60000.0 / tempo / subdivision
    out = []
    for index in range(count):
        time = index * step + (jitter(index) if jitter else 0.0)
        out.append(PlayedNote(time, 60 + index % 5))
    return out


def test_free_play_in_steady_eighths_is_clean_and_picks_the_subdivision():
    score = score_free(grid(16, 100, 2), 100)
    assert score.mode == "free"
    assert score.accuracy is None and score.expected == 0
    assert score.timing == 100.0
    assert score.evenness == 100.0
    assert score.clean is True
    assert [item.bar for item in score.bars] == [1, 2]


def test_free_play_in_steady_quarters_is_not_mistaken_for_a_finer_grid():
    score = score_free(grid(12, 90, 1), 90)
    assert score.timing == 100.0 and score.clean is True


def test_free_play_that_wanders_off_the_beat_scores_lower():
    rng = random.Random(3)
    steady = score_free(grid(16, 100, 2), 100)
    wobbly = score_free(grid(16, 100, 2, jitter=lambda i: rng.uniform(-70, 70)), 100)
    assert wobbly.overall < steady.overall - 20
    assert wobbly.evenness < steady.evenness
    assert wobbly.clean is False
    gentle = score_free(grid(16, 100, 2, jitter=lambda i: random.Random(i).uniform(-15, 15)), 100)
    assert gentle.clean is True


def test_free_play_reports_late_and_early_notes_per_bar():
    played = grid(8, 100, 1, jitter=lambda i: 200.0 if i == 5 else 0.0)
    score = score_free(played, 100, subdivision=1)
    assert score.late == 1
    assert next(item for item in score.bars if item.late).bar == 2


def test_free_play_with_too_little_to_judge_has_no_scores():
    score = score_free([PlayedNote(0, 60)], 100)
    assert score.timing is None and score.evenness is None and score.clean is False


def test_the_ladder_starts_below_the_target():
    state = ladder_state([], 120)
    assert state.recommended_tempo == default_start_tempo(120) == 72
    assert state.current_tempo is None and state.clean_streak == 0 and not state.raised
    assert default_start_tempo(50) == 40
    assert default_start_tempo(30) == 30


def test_the_ladder_raises_the_tempo_after_two_clean_runs():
    one = ladder_state([(80, True)], 120)
    assert (one.clean_streak, one.raised, one.recommended_tempo) == (1, False, 80)
    two = ladder_state([(80, True), (80, True)], 120)
    assert (two.clean_streak, two.raised, two.recommended_tempo) == (2, True, 84)


def test_an_unclean_run_breaks_the_streak():
    state = ladder_state([(80, True), (80, False), (80, True)], 120)
    assert state.clean_streak == 1 and not state.raised
    assert ladder_state([(80, False), (80, True), (80, True)], 120).clean_streak == 0


def test_a_new_tempo_starts_a_new_streak():
    state = ladder_state([(84, True), (80, True), (80, True)], 120)
    assert state.current_tempo == 84 and state.clean_streak == 1 and state.recommended_tempo == 84


def test_the_ladder_stops_at_the_target():
    assert next_tempo(118, 120) == 120
    assert next_tempo(40, 120) == 42
    state = ladder_state([(120, True), (120, True)], 120)
    assert state.reached_target and not state.raised and state.recommended_tempo == 120


def test_a_poor_run_pulls_review_closer_a_good_run_resets_it():
    now = datetime(2026, 10, 19, tzinfo=timezone.utc)
    before = now - timedelta(days=10)
    assert refreshed_practice_time(before, now, 90) == now
    assert refreshed_practice_time(before, now, 40) == before + timedelta(days=5)
    assert refreshed_practice_time(None, now, 10) == now
