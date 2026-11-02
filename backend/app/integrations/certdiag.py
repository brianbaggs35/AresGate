"""Why a certificate wasn't trusted, in words for whoever set the system up.

OpenSSL says very little when a chain can't be checked: a certificate that was sent without the
one that signed it, and a certificate signed by an authority nobody here knows, both come back as
"unable to get local issuer certificate". They are different problems with different cures, so
the certificates the system presents are looked at (they are the same either way: this only reads
what a browser is shown) and the answer says which one it is and what to change, on the system
or in AresGate.

The most common case at home is a system that serves its own certificate alone (Let's Encrypt's
``cert.pem``) instead of the whole chain (``fullchain.pem``). A browser fetches or remembers the
missing certificate; OpenSSL, and so AresGate, doesn't.
"""

import ssl
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography import x509
from cryptography.x509.oid import AuthorityInformationAccessOID

from app import audit

# What OpenSSL calls them: X509_V_ERR_*, from its documentation of `openssl verify`.
EXPIRED = 10
NOT_YET_VALID = 9
SELF_SIGNED = 18
SELF_SIGNED_IN_CHAIN = 19
NO_ISSUER = 20
NO_FIRST_ISSUER = 21
HOSTNAME_MISMATCH = 62
ADDRESS_MISMATCH = 64

_SHOWN_NAMES = 4
_MAX_URL = 120


@dataclass(frozen=True)
class Presented:
    """What a system presented, as far as an explanation needs: its own certificate first."""

    chain: tuple[x509.Certificate, ...]

    @property
    def leaf(self) -> x509.Certificate:
        return self.chain[0]

    @property
    def top(self) -> x509.Certificate:
        return self.chain[-1]


def read_chain(chain: list[bytes]) -> Presented | None:
    """The certificates a system presented (DER, its own first), or None if they can't be read
    or none was presented."""
    try:
        certificates = tuple(x509.load_der_x509_certificate(der) for der in chain)
    except ValueError:
        return None
    return Presented(certificates) if certificates else None


def name_of(name: x509.Name) -> str:
    """A certificate's subject or issuer as a person would say it: its common name, or else the
    organization (Wazuh's authority has only that), or else the whole name. It came from the
    system, so it's cleaned and kept short."""
    for oid in (x509.oid.NameOID.COMMON_NAME, x509.oid.NameOID.ORGANIZATION_NAME):
        found = name.get_attributes_for_oid(oid)
        if found:
            return audit.clean(str(found[0].value), 60) or "an unnamed authority"
    return audit.clean(name.rfc4514_string(), 60) or "an unnamed authority"


def _names(certificate: x509.Certificate) -> list[str]:
    try:
        alternative = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return []
    values = alternative.value
    found = [str(name) for name in values.get_values_for_type(x509.DNSName)]
    return found + [str(address) for address in values.get_values_for_type(x509.IPAddress)]


def _where_to_get_issuer(certificate: x509.Certificate) -> str | None:
    """The address its certificate gives for the certificate that signed it, if it gives one."""
    try:
        access = certificate.extensions.get_extension_for_class(x509.AuthorityInformationAccess)
    except x509.ExtensionNotFound:
        return None
    for description in access.value:
        address = description.access_location
        if (
            description.access_method == AuthorityInformationAccessOID.CA_ISSUERS
            and isinstance(address, x509.UniformResourceIdentifier)
            and address.value.startswith(("http://", "https://"))
            and len(address.value) <= _MAX_URL
            and address.value.isprintable()
        ):
            return address.value
    return None


def _date(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%d")


def _what_to_do(mode: str, issuer: str) -> str:
    """The cure in AresGate, for a certificate that nothing here vouches for."""
    if mode == "ca":
        return (
            f"add {issuer}'s certificate to the authority pasted under Certificate, or pin its "
            "fingerprint there."
        )
    return f"paste {issuer}'s certificate under Certificate, or pin its fingerprint there."


def _unknown_issuer(presented: Presented, mode: str) -> str:
    top = presented.top
    issuer = name_of(top.issuer)
    if len(presented.chain) > 1:
        return (
            f"The chain it sent ends at {name_of(top.subject)}, issued by {issuer}, and this "
            f"computer doesn't trust {issuer}. If that is your own authority, in AresGate "
            + _what_to_do(mode, issuer)
        )
    source = _where_to_get_issuer(top)
    if source is None:
        return (
            f"It sent only its own certificate, issued by {issuer}, and doesn't say where to get "
            f"{issuer}'s certificate, as a public authority's usually do. That looks like an "
            "authority of the system's own, not Let's Encrypt. In AresGate, "
            + _what_to_do(mode, issuer)
            + " If it should be a public certificate, serve the whole chain on that system "
            "(fullchain.pem)."
        )
    return (
        f"It sent only its own certificate, issued by {issuer}, without {issuer}'s certificate. "
        "Browsers fetch what is missing; AresGate doesn't. Serve the whole chain on that system "
        f"(with Let's Encrypt, fullchain.pem instead of cert.pem). Its certificate says where to "
        f"get it: {source}. Or in AresGate, " + _what_to_do(mode, issuer)
    )


def explain(
    error: ssl.SSLCertVerificationError, presented: Presented | None, mode: str, host: str
) -> str:
    """What is wrong with the system's certificate and what to change, from what OpenSSL said
    (``error``) and what the system presents (``presented``, or None if that couldn't be seen)."""
    code = error.verify_code
    generic = (
        f"The certificate isn't trusted ({error.verify_message}). If it is the right system, "
        "paste the certificate authority that signed it or pin the certificate's fingerprint, "
        "under Certificate."
    )
    if presented is None:
        return generic
    if code in (NO_ISSUER, NO_FIRST_ISSUER):
        return "The certificate isn't trusted. " + _unknown_issuer(presented, mode)
    if code == SELF_SIGNED:
        return (
            "The certificate isn't trusted: it vouches for itself and nobody else does. If it "
            "is the right system, pin the certificate's fingerprint under Certificate, or "
            "paste the certificate there as the authority."
        )
    if code == SELF_SIGNED_IN_CHAIN:
        top = name_of(presented.top.subject)
        return (
            f"The certificate isn't trusted: the chain it sent ends at {top}, which signed "
            f"itself, and this computer doesn't trust {top}. If that is your own authority, in "
            "AresGate " + _what_to_do(mode, top)
        )
    if code == EXPIRED:
        return (
            f"The certificate expired on {_date(presented.leaf.not_valid_after_utc)}. Renew it "
            "on that system."
        )
    if code == NOT_YET_VALID:
        return (
            f"The certificate isn't valid until {_date(presented.leaf.not_valid_before_utc)}. "
            "If that date has passed, check the clocks of both computers."
        )
    if code in (HOSTNAME_MISMATCH, ADDRESS_MISMATCH):
        names = _names(presented.leaf)
        shown = ", ".join(names[:_SHOWN_NAMES]) or "no name AresGate can read"
        more = f" and {len(names) - _SHOWN_NAMES} more" if len(names) > _SHOWN_NAMES else ""
        if not names:
            return (
                f"The certificate is for {shown}, not for {host}. With no name in it to match "
                "to the address, pin the certificate's fingerprint under Certificate."
            )
        return (
            f"The certificate is for {shown}{more}, not for {host}. Use one of those names in "
            "the address (it has to reach this system), or pin the certificate's fingerprint "
            "under Certificate."
        )
    return generic
