"""How an account lays out its dashboard, and the stream that tells an open dashboard when there
is something new to look at. For someone signed in."""

import asyncio
import time
from collections.abc import AsyncGenerator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app import answers, dashboard_layout
from app.api.deps import Db, SignedIn, signed_in
from app.dashboard_layout import PRESET_KEYS, Place
from app.models import DashboardLayout, Event, Incident

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(signed_in)])

# How often an open stream looks for something new, how often it says it is still there (nginx
# gives up on a connection that is quiet for a minute), and how long one stream lasts before the
# page connects again, which is how a sign-in that has ended is noticed.
CHECK_SECONDS = 3.0
KEEP_ALIVE_SECONDS = 20.0
STREAM_SECONDS = 600.0


class PlaceModel(BaseModel):
    id: str
    size: Literal["half", "full"]
    hidden: bool


class PresetOut(BaseModel):
    key: str
    title: str
    description: str
    widgets: list[PlaceModel]


class LayoutOut(BaseModel):
    """The dashboard as the account has it, and the presets to start from."""

    # The preset it started from, or None for one of the account's own making.
    preset: str | None
    widgets: list[PlaceModel]
    presets: list[PresetOut]


class LayoutIn(BaseModel):
    preset: Annotated[str, Field(max_length=16)] | None = None
    widgets: Annotated[list[PlaceModel], Field(max_length=len(dashboard_layout.WIDGETS))]

    @model_validator(mode="after")
    def _known(self) -> LayoutIn:
        names = [place.id for place in self.widgets]
        if len(set(names)) != len(names):
            raise ValueError("A widget can only be in the layout once.")
        if unknown := sorted(set(names) - dashboard_layout.WIDGET_IDS):
            raise ValueError(f"There is no widget called {unknown[0][:40]}.")
        if self.preset is not None and self.preset not in PRESET_KEYS:
            raise ValueError("There is no preset by that name.")
        return self


def _place_out(place: Place) -> PlaceModel:
    return PlaceModel(id=place.id, size=place.size, hidden=place.hidden)


def _out(db: Db | Session, auth: SignedIn) -> LayoutOut:
    row = db.get(DashboardLayout, auth.user.id)
    places = (
        dashboard_layout.from_stored(row.widgets)
        if row
        else list(dashboard_layout.default_places())
    )
    return LayoutOut(
        preset=row.preset if row else "overview",
        widgets=[_place_out(place) for place in places],
        presets=[
            PresetOut(
                key=preset.key,
                title=preset.title,
                description=preset.description,
                widgets=[_place_out(place) for place in preset.places],
            )
            for preset in dashboard_layout.PRESETS
        ],
    )


@router.get("/layout")
def get_layout(db: Db, auth: Annotated[SignedIn, Depends(signed_in)]) -> LayoutOut:
    """Which widgets the dashboard shows, in what order and how wide, with the presets
    to start from. An account that has not changed it has the first preset."""
    return _out(db, auth)


@router.put("/layout")
def change_layout(
    body: LayoutIn, db: Db, auth: Annotated[SignedIn, Depends(signed_in)]
) -> LayoutOut:
    """Saves the layout. A widget the request leaves out is added at the end, shown."""
    places = dashboard_layout.complete(
        [Place(item.id, item.size, item.hidden) for item in body.widgets]
    )
    row = db.get(DashboardLayout, auth.user.id)
    if row is None:
        row = DashboardLayout(user_id=auth.user.id)
        db.add(row)
    row.preset = body.preset
    row.widgets = dashboard_layout.to_stored(places)
    db.flush()
    out = _out(db, auth)
    db.commit()
    return out


@router.delete("/layout", status_code=status.HTTP_204_NO_CONTENT)
def reset_layout(db: Db, auth: Annotated[SignedIn, Depends(signed_in)]) -> Response:
    """Puts the first preset back."""
    row = db.get(DashboardLayout, auth.user.id)
    if row is not None:
        db.delete(row)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def signature(db: Session) -> str:
    """What has happened that the dashboard shows: the newest event and incident and the stamp of
    what the owner changed. It differs from the last one exactly when a fresh look could show
    something new."""
    newest = db.scalar(select(func.max(Event.id)))
    seen = db.scalar(select(func.max(Incident.last_seen_at)))
    count = db.scalar(select(func.count()).select_from(Incident))
    return f"{answers.current_stamp(db)}.{newest}.{seen.isoformat() if seen else ''}.{count}"


def _look(sessions: sessionmaker[Session]) -> str:
    with sessions() as db:
        return signature(db)


async def _events(request: Request, sessions: sessionmaker[Session]) -> AsyncGenerator[str]:
    """A ``ready`` when it begins, a ``changed`` each time what the dashboard shows may have, and
    a comment now and then so a quiet stream is not closed. Nothing but a signature goes out."""
    last = await run_in_threadpool(_look, sessions)
    yield f"event: ready\ndata: {last}\n\n"
    started = quiet_since = time.monotonic()
    while time.monotonic() - started < STREAM_SECONDS:
        await asyncio.sleep(CHECK_SECONDS)
        if await request.is_disconnected():
            return
        seen = await run_in_threadpool(_look, sessions)
        if seen != last:
            last = seen
            quiet_since = time.monotonic()
            yield f"event: changed\ndata: {seen}\n\n"
        elif time.monotonic() - quiet_since >= KEEP_ALIVE_SECONDS:
            quiet_since = time.monotonic()
            yield ": still here\n\n"


@router.get("/stream")
async def stream(request: Request, db: Db) -> StreamingResponse:
    """Server-sent events for an open dashboard: it asks for its numbers again as soon as one says
    that something changed, instead of waiting for its next turn. It goes on for ten minutes and
    the page connects again."""
    # Finding who is signed in began a transaction, which would hold a connection of the pool for
    # as long as the stream goes on. Each look below opens a session of its own.
    await run_in_threadpool(db.commit)
    sessions: sessionmaker[Session] = request.app.state.sessions()
    return StreamingResponse(
        _events(request, sessions),
        media_type="text/event-stream",
        # Nothing is kept, and nginx is not to hold it back (docker/nginx/templates/aresgate.conf).
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
