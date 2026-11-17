"""What to try when a request to an integration got no answer, for the API log and the status of
a collector or a connection test.

A message that only says what happened sends the person to guess. The advice is what usually
puts it right, said for the kind of failure and, where the system's own habits are known, for the
system. It is a hint and says so: nothing here is claimed to be the cause, and it never holds a
secret. A failure whose message already says what to do (an untrusted certificate, an address
AresGate won't connect to) has none.
"""

from enum import StrEnum


class Failure(StrEnum):
    """Why a request got no answer."""

    # It didn't answer in time.
    TIMEOUT = "timeout"
    # It couldn't be connected to.
    UNREACHABLE = "unreachable"
    # The certificate or the secure connection failed.
    SECURE = "secure"
    # It connected, and then the connection broke, was reset or wasn't a web server's.
    DROPPED = "dropped"
    # AresGate's own rules kept it from connecting to that address.
    REFUSED = "refused"
    # A fault inside AresGate, not with the system.
    INTERNAL = "internal"
    # Anything else the client says itself: too long an answer, a request it won't send.
    OTHER = "other"


GENERIC = {
    Failure.TIMEOUT: (
        "It may be busy, asleep or slow with this request. Try again in a minute, and if it keeps "
        "happening check that it is running and that nothing between it and AresGate is dropping "
        "traffic."
    ),
    Failure.UNREACHABLE: (
        "Check that the address and port are right and that it is running. If they are, AresGate's "
        "container may not be able to reach it: a firewall, or another network or VLAN, is the "
        "usual reason."
    ),
    Failure.DROPPED: (
        "It accepted the connection and then closed it before a complete answer came. Check that "
        "the address and port are its web interface's, and that the address starts with https:// "
        "for a secure port and http:// for one that isn't. If a reverse proxy is in front, check "
        "that it passes the request on. Its own log usually names the error behind this."
    ),
    Failure.INTERNAL: (
        "This is a fault inside AresGate and not with the system's settings, so changing them "
        "won't help. AresGate's log has the full error: look for the time of this request, and "
        "report it if it keeps happening."
    ),
}

# What is known of one system's habits, added to the generic advice.
SPECIFIC = {
    "ntopng": {
        Failure.DROPPED: (
            "ntopng answers a missing permission with a message of its own, which AresGate would "
            "show, so this isn't a permission. It closes the connection when the script behind "
            "the page fails or ntopng is restarting or overloaded, and its own log names the "
            "script."
        ),
        Failure.TIMEOUT: (
            "ntopng runs a script for each page, and a busy ntopng can take longer than AresGate "
            "waits."
        ),
    },
}

# Pages whose script asks ntopng's alert database, which can be busy or unavailable.
NTOPNG_ALERTS = (
    "This page reads ntopng's alert database, which can be busy or unavailable; ntopng's log "
    "says if it was."
)


def advise(integration: str, kind: Failure, path: str = "") -> str | None:
    """What to try for a request to ``path`` of an integration that failed this way, or None if
    there is nothing more to say than the message does."""
    parts = [GENERIC.get(kind)]
    if kind is not Failure.INTERNAL:
        parts.append(SPECIFIC.get(integration, {}).get(kind))
        if (
            integration == "ntopng"
            and "/alert/" in path
            and kind in (Failure.DROPPED, Failure.TIMEOUT)
        ):
            parts.append(NTOPNG_ALERTS)
    found = " ".join(part for part in parts if part)
    return found or None
