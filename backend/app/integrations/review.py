"""Looking at the certificate a system presents, so that someone can decide to trust it.

Most systems at home make a certificate for themselves, which nothing here vouches for. Rather
than send whoever sets AresGate up to find a fingerprint and paste it, AresGate connects, takes
what the system presents (nothing is sent over the connection), shows it, and says whether the
choice made under Certificate would accept it and, if not, why. Trusting it is then one click: it
is pinned by its fingerprint, and the connection from then on accepts that certificate and no
other.

Whatever is presented is shown, expired and self-signed included: it is for the person to decide
whether it is the right system, comparing the fingerprint with what the system itself shows.
"""

import hmac
import ssl
from dataclasses import dataclass

from app.integrations import certdiag, netguard
from app.integrations.client import in_chain
from app.integrations.netguard import AddressPolicy, CertificateInfo, Origin, Refused


@dataclass(frozen=True)
class Review:
    """What a system presents, and what the choice made under Certificate makes of it."""

    # Its own certificate, which is the one that is pinned ...
    certificate: CertificateInfo
    # ... and the others it sent with it, which vouch for it.
    issuers: list[CertificateInfo]
    # Whether the connection would accept it as things are chosen, and in words why or why not.
    accepted: bool
    verdict: str


def _pinned(pin: str | None, certificate: CertificateInfo) -> tuple[bool, str]:
    if pin is None:
        return False, "No certificate is trusted yet."
    if hmac.compare_digest(pin, certificate.fingerprint):
        return True, "It is the certificate you trusted."
    return False, (
        f"The certificate has changed: it isn't the one you trusted (that was {pin}). If you "
        "renewed or replaced it, trust this one instead. If you didn't, something else may be "
        "answering at this address."
    )


async def _checked(
    policy: AddressPolicy,
    origin: Origin,
    mode: str,
    ca_pem: str | None,
    chain: list[bytes],
) -> tuple[bool, str]:
    """Whether the computer's trusted certificates (or the authority pasted in) vouch for the
    certificate: a real connection that checks it, which the other connections do too."""
    if mode == "ca":
        try:
            ca_pem = netguard.clean_ca_pem(ca_pem or "")
        except ValueError as problem:
            return False, f"No certificate authority is pasted yet. {problem}"
    try:
        secured = await netguard.present(policy, origin, netguard.tls_context(mode, ca_pem))
    except Refused as refusal:
        if untrusted := in_chain(refusal, ssl.SSLCertVerificationError):
            return False, certdiag.explain(
                untrusted,
                certdiag.read_chain(chain),
                mode,
                origin.host,
                trust=certdiag.TRUST_BELOW,
            )
        return False, str(refusal)
    await secured.aclose()
    if mode == "ca":
        return True, "The authority you pasted vouches for it."
    return True, "This computer already trusts it."


async def review(
    policy: AddressPolicy,
    origin: Origin,
    mode: str = "system",
    ca_pem: str | None = None,
    pin: str | None = None,
) -> Review:
    """The certificates the system at ``origin`` presents and whether the way of checking given
    (what is chosen under Certificate) would accept them. Raises ``Refused`` if they can't be
    looked at."""
    chain = await netguard.look_up_chain(policy, origin)
    try:
        described = [netguard.describe_certificate(der) for der in chain]
    except ValueError as error:
        raise Refused(f"{origin.host} presented a certificate AresGate can't read.") from error
    own, *issuers = described
    if mode == "pinned":
        accepted, verdict = _pinned(pin, own)
    else:
        accepted, verdict = await _checked(policy, origin, mode, ca_pem, chain)
    return Review(own, issuers, accepted, verdict)
