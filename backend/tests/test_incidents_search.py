from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.incidents import search
from app.incidents.search import Context, SearchError
from app.models import Device, DeviceAddress, Incident, IncidentSignal

NOW = datetime(2026, 10, 27, 15, 30, tzinfo=UTC)
HALIFAX = ZoneInfo("America/Halifax")
CONTEXT = Context(zone=UTC, now=NOW)

# 203.0.113.0/24 is for examples and so are the others.
ATTACKER = "203.0.113.7"
SCANNER = "198.51.100.9"
DEVICE = "192.168.1.20"
V6 = "2001:db8::5"


def parse(text: str, context: Context = CONTEXT) -> search.Search:
    return search.parse(text, context)


def refused(text: str, context: Context = CONTEXT) -> str:
    with pytest.raises(SearchError) as error:
        parse(text, context)
    return str(error.value)


def incident(session: Session, name: str, **changes: object) -> Incident:
    fields: dict[str, object] = {
        "subject": name,
        "title": f"Incident {name}",
        "severity": 2,
        "confidence": 50,
        "status": "open",
        "first_seen_at": NOW - timedelta(hours=2),
        "last_seen_at": NOW - timedelta(hours=1),
        "signal_count": 3,
        "sources": ["wazuh"],
        "addresses": [],
        "ports": [],
        "activities": [],
        "top_source": "wazuh",
        "top_summary": "An alert",
        "banned": False,
        "verdict": None,
        "waves": 1,
    }
    fields.update(changes)
    found = Incident(**fields)
    session.add(found)
    session.flush()
    return found


@pytest.fixture
def incidents(session: Session) -> dict[str, Incident]:
    """Four incidents that differ in every way the language can ask about."""
    attack = incident(
        session,
        ATTACKER,
        title="Brute force on ssh (203.0.113.7)",
        severity=3,
        confidence=80,
        sources=["crowdsec", "opnsense", "wazuh"],
        addresses=[ip_address(ATTACKER), ip_address(DEVICE)],
        ports=[22],
        banned=True,
        activities=["brute_force"],
        signal_count=9,
        top_summary="Ban for ssh-bruteforce",
        first_seen_at=NOW - timedelta(hours=2),
        last_seen_at=NOW - timedelta(minutes=50),
    )
    scan = incident(
        session,
        SCANNER,
        title="Port scan (198.51.100.9)",
        severity=1,
        confidence=30,
        addresses=[ip_address(SCANNER)],
        ports=[80, 443, 8080],
        activities=["scan"],
        status="resolved",
        verdict="not_suspicious",
        first_seen_at=NOW - timedelta(days=3, hours=1),
        last_seen_at=NOW - timedelta(days=3),
    )
    rule = incident(
        session,
        "rule:wazuh:5710",
        title="Rule 5710 fired",
        severity=2,
        confidence=55,
        status="investigating",
        signal_count=1,
        last_seen_at=NOW - timedelta(minutes=30),
        first_seen_at=NOW - timedelta(minutes=30),
    )
    six = incident(
        session,
        V6,
        title="Probing from IPv6",
        severity=4,
        confidence=95,
        sources=["opnsense"],
        addresses=[ip_address(V6)],
        status="dismissed",
        verdict="threat",
        last_seen_at=NOW - timedelta(days=40),
        first_seen_at=NOW - timedelta(days=41),
    )
    session.add_all(
        [
            IncidentSignal(
                incident_id=attack.id,
                event_id=1,
                occurred_at=NOW - timedelta(hours=1),
                source="opnsense",
                kind="alert",
                severity=3,
                summary="A scan",
                signature="ET SCAN Nmap Scripting Engine",
            ),
            IncidentSignal(
                incident_id=scan.id,
                event_id=2,
                occurred_at=NOW - timedelta(days=3),
                source="wazuh",
                kind="alert",
                severity=1,
                summary="A probe",
                signature=None,
            ),
        ]
    )
    nas = Device(
        mac="aa:bb:cc:00:11:22",
        hostname="nas",
        vendor="Synology",
        first_seen_at=NOW,
        last_seen_at=NOW,
    )
    session.add(nas)
    session.flush()
    session.add(
        DeviceAddress(
            device_id=nas.id, address=ip_address(DEVICE), first_seen_at=NOW, last_seen_at=NOW
        )
    )
    session.commit()
    return {"attack": attack, "scan": scan, "rule": rule, "six": six}


NAMES = {ATTACKER: "attack", SCANNER: "scan", "rule:wazuh:5710": "rule", V6: "six"}


def found(session: Session, text: str, context: Context = CONTEXT) -> set[str]:
    """Which of the four a search finds, by the names they have in the fixture."""
    subjects = session.scalars(
        select(Incident.subject).where(*parse(text, context).conditions())
    ).all()
    return {NAMES[subject] for subject in subjects}


class TestWhatItUnderstands:
    def test_an_empty_search_asks_for_nothing(self) -> None:
        assert parse("").terms == ()
        assert parse("   \n ").conditions() == []

    def test_each_term_says_what_it_was_understood_as_and_where_it_was(self) -> None:
        terms = parse('ssh -source:wazuh severity>=high  "port scan"').terms
        assert [(term.field, term.negated, term.label) for term in terms] == [
            (None, False, "Contains: ssh"),
            ("source", True, "Not source: Wazuh"),
            ("severity", False, "Severity: at least high"),
            (None, False, "Contains: port scan"),
        ]
        text = 'ssh -source:wazuh severity>=high  "port scan"'
        assert [text[term.start : term.end] for term in terms] == [
            "ssh",
            "-source:wazuh",
            "severity>=high",
            '"port scan"',
        ]

    def test_it_can_say_whether_a_field_is_in_it(self) -> None:
        found = parse("status:open ssh")
        assert found.names("status")
        assert not found.names("source")

    def test_names_are_not_case_sensitive_and_some_have_shorter_ones(self) -> None:
        labels = [term.label for term in parse("SEVERITY:High sev:low ip:10.0.0.1 conf>40").terms]
        assert labels == [
            "Severity: high",
            "Severity: low",
            "Address: 10.0.0.1",
            "Confidence: over 40",
        ]

    def test_a_whole_address_is_an_address_even_where_it_looks_like_a_field(self) -> None:
        labels = [term.label for term in parse("fe80::1 dead:beef::1 10.0.0.0/8").terms]
        assert labels == [
            "Address: fe80::1",
            "Address: dead:beef::1",
            "Address: 10.0.0.0/8",
        ]

    def test_an_address_with_bits_past_the_range_is_the_range(self) -> None:
        assert parse("address:203.0.113.77/24").terms[0].label == "Address: 203.0.113.0/24"

    def test_a_quoted_phrase_is_text_even_when_it_looks_like_something_else(self) -> None:
        terms = parse('"severity:high" "10.0.0.1" "a,b"').terms
        assert [(term.field, term.label) for term in terms] == [
            (None, "Contains: severity:high"),
            (None, "Contains: 10.0.0.1"),
            (None, "Contains: a,b"),
        ]

    def test_a_choice_that_is_made_twice_is_made_once(self) -> None:
        labels = [
            term.label for term in parse("status:open,open port:22,22 source:wazuh,Wazuh").terms
        ]
        assert labels == ["Status: open", "Port: 22", "Source: Wazuh"]

    def test_a_quoted_value_can_hold_spaces(self) -> None:
        assert parse('signature:"ET SCAN"').terms[0].label == "Signature: ET SCAN"


class TestWhatItFinds:
    def test_text_is_looked_for_in_the_title_the_subject_and_the_strongest_signal(
        self, session: Session, incidents: dict[str, Incident]
    ) -> None:
        assert found(session, "brute") == {"attack"}
        assert found(session, "BRUTE") == {"attack"}
        assert found(session, "5710") == {"rule"}
        assert found(session, "ssh-bruteforce") == {"attack"}
        assert found(session, "ipv6") == {"six"}
        assert found(session, "nothing-says-this") == set()

    def test_text_is_only_ever_a_value(
        self, session: Session, incidents: dict[str, Incident]
    ) -> None:
        # Not wildcards and not a way out of the quotes.
        assert found(session, "%") == set()
        assert found(session, "_") == set()
        assert found(session, "5710%") == set()
        assert found(session, "';--") == set()
        assert found(session, "\\") == set()

    def test_several_terms_all_have_to_be_true(
        self, session: Session, incidents: dict[str, Incident]
    ) -> None:
        assert found(session, "source:wazuh status:open") == {"attack"}
        assert found(session, "source:wazuh status:open,resolved") == {"attack", "scan"}
        assert found(session, "source:wazuh status:dismissed") == set()

    def test_a_minus_turns_a_term_around(
        self, session: Session, incidents: dict[str, Incident]
    ) -> None:
        assert found(session, "-source:wazuh") == {"six"}
        assert found(session, "-brute") == {"scan", "rule", "six"}
        assert found(session, "-status:open,investigating") == {"scan", "six"}

    def test_a_whole_address_finds_the_incidents_that_name_it(
        self, session: Session, incidents: dict[str, Incident]
    ) -> None:
        assert found(session, ATTACKER) == {"attack"}
        # Not only the subject: any address that is in it.
        assert found(session, f"address:{DEVICE}") == {"attack"}
        assert found(session, "address:198.51.100.10") == set()
        assert found(session, V6) == {"six"}
        assert found(session, "address:2001:DB8:0:0:0:0:0:5") == {"six"}

    def test_a_range_finds_the_incidents_with_an_address_in_it(
        self, session: Session, incidents: dict[str, Incident]
    ) -> None:
        assert found(session, "address:203.0.113.0/24") == {"attack"}
        assert found(session, "src:192.168.0.0/16") == {"attack"}
        assert found(session, "address:198.51.100.0/24,203.0.113.0/24") == {"attack", "scan"}
        assert found(session, "address:2001:db8::/32") == {"six"}
        # A range of the other kind of address holds none of them, which is not an error.
        assert found(session, "address:10.0.0.0/8") == set()
        assert found(session, "-address:0.0.0.0/0") == {"rule", "six"}

    def test_a_source_is_found_by_its_key_or_its_name(
        self, session: Session, incidents: dict[str, Incident]
    ) -> None:
        assert found(session, "source:crowdsec") == {"attack"}
        assert found(session, "source:OPNsense") == {"attack", "six"}
        assert found(session, "program:opnsense,crowdsec") == {"attack", "six"}

    def test_severity_can_be_matched_or_compared(
        self, session: Session, incidents: dict[str, Incident]
    ) -> None:
        assert found(session, "severity:medium") == {"rule"}
        assert found(session, "severity:low,critical") == {"scan", "six"}
        assert found(session, "severity>=high") == {"attack", "six"}
        assert found(session, "severity>high") == {"six"}
        assert found(session, "severity<=low") == {"scan"}
        assert found(session, "severity<medium") == {"scan"}
        assert found(session, "severity=high") == {"attack"}

    def test_amounts_can_be_compared(
        self, session: Session, incidents: dict[str, Incident]
    ) -> None:
        assert found(session, "confidence>=80") == {"attack", "six"}
        assert found(session, "confidence:55") == {"rule"}
        assert found(session, "confidence<50") == {"scan"}
        assert found(session, "signals>3") == {"attack"}
        assert found(session, "signals<=1") == {"rule"}

    def test_status_and_verdict(self, session: Session, incidents: dict[str, Incident]) -> None:
        assert found(session, "status:resolved") == {"scan"}
        assert found(session, "status:open,investigating") == {"attack", "rule"}
        assert found(session, "verdict:threat") == {"six"}
        assert found(session, "verdict:not-suspicious") == {"scan"}
        assert found(session, "verdict:none") == {"attack", "rule"}
        # Having no verdict is a verdict too, so turning it around still finds the others.
        assert found(session, "-verdict:none") == {"scan", "six"}
        assert found(session, "-verdict:threat") == {"attack", "scan", "rule"}

    def test_activity(self, session: Session, incidents: dict[str, Incident]) -> None:
        assert found(session, "activity:scan") == {"scan"}
        assert found(session, "activity:brute-force") == {"attack"}
        assert found(session, "activity:scan,brute_force") == {"attack", "scan"}

    def test_a_signature_is_one_that_a_signal_of_the_incident_has(
        self, session: Session, incidents: dict[str, Incident]
    ) -> None:
        assert found(session, "signature:nmap") == {"attack"}
        assert found(session, 'sig:"ET SCAN"') == {"attack"}
        assert found(session, "signature:%") == set()
        assert found(session, "-signature:nmap") == {"scan", "rule", "six"}

    def test_a_device_is_found_by_the_name_the_maker_or_the_hardware_address(
        self, session: Session, incidents: dict[str, Incident]
    ) -> None:
        assert found(session, "device:nas") == {"attack"}
        assert found(session, "device:SYNO") == {"attack"}
        assert found(session, "device:aa:bb:cc") == {"attack"}
        assert found(session, "device:printer") == set()

    def test_ports(self, session: Session, incidents: dict[str, Incident]) -> None:
        assert found(session, "port:22") == {"attack"}
        assert found(session, "port:443") == {"scan"}
        assert found(session, "port:22,80") == {"attack", "scan"}
        assert found(session, "port:23") == set()

    def test_banned(self, session: Session, incidents: dict[str, Incident]) -> None:
        assert found(session, "banned:yes") == {"attack"}
        assert found(session, "banned:true") == {"attack"}
        assert found(session, "banned:no") == {"scan", "rule", "six"}
        assert found(session, "-banned:yes") == {"scan", "rule", "six"}

    def test_since_is_what_was_going_on_after_a_time(
        self, session: Session, incidents: dict[str, Incident]
    ) -> None:
        assert found(session, "since:1h") == {"attack", "rule"}
        assert found(session, "since:45m") == {"rule"}
        assert found(session, "since:7d") == {"attack", "scan", "rule"}
        assert found(session, "since:2w") == {"attack", "scan", "rule"}
        assert found(session, "since:2026-10-27") == {"attack", "rule"}
        assert found(session, "since:2026-10-27T14:50:00Z") == {"rule"}
        assert found(session, "since:2026-10-27T10:50:00-04:00") == {"rule"}

    def test_before_is_what_began_before_a_time(
        self, session: Session, incidents: dict[str, Incident]
    ) -> None:
        assert found(session, "before:1h") == {"attack", "scan", "six"}
        assert found(session, "before:30d") == {"six"}
        assert found(session, "since:7d before:1h") == {"attack", "scan"}

    def test_today_and_yesterday_are_where_the_person_is(
        self, session: Session, incidents: dict[str, Incident]
    ) -> None:
        # 15:30 UTC is 12:30 in Halifax (UTC-3 on this date), so today began at 03:00 UTC there.
        halifax = Context(zone=HALIFAX, now=NOW)
        assert search.moment("today", halifax)[0] == datetime(2026, 10, 27, 3, tzinfo=UTC)
        assert search.moment("Yesterday", halifax)[0] == datetime(2026, 10, 26, 3, tzinfo=UTC)
        assert parse("since:today", halifax).terms[0].label == "Going on since: today"
        assert found(session, "since:today", halifax) == {"attack", "rule"}
        assert found(session, "since:yesterday", halifax) == {"attack", "rule"}
        # An hour past midnight UTC is still the evening of the 26th in Halifax.
        late = Context(zone=HALIFAX, now=datetime(2026, 10, 27, 1, tzinfo=UTC))
        assert search.moment("today", late)[0] == datetime(2026, 10, 26, 3, tzinfo=UTC)
        assert search.moment("today", Context(zone=UTC, now=late.now))[0] == datetime(
            2026, 10, 27, tzinfo=UTC
        )

    def test_a_date_without_a_zone_is_in_the_persons_zone(self) -> None:
        halifax = Context(zone=HALIFAX, now=NOW)
        assert parse("since:2026-10-01", halifax).terms[0].label == (
            "Going on since: 2026-10-01 00:00"
        )
        assert parse('since:"2026-10-01 08:30"', halifax).terms[0].label == (
            "Going on since: 2026-10-01 08:30"
        )
        # With one of its own, it is shown where the person is.
        assert parse("before:2026-10-01T12:00:00Z", halifax).terms[0].label == (
            "Began before: 2026-10-01 09:00"
        )

    def test_durations_are_shown_as_they_were_typed(self) -> None:
        assert parse("since:6H").terms[0].label == "Going on since: 6h ago"


class TestWhatItRefuses:
    def test_a_field_nobody_knows_suggests_the_nearest(self) -> None:
        assert refused("sevrity:high") == (
            'There\'s no search field called "sevrity". Did you mean "severity"? '
            "To look for the text itself, put it in quotes."
        )
        assert 'Did you mean "address"?' in refused("ipp:1.2.3.4")

    def test_a_field_nobody_knows_and_nothing_near(self) -> None:
        message = refused("zzzzzz:1")
        assert "Did you mean" not in message
        assert '"zzzzzz"' in message

    def test_a_field_without_a_value(self) -> None:
        assert "needs a value right after it, such as severity:value" in refused("severity:")
        assert "put it in quotes" in refused("ET:")
        assert refused("status:,") == '"status:" needs a value after it.'

    def test_a_space_after_the_colon_is_a_field_without_a_value(self) -> None:
        assert "needs a value right after it" in refused("severity: high")

    def test_a_quote_that_is_not_closed(self) -> None:
        assert refused('ssh "port scan') == (
            "The quote at character 5 needs a space before it or a quote to close it."
        )

    def test_a_quote_that_touches_a_word(self) -> None:
        assert "The quote at character" in refused('ab"cd"')
        assert "The quote at character" in refused('"ab"cd')
        assert "The quote at character" in refused('severity:"high')

    def test_a_minus_with_nothing_after_it(self) -> None:
        assert refused("ssh -") == "A minus sign turns a term around, so it needs one after it."

    def test_something_that_is_not_an_address(self) -> None:
        assert refused("address:999.1.1.1") == (
            '"999.1.1.1" isn\'t an address or a range of them, such as 203.0.113.0/24.'
        )
        assert refused("address:10.0.0.0/33").startswith('"10.0.0.0/33" isn\'t an address')

    def test_a_source_nobody_has_set_up_or_knows(self) -> None:
        assert refused("source:snort") == (
            'No integration is called "snort". Try opnsense, ntopng, wazuh or crowdsec.'
        )

    def test_a_severity_that_is_not_one(self) -> None:
        assert refused("severity:urgent") == (
            '"urgent" isn\'t a severity. Use info, low, medium, high or critical.'
        )
        assert "isn't a severity" in refused("severity>=urgent")

    def test_a_comparison_takes_one_value(self) -> None:
        assert refused("severity>=high,low") == '"severity>=" takes one value, not a list.'
        assert refused("confidence>=1,2") == '"confidence>=" takes one value, not a list.'

    def test_a_comparison_of_something_that_is_not_an_amount(self) -> None:
        assert refused("status>open") == '"status" is matched with "status:", not ">".'
        assert refused("source<=wazuh").startswith('"source" is matched with')

    def test_an_amount_that_is_not_one(self) -> None:
        assert refused("confidence>=lots") == (
            '"confidence" is a whole number from 0 to 100, not "lots".'
        )
        assert refused("confidence>=101").startswith('"confidence" is a whole number')
        assert refused("signals>=-1").startswith('"signals" is a whole number from 0 to')
        assert refused("signals>=٣").startswith('"signals" is a whole number')

    def test_a_status_and_a_verdict_and_an_activity_that_are_not_one(self) -> None:
        assert refused("status:finished") == (
            '"finished" isn\'t a status. Use open, investigating, resolved or dismissed.'
        )
        assert "isn't something you can say of an incident" in refused("verdict:bad")
        assert "isn't a kind of activity" in refused("activity:dancing")

    def test_a_port_that_is_not_one(self) -> None:
        assert refused("port:0") == '"0" isn\'t a port, which is a number from 1 to 65535.'
        assert "isn't a port" in refused("port:65536")
        assert "isn't a port" in refused("port:ssh")

    def test_banned_is_yes_or_no(self) -> None:
        assert refused("banned:maybe") == '"maybe" isn\'t yes or no.'

    def test_a_time_that_is_not_one(self) -> None:
        assert refused("since:soon") == (
            '"soon" isn\'t a time. Try 6h, 2d, today, yesterday or 2026-10-27.'
        )
        assert "isn't a time" in refused("since:2026-13-45")
        assert refused("before:1999-01-01") == '"1999-01-01" isn\'t a year from 2000 to 2100.'

    def test_a_value_that_is_too_long_to_be_anything(self) -> None:
        assert refused(f"signature:{'a' * 101}") == '"signature" takes at most 100 characters.'
        assert refused("a" * 101) == '"text" takes at most 100 characters.'

    def test_too_many_choices(self) -> None:
        assert refused(f"port:{','.join(str(n) for n in range(1, 10))}") == (
            '"port" takes at most 8 choices.'
        )

    def test_too_long_or_too_many(self) -> None:
        assert refused("a" * 501) == "A search can be at most 500 characters."
        assert refused(" ".join(["a"] * 13)) == "A search can have at most 12 terms."
        assert len(parse(" ".join(["a"] * 12)).terms) == 12

    def test_characters_that_are_not_text(self) -> None:
        assert refused("ssh\x00") == "A search can't hold control characters."
        assert refused("ssh\x1b[0m") == "A search can't hold control characters."
        assert refused("ssh\ud800") == "A search can't hold control characters."
