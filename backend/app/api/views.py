"""Saved views: the filters and the order of a list kept under a name, for the account that saved
them, so a combination worth having is one tap and not rebuilt each time. Each page keeps up to
20, one of which can be the one the page opens on."""

import re
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
)
from sqlalchemy import func, select, update

from app.api.deps import Db, SignedIn, signed_in
from app.models import SavedView

router = APIRouter(prefix="/views", tags=["views"], dependencies=[Depends(signed_in)])

Page = Literal["incidents", "alerts", "devices", "assets"]
ViewId = Annotated[int, Path(ge=1, le=2**63 - 1)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]

# How many a page may keep, so the list of them stays one to read.
LIMIT = 20
# What a query may hold: it is the route's, so a few short names with short values.
MAX_NAMES = 20
MAX_VALUES = 20
MAX_VALUE_LENGTH = 500
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,39}$")


def _tidy(query: dict[str, str | list[str]]) -> dict[str, str | list[str]]:
    if len(query) > MAX_NAMES:
        raise ValueError(f"A view keeps at most {MAX_NAMES} filters.")
    for name, value in query.items():
        if not _NAME.match(name):
            raise ValueError(f"{name!r} is not the name of a filter.")
        values = [value] if isinstance(value, str) else value
        if len(values) > MAX_VALUES or any(len(item) > MAX_VALUE_LENGTH for item in values):
            raise ValueError(f"What {name} is set to is too long.")
    return query


Query_ = Annotated[dict[str, str | list[str]], AfterValidator(_tidy)]


class ViewOut(BaseModel):
    id: int
    page: Page
    name: str
    query: dict[str, str | list[str]]
    is_default: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime


class ViewList(BaseModel):
    items: list[ViewOut]


class ViewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: Page
    name: Name
    query: Query_
    default: bool = False


class ViewChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    default: bool | None = None


def _out(view: SavedView) -> ViewOut:
    return ViewOut(
        id=view.id,
        page=cast(Page, view.page),
        name=view.name,
        query=cast(dict[str, str | list[str]], view.query),
        is_default=view.is_default,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


def _mine(db: Db, auth: SignedIn, view_id: int) -> SavedView:
    view = db.scalars(
        select(SavedView).where(SavedView.id == view_id, SavedView.user_id == auth.user.id)
    ).first()
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no such view.")
    return view


def _make_default(db: Db, auth: SignedIn, view: SavedView) -> None:
    """Makes this the view its page opens on, and none other."""
    db.execute(
        update(SavedView)
        .where(
            SavedView.user_id == auth.user.id,
            SavedView.page == view.page,
            SavedView.id != view.id,
        )
        .values(is_default=False)
    )
    db.flush()
    view.is_default = True


@router.get("")
def list_views(
    db: Db,
    auth: Annotated[SignedIn, Depends(signed_in)],
    page: Annotated[Page | None, Query(description="Only this page's. Left out, all.")] = None,
) -> ViewList:
    """The views this account kept, by page and then by name."""
    found = select(SavedView).where(SavedView.user_id == auth.user.id)
    if page is not None:
        found = found.where(SavedView.page == page)
    views = db.scalars(found.order_by(SavedView.page, func.lower(SavedView.name), SavedView.id))
    return ViewList(items=[_out(view) for view in views])


@router.post("", status_code=status.HTTP_201_CREATED)
def save_view(
    body: ViewIn, response: Response, db: Db, auth: Annotated[SignedIn, Depends(signed_in)]
) -> ViewOut:
    """Keeps what a list shows under a name. Saving under a name that is taken changes that
    view."""
    view = db.scalars(
        select(SavedView).where(
            SavedView.user_id == auth.user.id,
            SavedView.page == body.page,
            SavedView.name == body.name,
        )
    ).first()
    if view is None:
        kept = db.scalar(
            select(func.count())
            .select_from(SavedView)
            .where(SavedView.user_id == auth.user.id, SavedView.page == body.page)
        )
        if (kept or 0) >= LIMIT:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"You can keep {LIMIT} views for this page. Delete one to save another.",
            )
        view = SavedView(user_id=auth.user.id, page=body.page, name=body.name, query=body.query)
        db.add(view)
    else:
        response.status_code = status.HTTP_200_OK
        view.query = body.query
    db.flush()
    if body.default:
        _make_default(db, auth, view)
    db.commit()
    return _out(view)


@router.patch("/{view_id}")
def change_view(
    view_id: ViewId,
    body: ViewChange,
    db: Db,
    auth: Annotated[SignedIn, Depends(signed_in)],
) -> ViewOut:
    """Renames a view, or makes it the one its page opens on, or stops it being."""
    view = _mine(db, auth, view_id)
    if body.name is not None and body.name != view.name:
        taken = db.scalar(
            select(func.count())
            .select_from(SavedView)
            .where(
                SavedView.user_id == auth.user.id,
                SavedView.page == view.page,
                SavedView.name == body.name,
            )
        )
        if taken:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"You already have a view called {body.name}."
            )
        view.name = body.name
    if body.default is True:
        _make_default(db, auth, view)
    elif body.default is False:
        view.is_default = False
    db.commit()
    return _out(view)


@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_view(view_id: ViewId, db: Db, auth: Annotated[SignedIn, Depends(signed_in)]) -> Response:
    """Forgets a view."""
    db.delete(_mine(db, auth, view_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
