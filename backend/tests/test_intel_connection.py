"""What VirusTotal's answers say of the connection, when a test or a search brings them."""

from datetime import UTC, datetime, timedelta

from app.intel import connection, virustotal
from app.models import IntegrationConnection

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
FAILURE = "VirusTotal answered HTTP 500."


def connection_row(
    last_success_at: datetime | None = None, last_error: str | None = None
) -> IntegrationConnection:
    return IntegrationConnection(
        integration="virustotal",
        connection="api",
        base_url="https://www.virustotal.com",
        tls_mode="system",
        options={"tier": "free"},
        last_success_at=last_success_at,
        last_error=last_error,
    )


def test_an_answer_accepts_the_key_at_the_access_level_chosen() -> None:
    free = connection.verdict_for(virustotal.Unknown(), {"tier": "free"})
    premium = connection.verdict_for(virustotal.Unknown(), {"tier": "premium"})

    assert (free.ok, free.held) == (True, False)
    assert free.message == "VirusTotal accepted the key. It is set to the free access level."
    assert premium.message == (
        "VirusTotal accepted the key. It is set to the premium access level."
    )


def test_a_limit_of_the_day_keeps_the_key_and_says_when_it_resets() -> None:
    verdict = connection.verdict_for(virustotal.Limited(until=NOW), {"tier": "free"})

    assert (verdict.ok, verdict.held) == (True, False)
    assert verdict.message == connection.DAILY_ACCEPTED


def test_too_many_requests_is_a_key_that_was_accepted_and_asked_to_slow_down() -> None:
    verdict = connection.verdict_for(virustotal.Throttled(until=NOW), {"tier": "free"})

    assert (verdict.ok, verdict.held) == (True, False)
    assert verdict.message == connection.THROTTLED


def test_a_failure_is_a_failed_key_with_its_reason() -> None:
    verdict = connection.verdict_for(virustotal.Failed(FAILURE), {"tier": "free"})

    assert (verdict.ok, verdict.message) == (False, FAILURE)


def test_a_limit_of_the_day_counts_as_a_success_with_no_error() -> None:
    row = connection_row()

    connection.remember(row, virustotal.Limited(until=NOW), NOW)

    assert row.last_success_at == NOW
    assert row.last_error is None


def test_too_many_requests_counts_as_a_success_with_no_error() -> None:
    earlier = NOW - timedelta(days=1)
    row = connection_row(last_success_at=earlier, last_error="Earlier trouble.")

    connection.remember(row, virustotal.Throttled(until=NOW + virustotal.THROTTLE), NOW)

    assert row.last_attempt_at == NOW
    assert row.last_success_at == NOW
    assert row.last_error is None


def test_an_answer_that_is_not_a_limit_is_left_for_a_test_to_judge() -> None:
    earlier = NOW - timedelta(days=1)
    row = connection_row(last_success_at=earlier)

    connection.remember(row, virustotal.Unknown(), NOW)
    connection.remember(row, virustotal.Failed(FAILURE), NOW)

    assert row.last_attempt_at is None
    assert row.last_success_at == earlier
