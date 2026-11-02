"""Why a certificate wasn't trusted: a certificate sent without the one that signed it is told
apart from one signed by an authority nobody here knows, with real connections to servers that
present each chain."""

import ssl
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.integrations import certdiag, netguard
from app.integrations import client as client_module
from app.integrations.client import CallFailed
from tests.stubs import Answer, Certificate, Serve, make_certificate, make_chain
from tests.test_integration_client import Log, request, target

ISSUER_URL = "http://int.example/intermediate.crt"


def refused(served: Certificate, serve: Serve, **options: object) -> str:
    """What the client says when it can't trust the certificate a server presents."""
    server = serve(lambda seen: Answer(), served)
    log = Log()
    system = target(server, **options)  # type: ignore[arg-type]
    with pytest.raises(CallFailed) as raised:
        request(system, log, "GET", "/x")
    assert server.seen == []
    assert log.calls[0].error == str(raised.value)
    return str(raised.value)


@dataclass(frozen=True)
class WazuhStyle:
    """What Wazuh's certificate tool makes: an authority with only an organization for a name and
    no key usage extension, and a certificate it signed that is served alone."""

    root_pem: str
    indexer: Certificate


def wazuh_style() -> WazuhStyle:
    now = datetime.now(UTC)
    root_key, leaf_key = (
        ec.generate_private_key(ec.SECP256R1()),
        ec.generate_private_key(ec.SECP256R1()),
    )
    wazuh = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Wazuh"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Wazuh"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "California"),
        ]
    )

    def build(
        subject: x509.Name, issuer: x509.Name, key: ec.EllipticCurvePrivateKey, *, authority: bool
    ) -> x509.CertificateBuilder:
        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30))
            .add_extension(
                x509.BasicConstraints(ca=authority, path_length=None), critical=authority
            )
        )
        if not authority:
            builder = builder.add_extension(
                x509.SubjectAlternativeName(
                    [x509.DNSName("localhost"), x509.IPAddress(ip_address("127.0.0.1"))]
                ),
                critical=False,
            )
        return builder

    root = build(wazuh, wazuh, root_key, authority=True).sign(root_key, hashes.SHA256())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "indexer")])
    leaf = build(name, wazuh, leaf_key, authority=False).sign(root_key, hashes.SHA256())
    return WazuhStyle(
        root_pem=root.public_bytes(serialization.Encoding.PEM).decode(),
        indexer=Certificate(
            pem=leaf.public_bytes(serialization.Encoding.PEM).decode(),
            key_pem=leaf_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode(),
            der=leaf.public_bytes(serialization.Encoding.DER),
        ),
    )


class TestAnAuthorityOfTheSystemsOwn:
    """A certificate from the authority a product made for itself, as Wazuh's indexer has, which
    isn't a Let's Encrypt certificate whatever is installed on the same product's dashboard."""

    def test_it_is_named_and_not_taken_for_a_public_one(self, serve: Serve) -> None:
        message = refused(wazuh_style().indexer, serve)

        assert message.startswith(
            "The certificate isn't trusted. It sent only its own certificate, issued by Wazuh, "
            "and doesn't say where to get Wazuh's certificate"
        )
        assert "That looks like an authority of the system's own, not Let's Encrypt." in message
        assert (
            "paste Wazuh's certificate under Certificate, or review its certificate under "
            "Certificate and trust it"
        ) in message
        assert "If it should be a public certificate, serve the whole chain" in message
        assert len(message) <= client_module.MAX_ERROR

    def test_the_authority_pasted_is_accepted_though_it_has_no_key_usage(
        self, serve: Serve
    ) -> None:
        wazuh = wazuh_style()
        server = serve(lambda seen: Answer(body="ok"), wazuh.indexer)

        reply = request(target(server, mode="ca", ca_pem=wazuh.root_pem), Log(), "GET", "/")

        assert reply.text == "ok"

    def test_so_is_a_chain_of_authorities_made_that_way(self, serve: Serve) -> None:
        chain = make_chain(authority_key_usage=False)
        server = serve(lambda seen: Answer(body="ok"), chain.full)

        reply = request(target(server, mode="ca", ca_pem=chain.root_pem), Log(), "GET", "/")

        assert reply.text == "ok"

    def test_its_certificate_can_be_pinned(self, serve: Serve) -> None:
        wazuh = wazuh_style()
        server = serve(lambda seen: Answer(body="ok"), wazuh.indexer)

        where = target(server, mode="pinned", pin=wazuh.indexer.fingerprint)

        assert request(where, Log(), "GET", "/").text == "ok"


class TestACertificateSentWithoutTheOneThatSignedIt:
    def test_it_says_so_and_says_to_serve_the_whole_chain(self, serve: Serve) -> None:
        chain = make_chain(issuer_url=ISSUER_URL)

        message = refused(chain.leaf, serve, mode="ca", ca_pem=chain.root_pem)

        assert message.startswith("The certificate isn't trusted. It sent only its own certificate")
        assert "issued by Test Intermediate, without Test Intermediate's certificate." in message
        assert "Serve the whole chain on that system (with Let's Encrypt, fullchain.pem" in message
        assert f"Its certificate says where to get it: {ISSUER_URL}." in message
        assert "add Test Intermediate's certificate to the authority pasted" in message

    def test_it_says_what_to_paste_when_no_authority_has_been(self, serve: Serve) -> None:
        message = refused(make_chain().leaf, serve)

        assert "paste Test Intermediate's certificate under Certificate" in message
        assert "Its certificate says where to get it" not in message
        assert "doesn't say where to get Test Intermediate's certificate" in message

    def test_the_whole_chain_is_trusted_with_the_authority_that_signed_it(
        self, serve: Serve
    ) -> None:
        chain = make_chain()
        server = serve(lambda seen: Answer(body="ok"), chain.full)

        reply = request(target(server, mode="ca", ca_pem=chain.root_pem), Log(), "GET", "/")

        assert reply.text == "ok"

    def test_pasting_the_intermediate_works_without_the_chain(self, serve: Serve) -> None:
        chain = make_chain()
        server = serve(lambda seen: Answer(body="ok"), chain.leaf)

        where = target(server, mode="ca", ca_pem=chain.intermediate_pem)

        assert request(where, Log(), "GET", "/").text == "ok"

    def test_pinning_works_without_the_chain(self, serve: Serve) -> None:
        chain = make_chain()
        server = serve(lambda seen: Answer(body="ok"), chain.leaf)

        where = target(server, mode="pinned", pin=chain.leaf.fingerprint)

        assert request(where, Log(), "GET", "/").text == "ok"


class TestAChainFromAnAuthorityNotTrusted:
    def test_it_says_where_the_chain_ends_and_who_to_trust(self, serve: Serve) -> None:
        message = refused(make_chain().full, serve)

        assert message.startswith("The certificate isn't trusted. The chain it sent ends at")
        assert "Test Intermediate, issued by Test Root, and this computer doesn't trust" in message
        assert "paste Test Root's certificate under Certificate" in message

    def test_a_wrong_authority_pasted_is_told_the_same_way(self, serve: Serve) -> None:
        chain, other = make_chain(), make_chain()

        message = refused(chain.full, serve, mode="ca", ca_pem=other.root_pem)

        assert "issued by Test Root, and this computer doesn't trust Test Root" in message
        assert "add Test Root's certificate to the authority pasted" in message

    def test_a_root_that_was_sent_but_isnt_trusted_is_named(self, serve: Serve) -> None:
        chain = make_chain()
        everything = replace(chain.full, pem=chain.full.pem + chain.root_pem)

        message = refused(everything, serve)

        assert "the chain it sent ends at Test Root, which signed itself" in message
        assert "paste Test Root's certificate under Certificate" in message


def test_a_certificate_that_vouches_for_itself_can_be_reviewed_and_trusted(serve: Serve) -> None:
    message = refused(make_certificate(), serve)

    assert message == (
        "The certificate isn't trusted: it vouches for itself and nobody else does. If it is "
        "the right system, review its certificate under Certificate and trust it."
    )


def test_an_expired_certificate_says_when_it_expired(serve: Serve) -> None:
    chain = make_chain(begins_days_ago=10, lasts_days=-5)
    ended = (datetime.now(UTC) - timedelta(days=5)).strftime("%Y-%m-%d")

    message = refused(chain.full, serve, mode="ca", ca_pem=chain.root_pem)

    assert message == (
        f"The certificate expired on {ended}. Renew it on that system, or if you know better, "
        "review its certificate under Certificate and trust it as it is."
    )


def test_a_certificate_that_is_not_valid_yet_says_when_it_will_be(serve: Serve) -> None:
    chain = make_chain(begins_days_ago=-3)
    starts = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%d")

    message = refused(chain.full, serve, mode="ca", ca_pem=chain.root_pem)

    assert message == (
        f"The certificate isn't valid until {starts}. "
        "If that date has passed, check the clocks of both computers, or review its "
        "certificate under Certificate and trust it as it is."
    )


def test_a_certificate_for_other_names_says_which(serve: Serve) -> None:
    names = ("nas.example", "nas.home.arpa", "a.example", "b.example", "c.example")
    chain = make_chain(dns_names=names, address=False)

    message = refused(chain.full, serve, mode="ca", ca_pem=chain.root_pem)

    assert message == (
        "The certificate is for nas.example, nas.home.arpa, a.example, b.example and 1 more, "
        "not for 127.0.0.1. Use one of those names in the address (it has to reach this system), "
        "or review its certificate under Certificate and trust it."
    )


def test_a_chain_that_cannot_be_looked_at_again_gets_what_openssl_said(
    serve: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def nothing(*args: object) -> list[bytes]:
        raise netguard.Refused("no")

    monkeypatch.setattr(netguard, "look_up_chain", nothing)

    message = refused(make_chain().leaf, serve)

    assert message == (
        "The certificate isn't trusted (unable to get local issuer certificate). If it is the "
        "right system, review its certificate under Certificate and trust it, or paste the "
        "certificate authority that signed it."
    )


def error(code: int, message: str = "a reason") -> ssl.SSLCertVerificationError:
    problem = ssl.SSLCertVerificationError(1, message)
    problem.verify_code = code
    problem.verify_message = message
    return problem


class TestReadingWhatWasPresented:
    def test_certificates_that_cannot_be_read_are_not_guessed_at(self) -> None:
        assert certdiag.read_chain([b"not a certificate"]) is None
        assert certdiag.read_chain([]) is None

    def test_it_reads_the_certificates_in_the_order_they_came(self) -> None:
        chain = make_chain()
        presented = certdiag.read_chain([chain.leaf.der, chain.full.der])

        assert presented is not None
        assert presented.leaf is presented.chain[0]
        assert presented.top is presented.chain[-1]

    def test_a_reason_it_has_no_words_for_is_given_as_openssl_said_it(self) -> None:
        presented = certdiag.read_chain([make_chain().leaf.der])

        message = certdiag.explain(error(7, "bad signature"), presented, "system", "h")

        assert message.startswith("The certificate isn't trusted (bad signature).")

    def test_nothing_can_be_said_of_a_certificate_that_could_not_be_looked_at(self) -> None:
        message = certdiag.explain(error(certdiag.NO_ISSUER, "no issuer"), None, "system", "h")

        assert message.startswith("The certificate isn't trusted (no issuer).")

    def test_a_certificate_without_a_list_of_names_says_so(self) -> None:
        presented = certdiag.read_chain([make_chain(dns_names=(), address=False).leaf.der])

        message = certdiag.explain(error(certdiag.HOSTNAME_MISMATCH), presented, "ca", "nas")

        assert message == (
            "The certificate is for no name AresGate can read, not for nas. With no name in it "
            "to match to the address, pin the certificate's fingerprint under Certificate."
        )

    def test_a_certificate_for_an_address_says_the_address(self) -> None:
        presented = certdiag.read_chain([make_chain(dns_names=(), address=True).leaf.der])

        message = certdiag.explain(error(certdiag.ADDRESS_MISMATCH), presented, "ca", "nas")

        assert message.startswith("The certificate is for 127.0.0.1, not for nas.")

    @pytest.mark.parametrize("url", ["ftp://x.example/i.crt", "http://x.example/" + "a" * 200])
    def test_an_address_for_the_issuer_that_is_not_a_web_address_or_too_long_is_left_out(
        self, url: str
    ) -> None:
        presented = certdiag.read_chain([make_chain(issuer_url=url).leaf.der])

        message = certdiag.explain(error(certdiag.NO_ISSUER), presented, "system", "h")

        assert "where to get it" not in message

    def test_a_name_is_the_common_name_or_else_the_organization_or_the_whole_name(self) -> None:
        organization = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Home Org")])
        common = x509.Name(
            [
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Home Org"),
                x509.NameAttribute(NameOID.COMMON_NAME, "Home CA"),
            ]
        )
        place = x509.Name([x509.NameAttribute(NameOID.LOCALITY_NAME, "Halifax")])

        assert certdiag.name_of(common) == "Home CA"
        assert certdiag.name_of(organization) == "Home Org"
        assert certdiag.name_of(place) == "L=Halifax"
        assert certdiag.name_of(x509.Name([])) == "an unnamed authority"

    def test_a_certificate_with_no_names_at_all_says_so(self) -> None:
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "OPNsense.localdomain")])
        now = datetime.now(UTC)
        bare = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256())
        )
        presented = certdiag.read_chain([bare.public_bytes(serialization.Encoding.DER)])

        message = certdiag.explain(error(certdiag.HOSTNAME_MISMATCH), presented, "ca", "nas")

        assert message.startswith("The certificate is for no name AresGate can read, not for nas.")


ALL_REASONS = [
    certdiag.EXPIRED,
    certdiag.NOT_YET_VALID,
    certdiag.SELF_SIGNED,
    certdiag.SELF_SIGNED_IN_CHAIN,
    certdiag.NO_ISSUER,
    certdiag.NO_FIRST_ISSUER,
    certdiag.HOSTNAME_MISMATCH,
    certdiag.ADDRESS_MISMATCH,
    7,
]


class TestSayingHowToTrustTheCertificate:
    @pytest.mark.parametrize("code", ALL_REASONS)
    @pytest.mark.parametrize("mode", ["system", "ca"])
    def test_every_reason_is_about_a_certificate_and_offers_to_trust_it(
        self, code: int, mode: str
    ) -> None:
        presented = certdiag.read_chain([make_chain().full.der, make_chain().leaf.der])

        message = certdiag.explain(error(code), presented, mode, "h")

        assert certdiag.is_about_a_certificate(message)
        assert "review its certificate under Certificate and trust it" in message

    @pytest.mark.parametrize("code", ALL_REASONS)
    def test_where_the_certificate_is_in_view_it_says_to_trust_it_below(self, code: int) -> None:
        presented = certdiag.read_chain([make_certificate().der])

        message = certdiag.explain(
            error(code), presented, "system", "h", trust=certdiag.TRUST_BELOW
        )

        assert "trust it below" in message
        assert "review its certificate" not in message

    def test_a_certificate_that_could_not_be_looked_at_offers_it_too(self) -> None:
        message = certdiag.explain(error(certdiag.SELF_SIGNED), None, "system", "h")

        assert "review its certificate under Certificate and trust it" in message
