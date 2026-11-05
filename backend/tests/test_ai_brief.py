"""What every AI analyst of AresGate is told before it is asked anything."""

from sqlalchemy.orm import Session

from app.ai import brief
from app.ai.redaction import Level, Redactor
from app.threats.settings import Tuning
from tests.test_ai_service import NOW


def test_it_comes_with_the_playbook_and_what_the_owner_said_of_their_network(
    session: Session,
) -> None:
    tuning = Tuning(exposure="some", exposed_ports=(22,), notes="A camera at 192.168.1.50.")

    said = brief.start(Redactor(session, Level.BALANCED, NOW), tuning)

    assert said.startswith(brief.PLAYBOOK)
    assert "on these ports: 22." in said
    assert "In their own words: A camera at HOST_" in said
    assert "192.168.1.50" not in said


def test_without_notes_there_are_none_of_their_words(session: Session) -> None:
    said = brief.start(Redactor(session, Level.BALANCED, NOW), Tuning())

    assert "In their own words" not in said
    assert "hasn't said" in said


def test_it_is_long_enough_for_a_provider_to_cache_it() -> None:
    # OpenAI's GPT-6 models don't cache a prompt shorter than 1,024 tokens; a token is about four
    # characters, and the system notice and the question come with it.
    assert len(brief.PLAYBOOK) > 2000
