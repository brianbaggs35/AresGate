"""Incidents: the alerts, bans and other signals from every integration that belong together."""

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow

# What becomes of a column that names a row when that row is deleted.
SET_NULL = "SET NULL"
# What the person who looks after the network has decided about an incident.
STATUSES = ("open", "investigating", "resolved", "dismissed")


class Incident(Base):
    """Signals that belong together: the same address behind a scan that Suricata saw, Wazuh
    logged and CrowdSec banned. It says how serious that is and how sure AresGate is, and keeps
    the reasons, so a person (or the analyst) can see why and disagree.

    It is kept as a summary that grows with each signal, so that working out what a new signal
    changes never means reading the old ones again. The signals themselves are kept beside it
    (``IncidentSignal``) as a timeline, and outlive the events they came from."""

    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint("severity BETWEEN 0 AND 4", name="severity"),
        CheckConstraint("confidence BETWEEN 0 AND 100", name="confidence"),
        CheckConstraint(
            "status IN ('open', 'investigating', 'resolved', 'dismissed')", name="status"
        ),
        CheckConstraint(
            "verdict IS NULL OR verdict IN ('not_suspicious', 'low_priority', 'threat')",
            name="verdict",
        ),
        CheckConstraint(
            "ai_class IS NULL OR ai_class IN ('compromise', 'attack', 'probe', 'noise', 'unclear')",
            name="ai_class",
        ),
        CheckConstraint(
            "ai_confidence IS NULL OR ai_confidence BETWEEN 0 AND 100", name="ai_confidence"
        ),
        CheckConstraint(
            "ai_basis IS NULL OR ai_basis IN ('owner', 'reading', 'family')", name="ai_basis"
        ),
        Index("ix_incidents_last_seen_at", "last_seen_at"),
        Index("ix_incidents_family_id", "family_id"),
        Index("ix_incidents_family_key", "family_key"),
        Index("ix_incidents_chain_id", "chain_id"),
        CheckConstraint(
            "chain_role IS NULL OR chain_role IN ('attacker', 'callout')", name="chain_role"
        ),
        CheckConstraint(
            "chain_link IS NULL OR chain_link IN ('confirmed', 'inferred')", name="chain_link"
        ),
        Index("ix_incidents_subject_last_seen_at", "subject", "last_seen_at"),
        Index("ix_incidents_block_last_seen_at", "block", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # What the signals are about: the address that is the centre of them (an attacker's, or the
    # device an alert is about), or the rule that fired when they carry no address.
    subject: Mapped[str] = mapped_column(String(300))
    title: Mapped[str] = mapped_column(String(200))
    # The most serious signal's severity, on the scale in app/events/event.py.
    severity: Mapped[int] = mapped_column(SmallInteger)
    # How sure AresGate is that this is a real attack, from 0 to 100, and the reasons it adds up
    # to (see app/incidents/rules.py): a list of {rule, points, text}.
    confidence: Mapped[int] = mapped_column(SmallInteger)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16), default="open")
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    signal_count: Mapped[int] = mapped_column(Integer, default=0)
    # The integrations whose signals are in it, sorted.
    sources: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    # Every address in the signals, the first fifty of them, subject first.
    addresses: Mapped[list[IPv4Address | IPv6Address]] = mapped_column(ARRAY(INET), default=list)
    # The block of addresses the subject is in (its /24 or /64), where it is on the internet: the
    # neighbours that do the same thing are the same incident (see episode.py).
    block: Mapped[str | None] = mapped_column(String(64), default=None)
    # What kinds of activity its signals were (``scan``, ``brute_force``), sorted.
    activities: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    # How many bursts its signals came in, and which destination ports they touched, sorted. No
    # waves at all means it has not been worked out yet: the engine does it on its next run.
    waves: Mapped[int] = mapped_column(Integer, default=0)
    ports: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    # Facts about the strongest signal and the rest, kept so scoring needs no old signals.
    top_source: Mapped[str] = mapped_column(String(32))
    top_summary: Mapped[str] = mapped_column(String(500))
    banned: Mapped[bool] = mapped_column(default=False)
    # How many of the signals the owner has a verdict on, by verdict. A signal that is not
    # suspicious or low priority is listed and counted in ``signal_count``, but everything above
    # (the severity, the programs, the addresses) is about the ones that are not.
    verdict_counts: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    # How many of the signals the owner's noise filters set aside (see app/incidents/filters.py),
    # which are none of the above: they are not a verdict, and a verdict outranks a filter. They
    # are listed and counted like a muted one and leave everything else to the rest.
    filtered_count: Mapped[int] = mapped_column(Integer, default=0)
    # What the verdicts say of the incident as a whole: a real threat if any signal is, not
    # suspicious or low priority if every signal is, and none otherwise.
    verdict: Mapped[str | None] = mapped_column(String(16), default=None)
    # How many alerts another program also reported (the same flow, within moments of the first),
    # which are listed in the timeline but counted once: ``signal_count`` has the others.
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    # The stages of an attack its signals are (``recon``, ``access``, ``foothold``; see
    # app/threats/stages.py), sorted. An incident with more than one is a chain, and one with a
    # foothold is past the point of being only scanning.
    stages: Mapped[list[str]] = mapped_column(ARRAY(String(12)), default=list)
    # The family it belongs to (app/threats/families.py): incidents that say the same thing in
    # the same way, which an AI judges once for all of them. ``family_key`` is what makes a family
    # and is worked out as the incident changes; ``family_id`` follows it.
    family_key: Mapped[str | None] = mapped_column(String(40), default=None)
    family_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("incident_families.id", ondelete=SET_NULL), default=None
    )
    # The chain it is a step of (app/threats/chains.py): an outside address that got in by a flaw,
    # and the device it got into calling out afterwards, which are one attack across two devices.
    # ``chain_role`` says which step it is, ``chain_link`` whether the link was seen or only
    # inferred, and ``chain_reason`` says why in words.
    chain_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("incident_chains.id", ondelete=SET_NULL), default=None
    )
    chain_role: Mapped[str | None] = mapped_column(String(8), default=None)
    chain_link: Mapped[str | None] = mapped_column(String(9), default=None)
    chain_reason: Mapped[str | None] = mapped_column(String(300), default=None)
    # What is thought of it beyond the rules (app/threats/calls.py): what kind of thing it is, how
    # sure that is, and whose opinion it is: the owner's (of its family), the AI's reading of this
    # incident, or the AI's judgement of its family. Kept here so that counting is only columns.
    ai_class: Mapped[str | None] = mapped_column(String(12), default=None)
    ai_confidence: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    ai_basis: Mapped[str | None] = mapped_column(String(8), default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    # When someone last changed the status, and nothing before that.
    status_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class IncidentChain(Base):
    """An attack that crossed from the internet to a device and then out again: the incident about
    the outside address that got in, and the one about the device calling out afterwards, linked by
    the device and the time between them (see app/threats/chains.py). The steps are the incidents
    whose ``chain_id`` is this one."""

    __tablename__ = "incident_chains"
    __table_args__ = (Index("ix_incident_chains_device_last_seen_at", "device", "last_seen_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # The inside address of the device the attack went through.
    device: Mapped[str] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    # Whether a step that calls out was seen to do what a compromised device does (a beacon, a
    # command server), and not only to be talking to the internet after being attacked.
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    steps: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class AddressName(Base):
    """What an address on the internet is called, as its reverse lookup (PTR record) answered, kept
    so that the same address is asked about once a week and not each time a page is opened. A name
    of None is a lookup that was answered with no name, which is kept for a day."""

    __tablename__ = "address_names"

    address: Mapped[str] = mapped_column(String(45), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(253), default=None)
    looked_up_at: Mapped[datetime] = mapped_column(UTCDateTime)


class IncidentSignal(Base):
    """One event in an incident's timeline, as it was when it joined: copied, because incidents
    are kept after the events they came from have passed their retention period."""

    __tablename__ = "incident_signals"
    __table_args__ = (
        # An event belongs to one incident.
        UniqueConstraint("event_id", name="uq_incident_signals_event_id"),
        CheckConstraint(
            "verdict IS NULL OR verdict IN ('not_suspicious', 'low_priority', 'threat')",
            name="verdict",
        ),
        Index("ix_incident_signals_incident_id_occurred_at", "incident_id", "occurred_at"),
        Index("ix_incident_signals_verdict_rule_id", "verdict_rule_id"),
        # The few that have not had their evidence read yet, so that finding them stays cheap.
        Index(
            "ix_incident_signals_evidence_unread",
            "id",
            postgresql_where=text("evidence IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    incident_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("incidents.id", ondelete="CASCADE")
    )
    # Which event it was, while that is still stored: its id and time, which are its key.
    event_id: Mapped[int] = mapped_column(BigInteger)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    source: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(32))
    severity: Mapped[int] = mapped_column(SmallInteger)
    summary: Mapped[str] = mapped_column(String(500))
    signature: Mapped[str | None] = mapped_column(String(256), default=None)
    src_address: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET, default=None)
    src_port: Mapped[int | None] = mapped_column(Integer, default=None)
    dst_address: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET, default=None)
    dst_port: Mapped[int | None] = mapped_column(Integer, default=None)
    protocol: Mapped[str | None] = mapped_column(String(16), default=None)
    # What the owner's rules said of it when it joined, and which rule that was while it exists.
    # A verdict stays on a resolved incident as it was, whatever becomes of the rule.
    verdict: Mapped[str | None] = mapped_column(String(16), default=None)
    verdict_rule_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("verdict_rules.id", ondelete=SET_NULL), default=None
    )
    # Which of the owner's noise filters set it aside (``inside``, ``severity``; see
    # app/incidents/filters.py), when it did and no verdict decided otherwise. Like a verdict it
    # is listed in the timeline and counted, and leaves what the incident says to the rest.
    filtered_by: Mapped[str | None] = mapped_column(String(16), default=None)
    # Another program reported the same alert moments before (``Event.twin_of``): it is listed, and
    # what it adds (the program that agrees, a higher severity) counts, but it is not counted again.
    duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    # Which event it is a twin of, while a duplicate: the one the other program reported first,
    # which is the signal it is shown with (``Event.twin_of``).
    twin_of: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # What the program reported besides the facts above, boiled down to what is worth showing
    # (app/incidents/evidence.py), kept because the event's own record is not: it goes with the
    # event's retention. None until it has been read from the event, and ``{}`` where there is
    # nothing to show.
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), default=None)


class IncidentFamily(Base):
    """A kind of incident: the ones a program reported in the same words, about the same sort of
    place. Hundreds of port scans from hundreds of addresses are one family, and what an AI makes
    of the family is what it makes of all of them, so it is asked once. The owner can overrule it
    (``owner_call``), and what they say comes before anything the AI says."""

    __tablename__ = "incident_families"
    __table_args__ = (
        CheckConstraint("reach IN ('internet', 'network', 'rule')", name="reach"),
        CheckConstraint(
            "owner_call IS NULL OR owner_call IN ('background', 'watch')", name="owner_call"
        ),
        CheckConstraint(
            "ai_class IS NULL OR ai_class IN ('compromise', 'attack', 'probe', 'noise', 'unclear')",
            name="ai_class",
        ),
        CheckConstraint(
            "ai_confidence IS NULL OR ai_confidence BETWEEN 0 AND 100", name="ai_confidence"
        ),
        CheckConstraint("review IN ('pending', 'auto', 'agreed', 'disagreed')", name="review"),
        UniqueConstraint("key", name="uq_incident_families_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    # What makes it this family, a hash of the program, the words and the reach.
    key: Mapped[str] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(32))
    # What its incidents say, normalised so that an address or a count in it doesn't make a family
    # of its own, and where from: the internet, the owner's own network or a rule that names none.
    label: Mapped[str] = mapped_column(String(200))
    reach: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # The owner's word on the family: ``background`` sets all of it aside, ``watch`` never does.
    owner_call: Mapped[str | None] = mapped_column(String(10), default=None)
    owner_call_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # What the AI made of it the last time it was asked, when, and how many incidents it had then,
    # to tell when it has grown since.
    ai_class: Mapped[str | None] = mapped_column(String(12), default=None)
    ai_confidence: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    ai_reason: Mapped[str | None] = mapped_column(String(300), default=None)
    judged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    judged_incidents: Mapped[int] = mapped_column(Integer, default=0)
    call_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ai_calls.id", ondelete=SET_NULL), default=None
    )
    provider: Mapped[str | None] = mapped_column(String(32), default=None)
    model: Mapped[str | None] = mapped_column(String(128), default=None)
    # Whether the owner has to look at the AI's judgement before it counts (``pending``), it
    # counted at once and is listed to look at later (``auto``), or the owner agreed or disagreed
    # with it (app/review).
    review: Mapped[str] = mapped_column(String(10), default="auto", server_default="auto")
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # What its incidents were like when it was judged (app/threats/drift.py): the stages, the
    # destination ports, the devices and the number of addresses, to tell when it has changed since.
    judged_profile: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True), default=None
    )
    # What is different about it now compared with ``judged_profile``, and when that was first
    # noticed: none while it is as it was. The AI is asked about it again, and the owner told.
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), default=None)
    changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # When it was last compared, so that it is looked at no more often than needed.
    drift_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # A suggestion the owner said not now to (app/threats/learning.py): which call it was and how
    # many of the kind's incidents they had decided by then, so that it is offered again only
    # when they have decided twice as many.
    suggestion_dismissed: Mapped[str | None] = mapped_column(String(10), default=None)
    suggestion_dismissed_count: Mapped[int | None] = mapped_column(Integer, default=None)


class ThreatSettings(Base):
    """How the owner wants threats told from noise on their network: how sure it has to be of one,
    whether the AI may set things aside, and what their network is like, so that the AI is told
    what is normal there. There is only ever one row, and none until the owner first saves (the
    defaults are in app/threats/settings.py)."""

    __tablename__ = "threat_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("threat_from BETWEEN 1 AND 100", name="threat_from"),
        CheckConstraint("clear_from BETWEEN 50 AND 100", name="clear_from"),
        CheckConstraint("exposure IN ('none', 'some', 'unknown')", name="exposure"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1, autoincrement=False)
    # How sure (0 to 100) the rules, or the AI, have to be that it is real to call it a threat.
    threat_from: Mapped[int] = mapped_column(SmallInteger, default=65)
    # Whether the AI may set incidents aside as background, and how sure it has to be to.
    ai_may_clear: Mapped[bool] = mapped_column(Boolean, default=True)
    clear_from: Mapped[int] = mapped_column(SmallInteger, default=80)
    # Whether, while the AI is watching, an incident has to be agreed with by it to be a threat.
    ai_confirms: Mapped[bool] = mapped_column(Boolean, default=True)
    # What is reachable from the internet: ``none``, ``some`` (the ports) or ``unknown``.
    exposure: Mapped[str] = mapped_column(String(8), default="unknown")
    exposed_ports: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    # What else the owner wants the AI to know of their network, in their words.
    notes: Mapped[str] = mapped_column(String(500), default="")
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class NoiseSettings(Base):
    """How AresGate narrows what it asks about without anyone's verdict: how sure it has to be of
    an incident to ask, which signals it sets aside, how long a scan may pause before it is another
    incident, and how many low signals a thin incident needs. There is only ever one row, and none
    until the owner first saves (the defaults are in app/incidents/filters.py)."""

    __tablename__ = "noise_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="single_row"),
        CheckConstraint("confidence_floor BETWEEN 1 AND 100", name="confidence_floor"),
        CheckConstraint("scan_gap_hours BETWEEN 1 AND 24", name="scan_gap_hours"),
        CheckConstraint("brute_force_gap_hours BETWEEN 1 AND 24", name="brute_force_gap_hours"),
        CheckConstraint("thin_low_signals BETWEEN 1 AND 10", name="thin_low_signals"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1, autoincrement=False)
    # How sure AresGate has to be of an incident (0 to 100) for it to be asked about.
    confidence_floor: Mapped[int] = mapped_column(SmallInteger, default=35)
    # Whether signals between two addresses on the owner's own network are set aside, unless a
    # program banned something.
    quiet_inside: Mapped[bool] = mapped_column(Boolean, default=False)
    # For a program, the lowest severity (on the scale in app/events/event.py) that counts as a
    # signal. A program that is not here has the engine's own minimum.
    source_floors: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict)
    # How long a scan or a brute force may go quiet before its next signal is a new incident, in
    # hours. It applies to the signals that arrive after it is saved, not to the incidents made.
    scan_gap_hours: Mapped[int] = mapped_column(SmallInteger, default=4)
    brute_force_gap_hours: Mapped[int] = mapped_column(SmallInteger, default=6)
    # The fewest signals an incident of one program's low-severity signals needs before it is asked
    # about. One is none.
    thin_low_signals: Mapped[int] = mapped_column(SmallInteger, default=1)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
