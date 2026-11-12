"""ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models.agents import (
    AI_SOURCES,
    CLEANUP_MODES,
    MIN_INTERVAL_MINUTES,
    PROPOSAL_STATUSES,
    Agent,
    AgentProposal,
    AgentRun,
    AgentSettings,
    AgentStep,
)
from app.models.agents import (
    STATUSES as AGENT_STATUSES,
)
from app.models.agents import (
    TRIGGERS as AGENT_TRIGGERS,
)
from app.models.ai import (
    CLASSES,
    USAGE_LEVELS,
    AiAlias,
    AiCall,
    AiConversation,
    AiMessage,
    AiProvider,
    AiSettings,
    AiTriage,
)
from app.models.alerts import KINDS as ALERT_KINDS
from app.models.alerts import AlertDelivery, AlertDestination
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
from app.models.devices import AssetProfile, Device, DeviceAddress, DeviceSource, HostListing
from app.models.events import Event, EventRetention
from app.models.incidents import STATUSES as INCIDENT_STATUSES
from app.models.incidents import (
    AddressName,
    Incident,
    IncidentChain,
    IncidentFamily,
    IncidentSignal,
    NoiseSettings,
    ThreatSettings,
)
from app.models.integrations import ApiCall, IntegrationConnection
from app.models.intel import IntelLookup, IntelOverride, IntelSubject
from app.models.interfaces import ROLES as INTERFACE_ROLES
from app.models.interfaces import Interface, InterfaceFeed
from app.models.metrics import MetricRetention, MetricSample, MetricSeries
from app.models.passkeys import Passkey, PasskeyChallenge
from app.models.retention import SourceRetention
from app.models.review import ANSWERS, REVIEW_MODES, ReviewFeedback, ReviewSettings
from app.models.searches import SavedSearch
from app.models.system import SystemInfo
from app.models.verdicts import VERDICTS, VerdictRule

__all__ = [
    "AGENT_STATUSES",
    "AGENT_TRIGGERS",
    "AI_SOURCES",
    "ALERT_KINDS",
    "ANSWERS",
    "CLASSES",
    "CLEANUP_MODES",
    "INCIDENT_STATUSES",
    "INTERFACE_ROLES",
    "MIN_INTERVAL_MINUTES",
    "PROPOSAL_STATUSES",
    "REVIEW_MODES",
    "USAGE_LEVELS",
    "VERDICTS",
    "AddressName",
    "Agent",
    "AgentProposal",
    "AgentRun",
    "AgentSettings",
    "AgentStep",
    "AiAlias",
    "AiCall",
    "AiConversation",
    "AiMessage",
    "AiProvider",
    "AiSettings",
    "AiTriage",
    "AlertDelivery",
    "AlertDestination",
    "ApiCall",
    "AssetProfile",
    "AuditEvent",
    "Base",
    "CollectorHealth",
    "Device",
    "DeviceAddress",
    "DeviceSource",
    "Event",
    "EventRetention",
    "HostListing",
    "Incident",
    "IncidentChain",
    "IncidentFamily",
    "IncidentSignal",
    "IntegrationConnection",
    "IntelLookup",
    "IntelOverride",
    "IntelSubject",
    "Interface",
    "InterfaceFeed",
    "LoginThrottle",
    "MetricRetention",
    "MetricSample",
    "MetricSeries",
    "NoiseSettings",
    "Passkey",
    "PasskeyChallenge",
    "RecoveryCode",
    "ReviewFeedback",
    "ReviewSettings",
    "SavedSearch",
    "SourceRetention",
    "StoredCredential",
    "SystemInfo",
    "ThreatSettings",
    "TotpCredential",
    "UTCDateTime",
    "User",
    "UserSession",
    "VerdictRule",
    "WorkerBeat",
    "utcnow",
]
