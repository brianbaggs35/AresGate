from typing import get_args

import pytest
from sqlalchemy.orm import Session

from app.ai import levels
from app.ai.triage import POLICIES
from app.events.event import Severity


def test_every_level_the_worker_follows_is_one_the_owner_can_choose() -> None:
    assert [level.key for level in levels.LEVELS] == list(POLICIES)
    assert set(get_args(levels.LevelKey)) == set(POLICIES)
    assert set(levels.LABELS) == set(POLICIES)


def test_the_levels_run_from_nothing_by_itself_to_the_most() -> None:
    assert [level.per_hour for level in levels.LEVELS] == [0, 6, 20, 60, 150]
    assert [level.label for level in levels.LEVELS] == [
        "Very low",
        "Low",
        "Medium",
        "High",
        "Maximum",
    ]


class TestWhatEachLevelSays:
    def said(self, key: str) -> str:
        return next(level.summary for level in levels.LEVELS if level.key == key)

    def test_the_lowest_reads_nothing_by_itself_but_still_answers_what_is_asked(self) -> None:
        said = self.said("very_low")

        assert "Reads nothing by itself" in said
        assert "Start investigating" in said
        assert "Assistant" in said

    def test_low_reads_the_serious_ones_once(self) -> None:
        said = self.said("low")

        assert "incidents rated high or higher" in said
        assert "up to 6 an hour" in said
        assert "Reads each one once." in said

    def test_medium_reads_one_again_when_it_has_grown(self) -> None:
        said = self.said("medium")

        assert "incidents rated medium or higher" in said
        assert "up to 20 an hour" in said
        assert "4 times the signals it had" in said
        assert "not within 15 minutes" in said

    def test_high_reads_the_minor_ones_too(self) -> None:
        said = self.said("high")

        assert "incidents rated low or higher" in said
        assert "2 times the signals" in said

    def test_maximum_reads_everything_and_reads_it_again_sooner(self) -> None:
        said = self.said("maximum")

        assert "every incident, even the least serious" in said
        assert "up to 150 an hour" in said
        assert "1.5 times the signals" in said

    @pytest.mark.parametrize("key", list(POLICIES))
    def test_it_says_nothing_the_worker_does_not_do(self, key: str) -> None:
        policy = POLICIES[key]
        said = self.said(key)

        if policy.minimum is not None and policy.minimum > Severity.INFO:
            assert policy.minimum.name.lower() in said
        assert (str(policy.per_hour) in said) == (policy.minimum is not None)


class TestChoosing:
    def test_it_is_medium_until_the_owner_says_otherwise(self, session: Session) -> None:
        assert levels.current(session) == "medium"

    def test_a_choice_is_kept_and_says_what_it_replaced(self, session: Session) -> None:
        assert levels.choose(session, "low") == ("medium", "low")
        assert levels.choose(session, "maximum") == ("low", "maximum")

        assert levels.current(session) == "maximum"
