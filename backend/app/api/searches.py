"""Saved searches: a search in words kept under a name, for the page it was made on, so it can be
used again with one tap. For someone signed in."""

from collections.abc import Callable
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, select

from app.api import asking
from app.api.deps import Db, signed_in
from app.events import search as event_search
from app.incidents import search as incident_search
from app.models import SavedSearch
from app.querylang import MAX_LENGTH, Context, Search, SearchError

router = APIRouter(prefix="/searches", tags=["searches"], dependencies=[Depends(signed_in)])

Scope = Literal["incidents", "logs"]
SearchId = Annotated[int, Path(ge=1, le=2**63 - 1)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Words = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_LENGTH)
]

# How many a page may keep, so the list in the search box stays one to read.
LIMIT = 50

# What each page's words mean.
LANGUAGES: dict[Scope, Callable[[str, Context], Search]] = {
    "incidents": incident_search.parse,
    "logs": event_search.parse,
}


class SavedOut(BaseModel):
    id: int
    scope: Scope
    name: str
    query: str
    created_at: AwareDatetime
    updated_at: AwareDatetime


class SavedList(BaseModel):
    items: list[SavedOut]


class SavedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Scope
    name: Name
    query: Words


def _out(saved: SavedSearch) -> SavedOut:
    return SavedOut(
        id=saved.id,
        scope=cast(Scope, saved.scope),
        name=saved.name,
        query=saved.query,
        created_at=saved.created_at,
        updated_at=saved.updated_at,
    )


@router.get("")
def list_searches(scope: Annotated[Scope, Query()], db: Db) -> SavedList:
    """The searches kept for a page, by name."""
    found = db.scalars(
        select(SavedSearch)
        .where(SavedSearch.scope == scope)
        .order_by(func.lower(SavedSearch.name), SavedSearch.id)
    ).all()
    return SavedList(items=[_out(saved) for saved in found])


@router.post("", status_code=status.HTTP_201_CREATED)
def save_search(body: SavedIn, response: Response, db: Db) -> SavedOut:
    """Keeps a search under a name. One that can't be read is refused in the words of the search
    itself, and saving under a name that is taken changes that search."""
    try:
        LANGUAGES[body.scope](body.query, asking.context(None))
    except SearchError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None
    saved = db.scalars(
        select(SavedSearch).where(SavedSearch.scope == body.scope, SavedSearch.name == body.name)
    ).first()
    if saved is None:
        kept = db.scalar(
            select(func.count()).select_from(SavedSearch).where(SavedSearch.scope == body.scope)
        )
        if (kept or 0) >= LIMIT:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"You can keep {LIMIT} searches for this page. Delete one to save another.",
            )
        saved = SavedSearch(scope=body.scope, name=body.name, query=body.query)
        db.add(saved)
    else:
        response.status_code = status.HTTP_200_OK
        saved.query = body.query
    db.commit()
    return _out(saved)


@router.delete("/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_search(search_id: SearchId, db: Db) -> Response:
    """Forgets a saved search."""
    saved = db.get(SavedSearch, search_id)
    if saved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There's no such saved search.")
    db.delete(saved)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
