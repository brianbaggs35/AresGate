"""What an address on the internet is called.

The programs say what they know of an address (a host name in a flow, a name that was looked up),
and where none did, its reverse lookup (the PTR record, which is the name the address's owner gave
it) says who it is: ``scanner-17.example.net`` is a scanner, ``ec2-…compute.amazonaws.com`` is a
rented server. It is the one thing AresGate looks up on the internet by itself, and only for an
address that is on the internet, only to the resolver the machine already uses and only when
``ARESGATE_REVERSE_DNS`` is on (it is, until it is turned off). Answers are kept, so an address is
asked about once a week, or once a day where it had no name.
"""

import socket
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from ipaddress import ip_address
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AddressName

Resolver = Callable[[str], str | None]

# How long an answer is kept, and one that was "no name" is.
KEEP: Final = timedelta(days=7)
KEEP_NONE: Final = timedelta(days=1)
# How many addresses one page asks about, and how long it waits for the answers: a resolver that is
# slow or down never holds a page up for longer.
MAX_LOOKUPS: Final = 6
WAIT: Final = 2.0


def system_resolver(address: str) -> str | None:
    """The name the machine's resolver gives an address, or None where it has none."""
    try:
        return socket.gethostbyaddr(address)[0].rstrip(".").lower() or None
    except OSError, UnicodeError:
        return None


# What looks addresses up: the machine's resolver, or a stand-in (the end-to-end test server
# replaces it, so that no test asks the internet).
resolver: Resolver = system_resolver


def _public(address: str) -> bool:
    try:
        return ip_address(address).is_global
    except ValueError:
        return False


def _fresh(row: AddressName, now: datetime) -> bool:
    return row.looked_up_at + (KEEP if row.name else KEEP_NONE) > now


def _ask(addresses: list[str]) -> dict[str, str | None]:
    """What the resolver answered for each address in time. One that did not answer, or failed, is
    left out, so that it is asked again and not remembered as having no name."""
    pool = ThreadPoolExecutor(max_workers=MAX_LOOKUPS)
    try:
        asked = {pool.submit(resolver, address): address for address in addresses}
        done, _ = wait(asked, timeout=WAIT)
        answers: dict[str, str | None] = {}
        for future in done:
            if future.exception() is None:
                answers[asked[future]] = future.result()
        return answers
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def lookup(db: Session, addresses: Iterable[str], now: datetime) -> dict[str, str]:
    """The names of the addresses that are on the internet and have one, from what is kept and from
    asking about the rest. The caller commits what was kept."""
    if not get_settings().reverse_dns:
        return {}
    wanted = sorted({address for address in addresses if _public(address)})
    if not wanted:
        return {}
    rows = {
        row.address: row
        for row in db.scalars(select(AddressName).where(AddressName.address.in_(wanted)))
    }
    stale = [address for address in wanted if address not in rows or not _fresh(rows[address], now)]
    for address, name in _ask(stale[:MAX_LOOKUPS]).items():
        row = rows.get(address)
        if row is None:
            row = rows[address] = AddressName(address=address)
            db.add(row)
        row.name = name
        row.looked_up_at = now
    return {address: row.name for address, row in rows.items() if row.name}
