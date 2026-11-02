"""Looking at the certificate a system presents, and whether the choice made under Certificate
would accept it: with real connections to servers that present each kind of certificate."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.integrations import certdiag, netguard, review
from app.integrations.netguard import HOME_NETWORK, HOME_NETWORK_AND_LOOPBACK, Origin, Refused
from tests.stubs import Answer, Certificate, Serve, StubServer, make_certificate, make_chain


def ok(seen: object) -> Answer:
    return Answer(body="ok")


def look(server: StubServer, **choice: Any) -> review.Review:
    origin = netguard.parse_origin(server.url, allow_http=False)
    return asyncio.run(review.review(HOME_NETWORK_AND_LOOPBACK, origin, **choice))


class TestACertificateThatVouchesForItself:
    def test_it_is_shown_with_what_it_says_of_itself(self, serve: Serve) -> None:
        certificate = make_certificate("wazuh.example")
        server = serve(ok, certificate)

        found = look(server)

        assert found.certificate.fingerprint == certificate.fingerprint
        assert found.certificate.subject == "CN=wazuh.example"
        assert found.certificate.names == ["wazuh.example", "127.0.0.1"]
        assert found.certificate.self_signed
        assert found.issuers == []
        # Nothing but the connection was made.
        assert server.seen == []

    def test_it_is_not_accepted_by_the_computers_trusted_certificates_and_says_why(
        self, serve: Serve
    ) -> None:
        found = look(serve(ok, make_certificate()))

        assert not found.accepted
        assert found.verdict == (
            "The certificate isn't trusted: it vouches for itself and nobody else does. If it "
            "is the right system, trust it below."
        )

    def test_it_is_accepted_once_it_is_pasted_as_the_authority(self, serve: Serve) -> None:
        certificate = make_certificate()

        found = look(serve(ok, certificate), mode="ca", ca_pem=certificate.pem)

        assert found.accepted
        assert found.verdict == "The authority you pasted vouches for it."

    def test_another_authority_does_not_vouch_for_it(self, serve: Serve) -> None:
        found = look(serve(ok, make_certificate()), mode="ca", ca_pem=make_certificate().pem)

        assert not found.accepted
        assert certdiag.is_about_a_certificate(found.verdict)

    @pytest.mark.parametrize("pasted", [None, "", "   ", "not a certificate"])
    def test_no_authority_pasted_yet_is_said_so(self, serve: Serve, pasted: str | None) -> None:
        found = look(serve(ok, make_certificate()), mode="ca", ca_pem=pasted)

        assert not found.accepted
        assert found.verdict.startswith("No certificate authority is pasted yet.")


class TestAPinnedCertificate:
    def test_the_one_pinned_is_accepted(self, serve: Serve) -> None:
        certificate = make_certificate()

        found = look(serve(ok, certificate), mode="pinned", pin=certificate.fingerprint)

        assert found.accepted
        assert found.verdict == "It is the certificate you trusted."

    def test_another_one_is_a_changed_certificate_and_both_are_named(self, serve: Serve) -> None:
        trusted = make_certificate()
        presented = make_certificate()

        found = look(serve(ok, presented), mode="pinned", pin=trusted.fingerprint)

        assert not found.accepted
        assert found.verdict.startswith("The certificate has changed: it isn't the one you trusted")
        assert trusted.fingerprint in found.verdict
        assert found.certificate.fingerprint == presented.fingerprint

    def test_nothing_pinned_yet_is_said_so(self, serve: Serve) -> None:
        found = look(serve(ok, make_certificate()), mode="pinned", pin=None)

        assert not found.accepted
        assert found.verdict == "No certificate is trusted yet."

    def test_it_is_accepted_whatever_it_is_even_expired(self, serve: Serve) -> None:
        expired = make_chain(begins_days_ago=30, lasts_days=-1).leaf

        found = look(serve(ok, expired), mode="pinned", pin=expired.fingerprint)

        assert found.accepted
        assert found.certificate.not_after < datetime.now(UTC)


class TestACertificateAnAuthorityIssued:
    def test_the_certificates_sent_with_it_are_listed_after_it(self, serve: Serve) -> None:
        chain = make_chain()

        found = look(serve(ok, chain.full))

        assert found.certificate.fingerprint == chain.full.fingerprint
        assert not found.certificate.self_signed
        assert [issuer.subject for issuer in found.issuers] == ["CN=Test Intermediate"]
        assert [issuer.self_signed for issuer in found.issuers] == [False]

    def test_the_whole_chain_is_accepted_by_the_authority_that_signed_it(
        self, serve: Serve
    ) -> None:
        chain = make_chain()

        found = look(serve(ok, chain.full), mode="ca", ca_pem=chain.root_pem)

        assert found.accepted

    def test_a_certificate_sent_alone_is_told_apart_from_one_signed_by_a_stranger(
        self, serve: Serve
    ) -> None:
        found = look(serve(ok, make_chain().leaf))

        assert not found.accepted
        assert "It sent only its own certificate" in found.verdict

    def test_the_computers_own_trusted_certificates_can_accept_it(
        self, serve: Serve, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        chain = make_chain()
        trusted = tmp_path / "ca.pem"
        trusted.write_text(chain.root_pem)
        monkeypatch.setenv("SSL_CERT_FILE", str(trusted))

        found = look(serve(ok, chain.full))

        assert found.accepted
        assert found.verdict == "This computer already trusts it."


class TestWhenItCannotBeLookedAt:
    def test_an_address_that_is_not_allowed_is_refused(self, serve: Serve) -> None:
        server = serve(ok, make_certificate())
        origin = netguard.parse_origin(server.url, allow_http=False)

        with pytest.raises(Refused, match="isn't a private network address"):
            asyncio.run(review.review(HOME_NETWORK, origin))

    def test_a_system_that_does_not_answer_is_said_so(self, serve: Serve) -> None:
        server = serve(ok, make_certificate())
        origin = netguard.parse_origin(server.url, allow_http=False)
        server.stop()

        with pytest.raises(Refused, match="Couldn't make a secure connection"):
            asyncio.run(review.review(HOME_NETWORK_AND_LOOPBACK, origin))

    def test_a_certificate_that_cannot_be_read_is_refused(
        self, serve: Serve, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        server = serve(ok, make_certificate())
        origin = netguard.parse_origin(server.url, allow_http=False)

        async def junk(*_: object) -> list[bytes]:
            return [b"not a certificate"]

        monkeypatch.setattr(netguard, "look_up_chain", junk)

        with pytest.raises(Refused, match="presented a certificate AresGate can't read"):
            asyncio.run(review.review(HOME_NETWORK_AND_LOOPBACK, origin))

    def test_a_failure_that_is_not_about_the_certificate_is_passed_on_in_words(
        self, serve: Serve, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        certificate: Certificate = make_certificate()
        server = serve(ok, certificate)
        origin = netguard.parse_origin(server.url, allow_http=False)
        present = netguard.present

        async def present_or_fail(policy: Any, where: Origin, context: Any = None) -> Any:
            if context is not None:
                raise Refused("Couldn't make a secure connection to somewhere.")
            return await present(policy, where)

        monkeypatch.setattr(netguard, "present", present_or_fail)

        found = asyncio.run(review.review(HOME_NETWORK_AND_LOOPBACK, origin))

        assert not found.accepted
        assert found.verdict == "Couldn't make a secure connection to somewhere."


class TestWhichFailuresAreAboutACertificate:
    @pytest.mark.parametrize(
        "message",
        [
            "The certificate isn't trusted (self-signed certificate). If it is the right system",
            "The certificate expired on 2026-01-01. Renew it on that system.",
            "The certificate isn't valid until 2027-01-01.",
            "The certificate is for fw.example, not for 192.168.1.1.",
            "The certificate has changed: this system now presents AA, not the one you trusted.",
        ],
    )
    def test_they_are_recognised(self, message: str) -> None:
        assert certdiag.is_about_a_certificate(message)

    @pytest.mark.parametrize(
        "message",
        [
            None,
            "",
            "OPNsense didn't accept the credentials, or the user isn't allowed to read this.",
            "192.168.1.1:443 didn't answer in time.",
            "The secure connection to 192.168.1.1:443 failed (TLS error).",
        ],
    )
    def test_others_are_not(self, message: str | None) -> None:
        assert not certdiag.is_about_a_certificate(message)
