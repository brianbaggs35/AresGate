"""Replies that say "nothing new" instead of sending the same answer again.

A route that opts in sends its answer with a tag. The browser keeps the answer and asks again with
that tag, and while the answer is the same it gets a reply with no body. The answers are for one
signed-in person, so they may only be kept by the browser that asked ("private"), and the browser
has to ask before it uses one ("no-cache"). Nginx lets exactly that header through and sends
"no-store" with everything else.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Response, status

from app.answers import etag_of

KEEPABLE = "private, no-cache"


def _tags(header: str) -> set[str]:
    """The tags in an If-None-Match, without the mark of a weak one."""
    return {tag.strip().removeprefix("W/") for tag in header.split(",")}


@dataclass(frozen=True)
class Conditional:
    """What the request knows about the answer the browser already has."""

    seen: str | None

    def reply(self, body: bytes, etag: str | None = None) -> Response:
        etag = etag or etag_of(body)
        headers = {"ETag": etag, "Cache-Control": KEEPABLE}
        if self.seen is not None and (etag in _tags(self.seen) or "*" in _tags(self.seen)):
            return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
        return Response(body, media_type="application/json", headers=headers)


def conditional(
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
) -> Conditional:
    return Conditional(if_none_match)


Revalidation = Annotated[Conditional, Depends(conditional)]
