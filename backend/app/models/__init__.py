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
from app.models.credentials import StoredCredential
from app.models.passkeys import Passkey, PasskeyChallenge
from app.models.system import SystemInfo

__all__ = [
    "AuditEvent",
    "Base",
    "LoginThrottle",
    "Passkey",
    "PasskeyChallenge",
    "RecoveryCode",
    "StoredCredential",
    "SystemInfo",
    "TotpCredential",
    "UTCDateTime",
    "User",
    "UserSession",
    "utcnow",
]
