"""How the collectors are doing: the worker, and each collector's last run and next one. For
someone signed in, and read-only: collectors are not started or stopped from here."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import Db, SettingsDep, signed_in
from app.collectors import report
from app.models import utcnow
from app.security.credential_store import NAME_PATTERN

router = APIRouter(prefix="/collectors", tags=["collectors"], dependencies=[Depends(signed_in)])


@router.get("")
def list_collectors(
    db: Db,
    settings: SettingsDep,
    integration: Annotated[
        str | None,
        Query(
            pattern=NAME_PATTERN, description="Only the collectors reading from this integration."
        ),
    ] = None,
) -> report.CollectorsOut:
    """The collector worker and every collector, or those of one integration."""
    return report.build(db, settings, utcnow(), integration)
