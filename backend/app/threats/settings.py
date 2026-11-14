"""What the owner has set for telling threats from noise, and what that comes to for an incident.

Nothing is stored until the owner first saves; until then every number is the default. The AI
watching or not is part of it, because with the AI watching a threat is one it agrees with."""

from copy import replace
from dataclasses import dataclass, field
from typing import Final

from sqlalchemy.orm import Session

from app.incidents import rules
from app.models import AiSettings, ThreatSettings

DEFAULT_THREAT_FROM: Final = rules.HIGH_FROM
DEFAULT_CLEAR_FROM: Final = 80
MIN_CLEAR_FROM: Final = 50
EXPOSURES: Final = ("none", "some", "unknown")
DEFAULT_IMPORTANT_DROP: Final = 10
DEFAULT_LOW_RAISE: Final = 0
MAX_SHIFT: Final = 30
MAX_NOTES: Final = 500
MAX_PORTS: Final = 20
# The usage level at which the AI reads nothing by itself, and so isn't watching.
UNWATCHING: Final = "very_low"


@dataclass(frozen=True)
class Tuning:
    """The owner's settings. ``confirming`` is whether the AI's agreement is needed for a threat
    right now: they asked for it and the AI is on, with a provider, and reads by itself."""

    threat_from: int = DEFAULT_THREAT_FROM
    ai_may_clear: bool = True
    clear_from: int = DEFAULT_CLEAR_FROM
    ai_confirms: bool = True
    exposure: str = "unknown"
    exposed_ports: tuple[int, ...] = field(default_factory=tuple[int, ...])
    notes: str = ""
    # How many points less sure than the floor an incident that touched an important device may be
    # and still be asked about, and how many more it takes when it touched only guest or IoT
    # devices (``app/threats/importance.py``).
    important_drop: int = DEFAULT_IMPORTANT_DROP
    low_raise: int = DEFAULT_LOW_RAISE
    confirming: bool = False

    def confirming_when(self, confirming: bool) -> Tuning:
        """These settings, with the AI's agreement needed for a threat or not."""
        return replace(self, confirming=confirming)

    def shift(self, importance: int | None) -> int:
        """How far the floor moves for an incident of that importance (none for one that has not
        been saved yet): down for one that touched an important or critical device, up for one
        that touched only guests and IoT devices."""
        importance = importance or 0
        if importance > 0:
            return -self.important_drop
        return self.low_raise if importance < 0 else 0


def watching(db: Session) -> bool:
    """Whether an AI is on, has a provider and reads incidents by itself."""
    row = db.get(AiSettings, 1)
    return (
        row is not None
        and row.enabled
        and row.provider is not None
        and row.usage_level != UNWATCHING
    )


def _stored(db: Session) -> Tuning:
    row = db.get(ThreatSettings, 1)
    if row is None:
        return Tuning()
    return Tuning(
        row.threat_from,
        row.ai_may_clear,
        row.clear_from,
        row.ai_confirms,
        row.exposure,
        tuple(row.exposed_ports),
        row.notes,
        row.important_drop,
        row.low_raise,
    )


def load(db: Session) -> Tuning:
    """The settings as they are saved, or the defaults where nothing has been."""
    stored = _stored(db)
    return stored.confirming_when(stored.ai_confirms and watching(db))


def save(db: Session, tuning: Tuning) -> bool:
    """Keeps the settings as they are given, and says whether that changed them. The caller
    commits."""
    if tuning.confirming_when(False) == _stored(db):
        return False
    row = db.get(ThreatSettings, 1)
    if row is None:
        row = ThreatSettings(id=1)
        db.add(row)
    row.threat_from = tuning.threat_from
    row.ai_may_clear = tuning.ai_may_clear
    row.clear_from = tuning.clear_from
    row.ai_confirms = tuning.ai_confirms
    row.exposure = tuning.exposure
    row.exposed_ports = list(tuning.exposed_ports)
    row.notes = tuning.notes
    row.important_drop = tuning.important_drop
    row.low_raise = tuning.low_raise
    db.flush()
    return True


def describe(tuning: Tuning) -> str:
    """The owner's network in a few lines for the AI, which is told what is normal there. Ports
    and the owner's own words only; nothing here names a device."""
    if tuning.exposure == "none":
        exposed = "Nothing on this network is meant to be reachable from the internet."
    elif tuning.exposure == "some":
        ports = ", ".join(str(port) for port in tuning.exposed_ports) or "unspecified ports"
        exposed = f"Some services are reachable from the internet, on these ports: {ports}."
    else:
        exposed = "The owner hasn't said whether anything is reachable from the internet."
    return exposed
