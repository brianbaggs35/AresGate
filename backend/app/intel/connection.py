"""Testing the VirusTotal connection, and what VirusTotal's limits say of it.

A test is one lookup of a public address that always has a report, so it spends one of the lookups
the key allows. It is made by hand, through the same budget as every other lookup, and never on a
timer. Its answer is kept like any other, but a test is always sent: it is the key that is being
checked, so an answer kept from before doesn't stand in for it. While VirusTotal's daily quota is
used up, nothing is sent and the connection is held as it was. A limit on a free key is no sign of
a broken connection: VirusTotal answered, so a quota error and a request to slow down are both
taken as VirusTotal accepting the key, since the limits are the key's own, and the test passes.
"""

from collections.abc import Mapping
from datetime import datetime
from ipaddress import IPv4Address

import anyio.from_thread
from sqlalchemy.orm import Session

from app.integrations import netguard, probes, registry, service
from app.integrations.client import ApiClient, Recorder, Target
from app.integrations.probes import Verdict
from app.intel import budget, greynoise, store, subjects, virustotal
from app.models import IntegrationConnection

CONNECTION = registry.VIRUSTOTAL.connections[0]
# A public address that always has a report, so that a key is tested on one that is known.
TEST_ADDRESS = IPv4Address("8.8.8.8")
# How a test's lookup is kept, so that it is told apart from a lookup of an incident's address.
TEST_KIND = "test"

DAILY_HELD = (
    "VirusTotal's daily limit is reached, so the key wasn't tested again. Testing resumes at "
    "00:00 UTC."
)
DAILY_ACCEPTED = (
    "VirusTotal accepted the key, but its daily limit is reached. It resets at 00:00 UTC."
)
THROTTLED = (
    "VirusTotal accepted the key, but asked for fewer requests for a minute. "
    "Lookups resume after that."
)


def verdict_for(answer: virustotal.Answer, options: Mapping[str, str | int]) -> Verdict:
    """What an answer says of the connection."""
    if isinstance(answer, virustotal.Failed):
        return Verdict(False, answer.message)
    if isinstance(answer, virustotal.Throttled):
        return Verdict(True, THROTTLED)
    if isinstance(answer, virustotal.Limited):
        return Verdict(True, DAILY_ACCEPTED)
    level = "premium" if options.get("tier") == "premium" else "free"
    return Verdict(True, f"VirusTotal accepted the key. It is set to the {level} access level.")


def remember(row: IntegrationConnection, answer: virustotal.Answer, now: datetime) -> None:
    """Keeps what a limit says of the connection. VirusTotal answered, so the connection isn't
    failing. A lookup that failed for another reason is left for a test to judge."""
    if isinstance(answer, virustotal.Limited | virustotal.Throttled):
        service.record_attempt(row, verdict_for(answer, row.options), now)


def test_key(db: Session, target: Target, recorder: Recorder, now: datetime) -> Verdict:
    """Tests the key of VirusTotal, or of GreyNoise (``_test_greynoise``), with one lookup, through
    the budget. For VirusTotal, while its daily quota holds,
    nothing is sent and the connection is held as it was. Raises ``budget.Wait`` when the limits
    don't allow a test now, which they don't for a minute after VirusTotal asked for fewer requests.
    A test that VirusTotal itself answers with a limit is a pass: it was reached and took the key.
    """
    if target.integration == greynoise.PROVIDER:
        return _test_greynoise(db, target, recorder, now)
    try:
        lookup_id = budget.reserve(
            db,
            virustotal.PROVIDER,
            budget.level_of(target.options),
            now,
            kind=TEST_KIND,
            subject=str(TEST_ADDRESS),
        )
    except budget.Paused as held:
        if not held.pause.daily:
            raise
        return Verdict(True, DAILY_HELD, held=True)
    db.commit()
    policy = service.policy_for(CONNECTION, netguard.HOME_NETWORK)
    subject = subjects.of_address(TEST_ADDRESS)
    answer = anyio.from_thread.run(virustotal.ask, target, recorder, policy, subject, now)
    store.finish(db, lookup_id, subject, answer, now)
    db.commit()
    return verdict_for(answer, target.options)


GREYNOISE_CONNECTION = registry.GREYNOISE.connections[0]
GREYNOISE_THROTTLED = "GreyNoise answered, but its limit is reached. Lookups resume in an hour."


def greynoise_verdict(answer: greynoise.Answer, options: Mapping[str, str | int]) -> Verdict:
    """What GreyNoise's answer to a test lookup says of the connection."""
    if isinstance(answer, greynoise.Failed):
        return Verdict(False, answer.message)
    if isinstance(answer, greynoise.Throttled):
        return Verdict(True, GREYNOISE_THROTTLED)
    if greynoise.plan_of(options) == greynoise.ANONYMOUS:
        return Verdict(True, "GreyNoise answered. With no account it allows 10 lookups a day.")
    return Verdict(True, "GreyNoise accepted the key. The free plan allows 50 searches a week.")


async def _ping(target: Target, recorder: Recorder) -> Verdict:
    policy = service.policy_for(GREYNOISE_CONNECTION, netguard.HOME_NETWORK)
    async with ApiClient(target, recorder, policy) as client:
        return await probes.run(probes.greynoise_ping, client, target)


def _test_greynoise(db: Session, target: Target, recorder: Recorder, now: datetime) -> Verdict:
    """Tests a GreyNoise connection. A subscription's key is pinged, which asks nothing about an
    address and counts as no lookup. With a free account's key or none, one lookup of a public
    address that is always in GreyNoise's dataset is made through the budget, since that is the
    only request the Community API has, and it spends one of the few lookups a day or a week
    allows. Raises ``budget.Wait`` when the limits don't allow a lookup now."""
    if greynoise.plan_of(target.options) == greynoise.SUBSCRIPTION:
        return anyio.from_thread.run(_ping, target, recorder)
    lookup_id = budget.reserve(
        db,
        greynoise.PROVIDER,
        budget.greynoise_level_of(target.options),
        now,
        kind=TEST_KIND,
        subject=str(TEST_ADDRESS),
    )
    db.commit()
    policy = service.policy_for(GREYNOISE_CONNECTION, netguard.HOME_NETWORK)
    subject = subjects.of_address(TEST_ADDRESS)
    answer = anyio.from_thread.run(greynoise.ask, target, recorder, policy, subject, now)
    store.finish(db, lookup_id, subject, answer, now)
    db.commit()
    return greynoise_verdict(answer, target.options)
