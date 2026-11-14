"""A short capture of the packets of one host, taken by ntopng. For someone signed in, because
what a packet carries can be private: the capture is read and shown, and nothing of it is kept."""

import threading
from typing import Annotated

import anyio.from_thread
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app import captures
from app.api.deps import Db, SettingsDep, SignedIn, record_audit, signed_in
from app.api.integrations import PolicyDep, RecorderDep
from app.audit import Action, Outcome
from app.integrations import registry, service

router = APIRouter(prefix="/captures", tags=["captures"], dependencies=[Depends(signed_in)])

# One capture at a time: ntopng holds the interface for each, and a second would only wait.
RUNNING = threading.Lock()


class CaptureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The address of the host whose packets are wanted.
    host: str = Field(min_length=2, max_length=45)
    seconds: int = Field(default=10, ge=captures.MIN_SECONDS, le=captures.MAX_SECONDS)


class PacketOut(BaseModel):
    at: AwareDatetime
    source: str
    destination: str
    protocol: str
    source_port: int | None
    destination_port: int | None
    length: int
    flags: str
    preview: str


class ProtocolOut(BaseModel):
    protocol: str
    packets: int


class CaptureOut(BaseModel):
    host: str
    seconds: int
    packets: list[PacketOut]
    total: int
    skipped: int
    bytes: int
    cut: bool
    protocols: list[ProtocolOut]
    max_packets: int


@router.post(
    "",
    responses={
        409: {"description": "ntopng isn't connected, or a capture is already running."},
        422: {"description": "The host isn't an IP address."},
        502: {"description": "ntopng couldn't give a capture."},
    },
)
def take_capture(
    body: CaptureIn,
    auth: Annotated[SignedIn, Depends(signed_in)],
    request: Request,
    db: Db,
    settings: SettingsDep,
    policy: PolicyDep,
    recorder: RecorderDep,
) -> CaptureOut:
    """Asks ntopng for a few seconds of the packets to and from a host, and returns what they
    say. It is a request for ntopng to listen for that long, so it is limited to one at a time
    and is in the audit log with the host it was about."""
    host = captures.valid_host(body.host)
    if host is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That isn't an IP address.")
    definition = registry.INTEGRATIONS["ntopng"]
    connection = definition.connection("api")
    row = service.rows_for(db, definition.key).get("api")
    if row is None or connection is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect ntopng first.")
    try:
        target = service.load_target(db, settings, definition, connection, row)
    except service.Incomplete as incomplete:
        raise HTTPException(status.HTTP_409_CONFLICT, str(incomplete)) from None
    # The listening takes seconds, which no transaction should be held open for.
    db.commit()
    if not RUNNING.acquire(blocking=False):
        raise HTTPException(status.HTTP_409_CONFLICT, "A capture is already running. Wait for it.")
    try:
        taken = anyio.from_thread.run(captures.take, target, recorder, policy, host, body.seconds)
    except captures.CaptureFailed as failed:
        record_audit(
            db,
            request,
            Action.CAPTURE_TAKEN,
            Outcome.FAILURE,
            user=auth.user,
            detail={"host": host, "seconds": body.seconds},
        )
        db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(failed)) from None
    finally:
        RUNNING.release()
    record_audit(
        db,
        request,
        Action.CAPTURE_TAKEN,
        Outcome.SUCCESS,
        user=auth.user,
        detail={"host": host, "seconds": body.seconds, "packets": taken.total},
    )
    db.commit()
    return CaptureOut(
        host=host,
        seconds=body.seconds,
        packets=[PacketOut(**vars(packet)) for packet in taken.packets],
        total=taken.total,
        skipped=taken.skipped,
        bytes=taken.bytes,
        cut=taken.cut,
        protocols=[ProtocolOut(protocol=name, packets=count) for name, count in taken.protocols],
        max_packets=captures.MAX_PACKETS,
    )
