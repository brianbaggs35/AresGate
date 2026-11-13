"""Alerts: the places AresGate sends word of what it finds. Their addresses only go in: no route
here returns one, and a failed request doesn't quote what was sent."""

from datetime import datetime
from typing import Annotated, Literal, cast

import anyio.from_thread
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    StringConstraints,
    model_validator,
)
from sqlalchemy.orm import Session

from app.alerts import destinations, discord, log, mail, message
from app.alerts import rules as alert_rules
from app.alerts.destinations import NameTaken, Unusable
from app.alerts.discord import InvalidWebhook
from app.api.dashboard import SEVERITY_NAMES, SeverityName
from app.api.deps import Db, SettingsDep, SignedIn, record_audit, signed_in
from app.api.integrations import RecorderDep
from app.audit import Action, Outcome
from app.config import Settings
from app.events.event import Severity
from app.incidents import episode
from app.integrations import registry
from app.integrations.service import Status
from app.models import AlertDelivery, AlertDestination, Incident, utcnow

# Everything here is for someone who is signed in.
router = APIRouter(prefix="/alerts", tags=["alerts"], dependencies=[Depends(signed_in)])

DestinationId = Annotated[int, Path(ge=1, le=2**63 - 1)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Address = Annotated[SecretStr, Field(min_length=1, max_length=discord.MAX_URL)]


Activity = Literal["scan", "brute_force"]
Detail = Literal["brief", "standard", "full"]
Mode = Literal["threats", "custom"]
Why = Literal["new", "worse", "reopened"]
Minute = Annotated[int, Field(ge=0, le=alert_rules.MINUTES_A_DAY - 1)]


class RulesModel(BaseModel):
    """What a destination is told about, and when (see app/alerts/rules.py). Every field is
    always given: the page edits the whole set."""

    model_config = ConfigDict(extra="forbid")

    # Only the incidents on the Threats page, or what the four rules below choose.
    mode: Mode
    min_severity: Annotated[int, Field(ge=1, le=4)]
    min_confidence: Annotated[int, Field(ge=0, le=100)]
    sources: Annotated[list[Annotated[str, StringConstraints(max_length=32)]], Field(max_length=16)]
    activities: Annotated[list[Activity], Field(max_length=2)]
    quiet_hours: bool
    quiet_from: Minute
    quiet_until: Minute
    quiet_critical: bool
    time_zone: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    max_per_hour: Annotated[int, Field(ge=1, le=60)]
    detail: Detail
    again_when_worse: bool


class ChoiceOut(BaseModel):
    key: str
    name: str


class ChoicesOut(BaseModel):
    """What the rules can name, for the page to offer."""

    sources: list[ChoiceOut]
    activities: list[ChoiceOut]


class SmtpOut(BaseModel):
    """The mail server email destinations send through. The password only goes in: whether one is
    kept is all that is said of it."""

    configured: bool
    host: str
    port: int
    security: Literal["starttls", "ssl", "none"]
    username: str | None
    sender: str
    password_kept: bool
    # The port that is usual for each way of connecting, for the page to offer.
    default_ports: dict[str, int]


class DestinationOut(BaseModel):
    id: int
    kind: Literal["discord", "email"]
    name: str
    enabled: bool
    # Where it goes without the secret: the host, and the end of the webhook's number. For an
    # email destination, the mail server's name (empty until it is set up).
    host: str
    hint: str
    # The address an email destination is sent to. Not a secret. None for any other kind.
    recipient: str | None
    # Not tried, working, or failing; "not_connected" is a destination whose address is gone.
    status: Status
    last_attempt_at: AwareDatetime | None
    last_success_at: AwareDatetime | None
    last_error: str | None
    rules: RulesModel
    created_at: AwareDatetime
    updated_at: AwareDatetime


class DestinationsOut(BaseModel):
    items: list[DestinationOut]
    max_destinations: int
    # The addresses a webhook may be at, for the page to say.
    hosts: list[str]
    choices: ChoicesOut
    smtp: SmtpOut


class LeftOutOut(BaseModel):
    reason: alert_rules.Reason
    text: str
    count: int


class ExampleOut(BaseModel):
    id: int
    title: str
    severity: SeverityName
    confidence: int
    last_seen_at: AwareDatetime


class PreviewOut(BaseModel):
    """What a set of rules would have done in the last day."""

    hours: int
    considered: int
    would_send: int
    held: int
    busiest_hour: int
    over_limit: int
    truncated: bool
    left_out: list[LeftOutOut]
    examples: list[ExampleOut]


DeliveryState = Literal[
    "queued", "held", "retrying", "limited", "summarized", "sent", "failed", "dropped"
]


class DeliveryOut(BaseModel):
    """One message to a destination and what became of it."""

    id: int
    destination_id: int
    destination: str
    # None for a summary, and for a message whose incident has since been deleted.
    incident_id: int | None
    kind: Literal["incident", "summary", "update"]
    reason: Literal["new", "worse", "reopened", "limit", "quiet", "retract"]
    state: DeliveryState
    title: str
    severity: SeverityName
    confidence: int
    # For a summary, how many incidents it told of.
    covers: int
    attempts: int
    created_at: AwareDatetime
    # When it is due to be sent, or tried again.
    due_at: AwareDatetime
    sent_at: AwareDatetime | None
    # Why it is waiting, was not sent or failed, in words.
    note: str | None


class DeliveriesOut(BaseModel):
    items: list[DeliveryOut]
    # The id to pass as ``before`` for the next page, or none on the last.
    next_before: int | None
    # How many messages are in each state, for the destination asked about or all.
    counts: dict[DeliveryState, int]


class DestinationIn(BaseModel):
    """A new destination: a Discord webhook's address (``url``), or an email address
    (``recipient``) to send through the mail server."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["discord", "email"] = "discord"
    name: Name
    url: Address | None = None
    recipient: Annotated[str, Field(min_length=1, max_length=mail.MAX_ADDRESS)] | None = None

    @model_validator(mode="after")
    def _the_address_of_its_kind(self) -> DestinationIn:
        if self.kind == "discord" and self.url is None:
            raise ValueError("Paste the webhook address from Discord.")
        if self.kind == "email" and self.recipient is None:
            raise ValueError("Enter the email address to send alerts to.")
        return self


class DestinationChange(BaseModel):
    """What can be changed of a destination. What is left out stays; an address is replaced, never
    shown."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    enabled: bool | None = None
    url: Address | None = None
    recipient: Annotated[str, Field(min_length=1, max_length=mail.MAX_ADDRESS)] | None = None


class SmtpIn(BaseModel):
    """The mail server's settings. A password left out stays as it is; ``clear_password`` forgets
    it, for a server that needs none."""

    model_config = ConfigDict(extra="forbid")

    host: Annotated[str, Field(min_length=1, max_length=mail.MAX_HOST)]
    port: Annotated[int, Field(ge=1, le=65535)]
    security: Literal["starttls", "ssl", "none"]
    username: Annotated[str, Field(max_length=mail.MAX_USERNAME)] | None = None
    sender: Annotated[str, Field(min_length=1, max_length=mail.MAX_ADDRESS)]
    password: Annotated[SecretStr, Field(min_length=1, max_length=mail.MAX_PASSWORD)] | None = None
    clear_password: bool = False


class TestOut(BaseModel):
    ok: bool
    message: str
    destination: DestinationOut


def _invalid(*location: str, message: str) -> dict[str, object]:
    return {"type": "value_error", "loc": ["body", *location], "msg": message}


def _rules_model(row: AlertDestination) -> RulesModel:
    return RulesModel(
        mode=cast("Mode", row.mode),
        min_severity=row.min_severity,
        min_confidence=row.min_confidence,
        sources=list(row.sources),
        activities=[cast("Activity", item) for item in row.activities],
        quiet_hours=row.quiet_hours,
        quiet_from=row.quiet_from,
        quiet_until=row.quiet_until,
        quiet_critical=row.quiet_critical,
        time_zone=row.time_zone,
        max_per_hour=row.max_per_hour,
        detail=cast("Detail", row.detail),
        again_when_worse=row.again_when_worse,
    )


def _smtp_out(db: Session) -> SmtpOut:
    row = destinations.smtp(db)
    return SmtpOut(
        configured=row is not None,
        host=row.host if row else "",
        port=row.port if row else mail.DEFAULT_PORTS["starttls"],
        security=cast("Literal['starttls', 'ssl', 'none']", row.security) if row else "starttls",
        username=row.username if row else None,
        sender=row.sender if row else "",
        password_kept=destinations.smtp_password_kept(db),
        default_ports=mail.DEFAULT_PORTS,
    )


def _out(row: AlertDestination, *, has_address: bool, mail_host: str = "") -> DestinationOut:
    return DestinationOut(
        id=row.id,
        kind=cast("Literal['discord', 'email']", row.kind),
        name=row.name,
        enabled=row.enabled,
        host=mail_host if row.kind == "email" else discord.HOSTS[0],
        hint=row.hint,
        recipient=row.recipient,
        status=destinations.status_of(row, has_address=has_address),
        last_attempt_at=row.last_attempt_at,
        last_success_at=row.last_success_at,
        last_error=row.last_error,
        rules=_rules_model(row),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _one(db: Session, row: AlertDestination) -> DestinationOut:
    server = destinations.smtp(db)
    return _out(
        row,
        has_address=row.id in destinations.with_address(db),
        mail_host=server.host if server else "",
    )


def _find(db: Session, destination_id: int) -> AlertDestination:
    row = db.get(AlertDestination, destination_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no such destination.")
    return row


@router.put("/smtp")
def change_smtp(
    body: SmtpIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> SmtpOut:
    """Keeps the mail server that email destinations send through. Its password is sealed and never
    returned."""
    try:
        destinations.save_smtp(
            db,
            settings,
            host=body.host,
            port=body.port,
            security=body.security,
            username=body.username,
            sender=body.sender,
            password=body.password.get_secret_value() if body.password else None,
            clear_password=body.clear_password,
            now=utcnow(),
        )
    except mail.InvalidSettings as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, [_invalid(error.field, message=str(error))]
        ) from None
    record_audit(
        db,
        request,
        Action.ALERT_SMTP_CHANGED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"host": body.host.strip().lower(), "security": body.security},
    )
    db.commit()
    return _smtp_out(db)


@router.delete("/smtp", status_code=status.HTTP_204_NO_CONTENT)
def remove_smtp(
    auth: Annotated[SignedIn, Depends(signed_in)], request: Request, db: Db
) -> Response:
    """Forgets the mail server and its password. Email destinations stay, and wait for a server."""
    destinations.forget_smtp(db)
    record_audit(db, request, Action.ALERT_SMTP_REMOVED, Outcome.SUCCESS, user=auth.user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/destinations")
def list_destinations(db: Db) -> DestinationsOut:
    """The places alerts are sent, in the order they were added."""
    addressed = destinations.with_address(db)
    server = destinations.smtp(db)
    mail_host = server.host if server else ""
    return DestinationsOut(
        items=[
            _out(row, has_address=row.id in addressed, mail_host=mail_host)
            for row in destinations.listing(db)
        ],
        max_destinations=destinations.MAX_DESTINATIONS,
        hosts=list(discord.HOSTS),
        choices=ChoicesOut(
            sources=[
                ChoiceOut(key=key, name=known.name) for key, known in registry.INTEGRATIONS.items()
            ],
            activities=[
                ChoiceOut(key=key, name=name) for key, name in episode.ACTIVITY_NAMES.items()
            ],
        ),
        smtp=_smtp_out(db),
    )


@router.post("/destinations", status_code=status.HTTP_201_CREATED)
def add_destination(
    body: DestinationIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> DestinationOut:
    """Keeps a new destination, with its address sealed. It isn't tried yet: the test route does
    that."""
    if destinations.count(db) >= destinations.MAX_DESTINATIONS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"You can keep {destinations.MAX_DESTINATIONS} destinations. Remove one to add "
            "another.",
        )
    try:
        if body.kind == "email":
            row = destinations.create_email(db, body.name, body.recipient or "", utcnow())
        else:
            row = destinations.create(
                db, settings, body.name, (body.url or SecretStr("")).get_secret_value(), utcnow()
            )
    except InvalidWebhook as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, [_invalid("url", message=str(error))]
        ) from None
    except mail.InvalidSettings as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, [_invalid(error.field, message=str(error))]
        ) from None
    except NameTaken as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, [_invalid("name", message=str(error))]
        ) from None
    record_audit(
        db,
        request,
        Action.ALERT_DESTINATION_ADDED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"destination": row.name, "kind": row.kind},
    )
    db.commit()
    return _one(db, row)


def _rename(db: Db, row: AlertDestination, body: DestinationChange) -> bool:
    """Gives the destination the new name, if there is one. Answers whether it changed."""
    if body.name is None or body.name == row.name:
        return False
    try:
        destinations.check_name(db, body.name, except_id=row.id)
    except NameTaken as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, [_invalid("name", message=str(error))]
        ) from None
    row.name = body.name
    return True


def _readdress(
    db: Db, settings: Settings, row: AlertDestination, body: DestinationChange, now: datetime
) -> bool:
    """Replaces the webhook's address or the email address, when one is given for its kind.
    Answers whether it changed."""
    try:
        if body.url is not None and row.kind == "discord":
            destinations.replace_address(db, settings, row, body.url.get_secret_value(), now)
            return True
        if body.recipient is not None and row.kind == "email":
            destinations.replace_recipient(row, body.recipient, now)
            return True
    except InvalidWebhook as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, [_invalid("url", message=str(error))]
        ) from None
    except mail.InvalidSettings as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, [_invalid(error.field, message=str(error))]
        ) from None
    return False


@router.patch("/destinations/{destination_id}")
def change_destination(
    destination_id: DestinationId,
    body: DestinationChange,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
) -> DestinationOut:
    """Renames a destination, turns it on or off, or replaces its address."""
    row = _find(db, destination_id)
    now = utcnow()
    changed: list[str] = []
    if _rename(db, row, body):
        changed.append("name")
    if _readdress(db, settings, row, body, now):
        changed.append("address")
    if body.enabled is not None and body.enabled != row.enabled:
        row.enabled = body.enabled
        if body.enabled:
            # It hears of what happens from now on, not of what it missed while it was off.
            row.listening_since = now
        changed.append("turned on" if body.enabled else "turned off")
    if changed:
        row.updated_at = now
        record_audit(
            db,
            request,
            Action.ALERT_DESTINATION_CHANGED,
            Outcome.SUCCESS,
            user=auth.user,
            detail={"destination": row.name, "changed": ", ".join(changed)},
        )
    db.commit()
    return _one(db, row)


@router.delete("/destinations/{destination_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_destination(
    destination_id: DestinationId,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> Response:
    """Forgets a destination and its address."""
    row = _find(db, destination_id)
    name = row.name
    destinations.forget(db, row)
    record_audit(
        db,
        request,
        Action.ALERT_DESTINATION_REMOVED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"destination": name},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class SampleOut(BaseModel):
    """A message as Discord will show it, for the page to draw."""

    payload: dict[str, object]


def _deliver(
    row: AlertDestination,
    payload: dict[str, object],
    *,
    auth: SignedIn,
    request: Request,
    db: Session,
    settings: SettingsDep,
    recorder: RecorderDep,
    now: datetime,
    done: str,
) -> TestOut:
    """Sends a message the owner asked for to a destination and keeps how it went. It goes even
    when the destination is turned off."""
    sent: discord.Sent | str
    try:
        if row.kind == "email":
            box = destinations.open_mailbox(db, settings, row)
            sent = anyio.from_thread.run(lambda: mail.send(box, payload))
        else:
            webhook = destinations.open_webhook(db, settings, row)
            sent = anyio.from_thread.run(
                lambda: discord.send(
                    webhook,
                    payload,
                    connection=f"destination-{row.id}",
                    recorder=recorder,
                    policy=request.app.state.alert_policy,
                    origin=request.app.state.alert_origin,
                )
            )
    except Unusable as problem:
        sent = str(problem)
    destinations.record_attempt(row, sent, now)
    ok = not isinstance(sent, str) and sent.ok
    record_audit(
        db,
        request,
        Action.ALERT_DESTINATION_TESTED,
        Outcome.SUCCESS if ok else Outcome.FAILURE,
        user=auth.user,
        detail={"destination": row.name},
    )
    db.commit()
    text = done
    if not ok:
        problem = sent if isinstance(sent, str) else sent.problem
        text = problem or "The message didn't get through."
    return TestOut(ok=ok, message=text, destination=_one(db, row))


def _arrived(row: AlertDestination, what: str) -> str:
    """What a message that got through says, by where it went."""
    where = f"the inbox of {row.recipient}" if row.kind == "email" else "the channel"
    return f"The {what} was sent. Look for it in {where}."


@router.post("/destinations/{destination_id}/test")
def test_destination(
    destination_id: DestinationId,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
    recorder: RecorderDep,
) -> TestOut:
    """Sends a real test message and keeps how it went. It goes even when the destination is turned
    off, because the owner asked for it."""
    row = _find(db, destination_id)
    now = utcnow()
    return _deliver(
        row,
        mail.check_message(row.name, now)
        if row.kind == "email"
        else discord.check_message(row.name, now),
        auth=auth,
        request=request,
        db=db,
        settings=settings,
        recorder=recorder,
        now=now,
        done=_arrived(row, "test message"),
    )


@router.post("/destinations/{destination_id}/sample")
def send_sample(
    destination_id: DestinationId,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
    recorder: RecorderDep,
) -> TestOut:
    """Sends a sample alert, made up and marked as one, in the form this destination's rules give
    its real messages, so the owner sees what will arrive before a real one does."""
    row = _find(db, destination_id)
    now = utcnow()
    return _deliver(
        row,
        message.sample_message(
            mode=row.mode, reason="new", detail=row.detail, origin=settings.public_origin, at=now
        ),
        auth=auth,
        request=request,
        db=db,
        settings=settings,
        recorder=recorder,
        now=now,
        done=_arrived(row, "sample alert"),
    )


@router.get("/sample")
def sample(
    settings: SettingsDep,
    mode: Mode = "threats",
    detail: Detail = "standard",
    reason: Why = "new",
) -> SampleOut:
    """A message as the rules in this mode and at this level of detail would send it, about an
    incident that is made up, for the page to show next to the choice."""
    return SampleOut(
        payload=message.sample_message(
            mode=mode, reason=reason, detail=detail, origin=settings.public_origin, at=utcnow()
        )
    )


def _checked(body: RulesModel) -> alert_rules.Rules:
    """The rules the page sent, if they make sense; otherwise a 422 on the field that doesn't."""
    unknown = sorted(set(body.sources) - set(registry.INTEGRATIONS))
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [_invalid("sources", message=f"AresGate has no program called {unknown[0]}.")],
        )
    if alert_rules.zone_of(body.time_zone) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [_invalid("time_zone", message="That isn't a time zone, such as Europe/Berlin.")],
        )
    if body.quiet_hours and body.quiet_from == body.quiet_until:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [
                _invalid(
                    "quiet_until", message="Quiet hours need an end that differs from the start."
                )
            ],
        )
    return alert_rules.Rules(
        mode=body.mode,
        min_severity=body.min_severity,
        min_confidence=body.min_confidence,
        sources=tuple(sorted(set(body.sources))),
        activities=tuple(sorted(set(body.activities))),
        quiet=alert_rules.Quiet(
            body.quiet_from, body.quiet_until, body.time_zone, body.quiet_critical
        )
        if body.quiet_hours
        else None,
        max_per_hour=body.max_per_hour,
        detail=body.detail,
        again_when_worse=body.again_when_worse,
    )


@router.put("/destinations/{destination_id}/rules")
def change_rules(
    destination_id: DestinationId,
    body: RulesModel,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
) -> DestinationOut:
    """Replaces what a destination is told about, and when."""
    row = _find(db, destination_id)
    rules = _checked(body)
    row.mode = rules.mode
    row.min_severity = rules.min_severity
    row.min_confidence = rules.min_confidence
    row.sources = list(rules.sources)
    row.activities = list(rules.activities)
    row.quiet_hours = body.quiet_hours
    row.quiet_from = body.quiet_from
    row.quiet_until = body.quiet_until
    row.quiet_critical = body.quiet_critical
    row.time_zone = body.time_zone
    row.max_per_hour = rules.max_per_hour
    row.detail = rules.detail
    row.again_when_worse = rules.again_when_worse
    row.updated_at = utcnow()
    # New rules apply to what happens from now on: a looser one does not send the last hours.
    row.listening_since = row.updated_at
    record_audit(
        db,
        request,
        Action.ALERT_RULES_CHANGED,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"destination": row.name},
    )
    db.commit()
    return _one(db, row)


def _example(incident: Incident) -> ExampleOut:
    return ExampleOut(
        id=incident.id,
        title=incident.title,
        severity=SEVERITY_NAMES[Severity(incident.severity)],
        confidence=incident.confidence,
        last_seen_at=incident.last_seen_at,
    )


@router.post("/destinations/{destination_id}/preview")
def preview_rules(destination_id: DestinationId, body: RulesModel, db: Db) -> PreviewOut:
    """What these rules would have sent in the last day, without saving them or sending anything,
    so that they can be tuned before they are used."""
    _find(db, destination_id)
    rules = _checked(body)
    result = alert_rules.preview(db, rules, utcnow())
    return PreviewOut(
        hours=result.hours,
        considered=result.considered,
        would_send=result.would_send,
        held=result.held,
        busiest_hour=result.busiest_hour,
        over_limit=result.over_limit,
        truncated=result.truncated,
        left_out=[
            LeftOutOut(reason=reason, text=alert_rules.explain(reason, rules), count=count)
            for reason, count in result.left_out.items()
            if count
        ],
        examples=[_example(incident) for incident in result.examples],
    )


def _delivery(row: AlertDelivery, destination: str) -> DeliveryOut:
    return DeliveryOut(
        id=row.id,
        destination_id=row.destination_id,
        destination=destination,
        incident_id=row.incident_id,
        kind=cast("Literal['incident', 'summary', 'update']", row.kind),
        reason=cast("Literal['new', 'worse', 'reopened', 'limit', 'quiet', 'retract']", row.reason),
        state=cast("DeliveryState", row.state),
        title=row.title,
        severity=SEVERITY_NAMES[Severity(row.severity)],
        confidence=row.confidence,
        covers=row.covers,
        attempts=row.attempts,
        created_at=row.created_at,
        due_at=row.due_at,
        sent_at=row.sent_at,
        note=row.note,
    )


@router.get("/deliveries")
def list_deliveries(
    db: Db,
    destination_id: Annotated[int | None, Query(ge=1, le=2**63 - 1)] = None,
    state: DeliveryState | None = None,
    before: Annotated[int | None, Query(ge=1, le=2**63 - 1)] = None,
    limit: Annotated[int, Query(ge=1, le=log.MAX_PAGE)] = log.PAGE,
) -> DeliveriesOut:
    """The log of messages, newest first: what was sent to each destination, what is waiting, and
    what was held back, left out or given up on, with the reason."""
    page = log.listing(db, destination_id=destination_id, state=state, before=before, limit=limit)
    return DeliveriesOut(
        items=[_delivery(row, name) for row, name in page],
        next_before=page[-1][0].id if len(page) == limit else None,
        counts=cast("dict[DeliveryState, int]", log.counts(db, destination_id)),
    )
