from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.services.economy import ACHIEVEMENT_RULES, ACHIEVEMENT_SERIES, AchievementEngine
from app.services.growth import rolling, weekly_series
from app.services.streaks import STREAK_MIN_MINUTES, bonus_for, compute_streak, local_day, minutes_per_day

TODAY = date(2026, 9, 26)


def days(*offsets, minutes=10):
    return {TODAY - timedelta(days=offset): minutes for offset in offsets}


def test_streak_counts_consecutive_days_ending_today():
    stats = compute_streak(days(0, 1, 2, 5, 6), TODAY)
    assert (stats.current, stats.longest, stats.today_done) == (3, 3, True)


def test_streak_survives_until_today_is_over():
    stats = compute_streak(days(1, 2), TODAY)
    assert stats.current == 2
    assert not stats.today_done
    assert stats.next_bonus_xp == bonus_for(3)


def test_missing_a_day_is_covered_by_a_free_streak_freeze():
    stats = compute_streak(days(2, 3, 4, 5, 6, 7, 8), TODAY)
    assert stats.current == 7
    assert stats.longest == 7
    assert stats.freezes == 1
    assert stats.frozen_days == (TODAY - timedelta(days=1),)
    assert stats.state == "covered"


def test_a_gap_longer_than_the_freezes_starts_a_fresh_streak_quietly():
    stats = compute_streak(days(5, 6, 7), TODAY)
    assert stats.current == 0
    assert stats.longest == 3
    assert stats.state == "fresh"
    assert stats.freezes == 1


def test_short_sessions_do_not_count():
    minutes = {**days(0, 1), TODAY - timedelta(days=2): STREAK_MIN_MINUTES - 1}
    assert compute_streak(minutes, TODAY).current == 2


def test_bonus_grows_then_caps():
    assert [bonus_for(n) for n in (1, 2, 7, 30)] == [10, 20, 70, 70]


def test_days_are_local_to_the_user():
    late = datetime(2026, 9, 25, 23, 30, tzinfo=timezone.utc)
    assert local_day(late, ZoneInfo("Asia/Singapore")) == date(2026, 9, 26)
    assert local_day(late, ZoneInfo("America/New_York")) == date(2026, 9, 25)
    sessions = [
        SimpleNamespace(started_at=late, ended_at=late, logged_minutes=20),
        SimpleNamespace(started_at=late, ended_at=None, logged_minutes=50),
    ]
    assert minutes_per_day(sessions, ZoneInfo("Asia/Singapore")) == {date(2026, 9, 26): 20}


def test_weekly_series_weights_by_minutes_and_rolls():
    monday = TODAY - timedelta(days=TODAY.weekday())
    practice = [
        (monday, 40.0, 30),
        (monday, 80.0, 10),
        (monday - timedelta(weeks=1), 60.0, 20),
    ]
    learned = [(monday, "Etude", 92.0)]
    series = weekly_series(practice, learned, TODAY, 4)
    last, previous = series["weeks"][-1], series["weeks"][-2]
    assert last["practised_avg"] == 50.0
    assert previous["practised_avg"] == 60.0
    assert last["rolling_avg"] == 55.0
    assert last["learned"][0]["title"] == "Etude"
    assert series["change"] == -5.0
    assert rolling([None, 2.0, None, 4.0], 2) == [None, 2.0, 2.0, 4.0]


def test_every_seeded_achievement_has_a_rule_and_series():
    from app.seed import ACHIEVEMENTS

    codes = {code for code, *_ in ACHIEVEMENTS}
    assert codes <= set(ACHIEVEMENT_RULES)
    assert codes <= {code for series in ACHIEVEMENT_SERIES.values() for code in series}


def test_progress_labels_and_fraction():
    metrics = {"learned": 3, "best_grade": 72.0, "best_polyrhythm": 0.81, "longest_streak": 9}
    assert AchievementEngine.progress("five_learned", metrics)["label"] == "3 of 5 pieces learnt"
    assert AchievementEngine.progress("five_learned", metrics)["fraction"] == 0.6
    assert AchievementEngine.progress("first_pass", metrics)["label"] == "best graded run 72, needs 80"
    assert AchievementEngine.progress("polyrhythm_steady", metrics)["label"] == "best polyrhythm 81%, needs 90%"
    assert AchievementEngine.progress("streak_week", metrics)["label"] == "longest streak 9 of 7 days"
    assert AchievementEngine.progress("streak_month", metrics)["label"] == "longest streak 9 of 30 days"
    assert AchievementEngine.qualifies("streak_week", metrics)
    assert not AchievementEngine.qualifies("streak_month", metrics)


def test_a_new_player_with_nothing_logged_has_a_new_streak_and_one_freeze():
    stats = compute_streak({}, TODAY)
    assert (stats.current, stats.freezes, stats.state, stats.last_day) == (0, 1, "new", None)
    assert stats.as_dict()["freeze_cap"] == 2


def test_the_freeze_covers_one_missed_day_in_the_middle_of_a_streak():
    stats = compute_streak(days(0, 1, 2, 4, 5), TODAY)
    assert stats.current == 5
    assert stats.freezes == 0
    assert stats.frozen_days == (TODAY - timedelta(days=3),)
    assert stats.state == "lit"


def test_a_second_missed_day_without_a_freeze_left_starts_over_without_losing_the_record():
    stats = compute_streak(days(0, 1, 4, 5, 6), TODAY)
    assert stats.longest == 3
    assert stats.current == 2
    assert stats.freezes == 1


def test_a_week_of_practice_earns_another_freeze_up_to_two():
    week = compute_streak(days(*range(0, 7)), TODAY)
    assert (week.current, week.freezes) == (7, 2)
    month = compute_streak(days(*range(0, 40)), TODAY)
    assert month.current == 40
    assert month.freezes == 2
    assert week.next_freeze_in == 7


def test_the_next_freeze_is_counted_down_from_the_streak():
    stats = compute_streak(days(0, 1, 2), TODAY)
    assert stats.next_freeze_in == 4


def test_waiting_for_today_does_not_use_a_freeze_or_break_anything():
    stats = compute_streak(days(1, 2, 3), TODAY)
    assert (stats.current, stats.freezes, stats.state) == (3, 1, "waiting")
    assert stats.frozen_days == ()


def test_the_state_reads_lit_covered_waiting_fresh_or_new():
    assert compute_streak(days(0), TODAY).state == "lit"
    assert compute_streak(days(2, 3), TODAY).state == "covered"
    assert compute_streak(days(1, 2), TODAY).state == "waiting"
    assert compute_streak(days(5), TODAY).state == "fresh"
    assert compute_streak({}, TODAY).state == "new"


def test_days_after_the_day_being_asked_about_are_ignored():
    stats = compute_streak(days(-2, -1, 0, 1), TODAY)
    assert stats.current == 2
    assert stats.today_done is True


def test_old_freezes_drop_out_of_the_list_shown():
    far = {TODAY - timedelta(days=offset): 10 for offset in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 22]}
    stats = compute_streak(far, TODAY)
    assert stats.frozen_days == ()
    assert stats.current == 22
    assert stats.freezes == 2
