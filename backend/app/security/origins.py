"""Which web addresses count as AresGate's own: the one it is served from, and, away from
production, the web app's dev server and the end-to-end tests' copy of it."""

from urllib.parse import urlsplit

from app.config import Settings

# The web app's dev server and the end-to-end tests serve it over plain HTTP on this computer.
_DEV_HOSTS = frozenset({"localhost", "127.0.0.1"})


def is_dev_server_origin(origin: str) -> bool:
    """Whether the origin is plain HTTP on this computer, with or without a port."""
    try:
        parts = urlsplit(origin)
        port = parts.port
    except ValueError:
        return False
    host = parts.hostname
    expected = host if port is None else f"{host}:{port}"
    return (
        parts.scheme == "http"
        and host in _DEV_HOSTS
        and parts.netloc == expected
        and origin == f"{parts.scheme}://{parts.netloc}"
    )


def is_own_origin(settings: Settings, origin: str) -> bool:
    """Whether a page served from the origin is AresGate's own."""
    return origin == settings.public_origin or (
        not settings.is_production and is_dev_server_origin(origin)
    )
