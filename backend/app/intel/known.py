"""What AresGate knows from threat intelligence: every answer kept, newest first, to look through
without asking a service anything."""

from dataclasses import dataclass
from typing import get_args

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.intel import virustotal
from app.models import IntelSubject

JUDGEMENTS: tuple[str, ...] = get_args(virustotal.Judgement.__value__)
MAX_PAGE = 100
MAX_TEXT = 253


@dataclass(frozen=True)
class Page:
    """One page of the answers kept, with how many there are of each judgement."""

    rows: list[IntelSubject]
    # How many answers match the search, with and without the judgement asked for.
    total: int
    counts: dict[str, int]


def _escaped(text: str) -> str:
    """The text as a pattern that matches it anywhere, with nothing in it read as a wildcard."""
    cleaned = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{cleaned}%"


def page(
    db: Session,
    provider: str,
    *,
    text: str = "",
    kind: str | None = None,
    judgement: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> Page:
    """The answers kept that match: the text is looked for in the address or name and in the owner.
    The counts are of everything the text and the kind match, whichever judgement is asked for."""
    matching: list[ColumnElement[bool]] = [IntelSubject.provider == provider]
    if text:
        pattern = _escaped(text.lower())
        matching.append(
            or_(
                func.lower(func.coalesce(IntelSubject.host, "")).like(pattern, escape="\\"),
                func.lower(func.coalesce(IntelSubject.owner, "")).like(pattern, escape="\\"),
            )
        )
    if kind is not None:
        matching.append(IntelSubject.kind == kind)
    counted: dict[str, int] = {}
    for name, count in db.execute(
        select(IntelSubject.judgement, func.count())
        .where(*matching)
        .group_by(IntelSubject.judgement)
    ):
        counted[name] = count
    counts = {name: counted.get(name, 0) for name in JUDGEMENTS}
    if judgement is not None:
        matching.append(IntelSubject.judgement == judgement)
    rows = list(
        db.scalars(
            select(IntelSubject)
            .where(*matching)
            .order_by(IntelSubject.checked_at.desc(), IntelSubject.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    total = counts[judgement] if judgement is not None else sum(counts.values())
    return Page(rows=rows, total=total, counts=counts)
