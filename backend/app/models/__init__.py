"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models.ai import AiProvider, AiSettings
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
from app.models.devices import Device, DeviceAddress
from app.models.events import Event, EventRetention
from app.models.incidents import STATUSES as INCIDENT_STATUSES
from app.models.incidents import Incident, IncidentSignal
from app.models.integrations import ApiCall, IntegrationConnection
from app.models.metrics import MetricRetention, MetricSample, MetricSeries
from app.models.passkeys import Passkey, PasskeyChallenge
from app.models.retention import SourceRetention
from app.models.searches import SavedSearch
from app.models.system import SystemInfo
from app.models.verdicts import VERDICTS, VerdictRule

__all__ = [
    "INCIDENT_STATUSES",
    "VERDICTS",
    "AiProvider",
    "AiSettings",
    "ApiCall",
    "AuditEvent",
    "Base",
    "CollectorHealth",
    "Device",
    "DeviceAddress",
    "Event",
    "EventRetention",
    "Incident",
    "IncidentSignal",
    "IntegrationConnection",
    "LoginThrottle",
    "MetricRetention",
    "MetricSample",
    "MetricSeries",
    "Passkey",
    "PasskeyChallenge",
    "RecoveryCode",
    "SavedSearch",
    "SourceRetention",
    "StoredCredential",
    "SystemInfo",
    "TotpCredential",
    "UTCDateTime",
    "User",
    "UserSession",
    "VerdictRule",
    "WorkerBeat",
    "utcnow",
]
