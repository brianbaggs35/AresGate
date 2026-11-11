"""Trust: the owner's decisions that something is safe, in words.

A trust decision is a verdict that keeps what it matches from raising an alarm (see
``verdicts.MUTING``). This says what one is about, in a sentence a person can read.
"""

from ipaddress import IPv4Network, IPv6Network

from app.incidents import rules
from app.models import VerdictRule


def destination_text(network: IPv4Network | IPv6Network) -> str:
    """A single address as itself, and a network in the notation of its prefix."""
    single = network.prefixlen == network.max_prefixlen
    return str(network.network_address) if single else str(network)


def about(rule: VerdictRule) -> str:
    """What a decision is about, as a sentence a person can read."""
    signature = f"“{rule.signature}”" if rule.signature else None
    source = rules.name_of(rule.source) if rule.source else None
    if rule.address is not None and rule.destination is not None:
        text = f"What {rule.address} sends to {destination_text(rule.destination)}"
    elif rule.address is not None:
        text = f"Everything about {rule.address}"
    elif signature:
        text = f"Every {signature} alert"
    else:
        text = f"Everything {source} reports"
    if signature and rule.address is not None:
        text += f", when it is {signature}"
    if source and not (rule.address is None and signature is None):
        text += f", as reported by {source}"
    return text
