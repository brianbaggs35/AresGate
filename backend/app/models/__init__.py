"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models.audit import AuditEvent
from app.models.auth import (
    LoginThrottle,
    RecoveryCode,
    TotpCredential,
    User,
    UserSession,
)
from app.models.base import Base, UTCDateTime, utcnow
from app.models.collectors import CollectorHealth, WorkerBeat
from app.models.credentials import StoredCredential
from app.models.events import Event, EventRetention
from app.models.integrations import ApiCall, IntegrationConnection
from app.models.metrics import MetricRetention, MetricSample, MetricSeries
from app.models.passkeys import Passkey, PasskeyChallenge
from app.models.retention import SourceRetention
from app.models.system import SystemInfo

__all__ = [
    "ApiCall",
    "AuditEvent",
    "Base",
    "CollectorHealth",
    "Event",
    "EventRetention",
    "IntegrationConnection",
    "LoginThrottle",
    "MetricRetention",
    "MetricSample",
    "MetricSeries",
    "Passkey",
    "PasskeyChallenge",
    "RecoveryCode",
    "SourceRetention",
    "StoredCredential",
    "SystemInfo",
    "TotpCredential",
    "UTCDateTime",
    "User",
    "UserSession",
    "WorkerBeat",
    "utcnow",
]
