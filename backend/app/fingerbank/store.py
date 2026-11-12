"""Keeping what Fingerbank said a device is."""

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.fingerbank.lookup import PROVIDER, Identified, Unknown
from app.fingerbank.queue import Wanted
from app.models import DeviceIdentity


def save(db: Session, wanted: Wanted, answer: Identified | Unknown, now: datetime) -> None:
    """Keeps the answer for the device, in place of the one kept before. The caller commits."""
    identity = answer.identity if isinstance(answer, Identified) else None
    values = {
        "source": PROVIDER,
        "state": "identified" if identity else "unknown",
        "reason": wanted.reason,
        "name": identity.name if identity else None,
        "path": identity.path if identity else None,
        "manufacturer": identity.manufacturer if identity else None,
        "operating_system": identity.operating_system if identity else None,
        "score": identity.score if identity else None,
        "external_id": identity.external_id if identity else None,
        "checked_at": now,
    }
    statement = insert(DeviceIdentity).values(device_id=wanted.device_id, **values)
    db.execute(statement.on_conflict_do_update(index_elements=["device_id"], set_=values))
