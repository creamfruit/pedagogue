from app.schemas.schemas import OnboardingStatus


def status(**overrides):
    values = dict(
        profile_complete=True,
        genres_chosen=0,
        composers_chosen=0,
        techniques_rated=17,
        top_ten_logged=1,
        tier_quiz_complete=True,
        tastes_complete=False,
        complete=False,
    )
    values.update(overrides)
    return OnboardingStatus(**values)


def test_tastes_step_waits_until_finished():
    assert status().next_step == "tastes"


def test_finishing_without_a_composer_reaches_the_dashboard():
    assert status(genres_chosen=2, tastes_complete=True, complete=True).next_step == "done"


def test_finishing_with_nothing_picked_still_completes():
    assert status(tastes_complete=True, complete=True).next_step == "done"


def test_next_step_is_serialised():
    assert status().model_dump()["next_step"] == "tastes"
