"""Web servers on this machine that answer like the systems AresGate connects to, for tests that
need real connections. They live in ``e2e.stand_ins``, which the end-to-end harness uses too."""

from abc import abstractmethod
from typing import Protocol

from e2e.stand_ins import (
    Answer,
    Certificate,
    Handler,
    Seen,
    StubServer,
    make_certificate,
)

__all__ = [
    "Answer",
    "Certificate",
    "Handler",
    "Seen",
    "Serve",
    "StubServer",
    "make_certificate",
]


class Serve(Protocol):
    """The ``serve`` fixture: starts a server that answers like an integration."""

    @abstractmethod
    def __call__(self, handler: Handler, certificate: Certificate | None = None) -> StubServer:
        """Starts the server, which is stopped when the test ends."""
