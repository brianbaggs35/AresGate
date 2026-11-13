"""Alerts by email: checking a mail server's settings, turning a message into an email, and
sending it, with what goes wrong said in words."""

import asyncio
import dataclasses
import ipaddress
import smtplib
import socketserver
import ssl
import threading
from datetime import UTC, datetime
from email import message_from_bytes
from email.message import EmailMessage
from typing import Any, ClassVar

import pytest

from app.alerts import mail
from app.alerts.discord import Sent
from app.alerts.discord import message as discord_message
from app.integrations import netguard

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
SERVER = mail.Server(
    host="smtp.example.com",
    port=587,
    security="starttls",
    username="alerts",
    password="correct horse",
    sender="alerts@example.com",
)
BOX = mail.Mailbox(SERVER, "me@example.org")


def payload(**changes: Any) -> dict[str, object]:
    fields: dict[str, Any] = {
        "title": "**Brute force** on ssh",
        "description": (
            "From 93.184.216.34.\n[Open the incident](https://ares.example/incidents/4) now."
        ),
        "footer": "AresGate · incident 4",
        "link": "https://ares.example/incidents/4",
        "fields": [("Where", "web1 (192.168.1.20)", True)],
        "at": NOW,
    }
    fields.update(changes)
    return discord_message(**fields)


class TestCheckingAnAddress:
    @pytest.mark.parametrize(
        "text", ["me@example.org", "  first.last+tag@sub.example.co.uk  ", "a_b-c@example.io"]
    )
    def test_an_email_address_is_accepted_and_trimmed(self, text: str) -> None:
        assert mail.check_address(text, "recipient") == text.strip()

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "plain",
            "no@dot",
            "two@@example.org",
            "a b@example.org",
            "Name <me@example.org>",
            "me@example.org, you@example.org",
            "me@example.org\nBcc: x@example.org",
            "me@exa mple.org",
            "x" * 250 + "@example.org",
            "@example.org",
        ],
    )
    def test_anything_else_is_refused_on_the_field(self, text: str) -> None:
        with pytest.raises(mail.InvalidSettings) as refused:
            mail.check_address(text, "recipient")

        assert refused.value.field == "recipient"
        assert str(refused.value)


class TestCheckingTheServer:
    def check(self, **changes: Any) -> tuple[str, str | None, str]:
        fields: dict[str, Any] = {
            "host": " SMTP.Example.com. ",
            "port": 587,
            "security": "starttls",
            "username": " alerts ",
            "sender": "alerts@example.com",
            "has_password": True,
        }
        fields.update(changes)
        return mail.check_server(**fields)

    def test_it_is_cleaned(self) -> None:
        assert self.check() == ("smtp.example.com", "alerts", "alerts@example.com")

    def test_a_server_that_needs_no_sign_in_can_be_reached_without_encryption(self) -> None:
        assert self.check(security="none", username=" ", has_password=False) == (
            "smtp.example.com",
            None,
            "alerts@example.com",
        )

    @pytest.mark.parametrize(
        ("changes", "field"),
        [
            ({"host": ""}, "host"),
            ({"host": "not a host"}, "host"),
            ({"host": "-bad.example.com"}, "host"),
            ({"host": "a" * 254}, "host"),
            ({"port": 0}, "port"),
            ({"port": 65536}, "port"),
            ({"security": "tls13"}, "security"),
            ({"username": "a\nb"}, "username"),
            ({"username": "x" * 300}, "username"),
            ({"security": "none"}, "security"),
            ({"security": "none", "username": None}, "security"),
            ({"username": None}, "username"),
            ({"sender": "nobody"}, "sender"),
        ],
    )
    def test_what_cannot_be_used_is_refused_on_its_field(
        self, changes: dict[str, Any], field: str
    ) -> None:
        with pytest.raises(mail.InvalidSettings) as refused:
            self.check(**changes)

        assert refused.value.field == field

    @pytest.mark.parametrize("password", ["", "x" * 2000, "a\nb", "a\x00b"])
    def test_a_password_that_cannot_be_sent_is_refused_without_repeating_it(
        self, password: str
    ) -> None:
        with pytest.raises(mail.InvalidSettings) as refused:
            mail.check_password(password)

        assert refused.value.field == "password"
        assert password not in str(refused.value) or not password

    def test_a_password_is_otherwise_kept_as_it_is(self) -> None:
        assert mail.check_password(" p@ss w0rd ") == " p@ss w0rd "

    def test_a_server_never_shows_its_password(self) -> None:
        assert "correct horse" not in repr(SERVER)
        assert "correct horse" not in repr(BOX)


class TestTheEmail:
    def rendered(self, body: dict[str, object] | None = None) -> EmailMessage:
        return mail.render(body or payload(), SERVER, "me@example.org")

    def test_the_title_is_the_subject_and_the_message_says_who_it_is_between(self) -> None:
        mail_ = self.rendered()

        assert mail_["Subject"] == "[AresGate] Brute force on ssh"
        assert mail_["From"] == "alerts@example.com"
        assert mail_["To"] == "me@example.org"
        assert mail_["Auto-Submitted"] == "auto-generated"
        assert mail_["Message-ID"].endswith("@example.com>")
        assert mail_["Date"]

    def test_discords_writing_is_plain_words_in_the_text_and_html(self) -> None:
        mail_ = self.rendered()
        text = mail_.get_body(("plain",))
        html = mail_.get_body(("html",))

        assert text is not None
        assert html is not None
        plain = text.get_content()
        assert "**" not in plain
        assert "Open the incident (https://ares.example/incidents/4) now." in plain
        assert "Where: web1 (192.168.1.20)" in plain
        assert plain.index("https://ares.example/incidents/4\n") > plain.index("Where:")
        assert "-- \nAresGate · incident 4" in plain
        markup = html.get_content()
        assert "<h2>Brute force on ssh</h2>" in markup
        assert "<b>Where</b>: web1 (192.168.1.20)" in markup
        assert '<a href="https://ares.example/incidents/4">' in markup
        assert "<small>AresGate · incident 4</small>" in markup

    def test_what_a_message_says_is_escaped_in_the_html(self) -> None:
        body = payload(
            title="<script>x</script>", description="a < b & c", fields=[("<i>", "<b>", False)]
        )

        markup = self.rendered(body).get_body(("html",))

        assert markup is not None
        html = markup.get_content()
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "a &lt; b &amp; c" in html
        assert "&lt;i&gt;" in html

    def test_a_title_cannot_start_another_header(self) -> None:
        mail_ = self.rendered(payload(title="Hello\r\nBcc: attacker@example.net"))

        assert "Bcc" not in mail_
        assert mail_["Subject"] == "[AresGate] Hello  Bcc: attacker@example.net"

    def test_a_long_title_is_cut_short_in_the_subject(self) -> None:
        mail_ = self.rendered(payload(title="x" * 300))

        assert len(str(mail_["Subject"])) == mail.MAX_SUBJECT

    def test_a_message_with_only_a_title_is_still_an_email(self) -> None:
        body = discord_message(title="Only a title", description="")

        mail_ = self.rendered(body)

        text = mail_.get_body(("plain",))
        assert text is not None
        assert text.get_content() == "Only a title\n"
        assert mail_["Subject"] == "[AresGate] Only a title"

    def test_a_link_that_is_not_a_web_address_is_left_out(self) -> None:
        body = payload(link=None)
        body_embeds: Any = body["embeds"]
        body_embeds[0]["url"] = "javascript:alert(1)"

        mail_ = self.rendered(body)

        assert "javascript" not in mail_.as_string()

    def test_a_payload_with_no_embed_still_gives_a_message(self) -> None:
        assert self.rendered({"username": "x"})["Subject"] == "[AresGate] AresGate"
        assert self.rendered({"embeds": "nonsense"})["Subject"] == "[AresGate] AresGate"
        assert self.rendered({"embeds": [7]})["Subject"] == "[AresGate] AresGate"

    def test_the_test_message_says_where_it_came_from_and_that_nothing_is_wrong(self) -> None:
        mail_ = self.rendered(mail.check_message("Home", NOW))

        text = mail_.get_body(("plain",))
        assert text is not None
        assert mail_["Subject"] == "[AresGate] AresGate can email you"
        assert "“Home”" in text.get_content()
        assert "Nothing is wrong." in text.get_content()


class Fake:
    """A stand-in for smtplib's connection, that remembers what was done and can fail."""

    made: ClassVar[list[Fake]] = []
    fail_on: ClassVar[str | None] = None
    error: ClassVar[Exception] = smtplib.SMTPException("x")

    def __init__(self, host: str, port: int, **options: Any) -> None:
        self.host, self.port, self.options = host, port, options
        self.calls: list[tuple[str, Any]] = []
        Fake.made.append(self)

    def __enter__(self) -> Fake:
        return self

    def __exit__(self, *_: object) -> None:
        self.calls.append(("quit", None))

    def _do(self, name: str, detail: Any = None) -> None:
        self.calls.append((name, detail))
        if Fake.fail_on == name:
            raise Fake.error

    def ehlo(self) -> None:
        self._do("ehlo")

    def starttls(self, context: ssl.SSLContext) -> None:
        self._do("starttls", context)

    def login(self, user: str, password: str) -> None:
        self._do("login", (user, password))

    def send_message(self, message: EmailMessage) -> None:
        self._do("send", message)


def leads_to(monkeypatch: pytest.MonkeyPatch, address: str) -> None:
    """Makes every name lead to one address."""

    def lookup(host: str, port: int) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        del host, port
        return [ipaddress.ip_address(address)]

    monkeypatch.setattr(netguard, "lookup", lookup)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> type[Fake]:
    """Connections that go nowhere, and a mail server's name that leads to a public address."""
    Fake.made, Fake.fail_on, Fake.error = [], None, smtplib.SMTPException("x")
    monkeypatch.setattr(smtplib, "SMTP", Fake)
    monkeypatch.setattr(smtplib, "SMTP_SSL", Fake)
    leads_to(monkeypatch, "93.184.216.34")
    return Fake


def send(box: mail.Mailbox = BOX) -> Sent:
    return asyncio.run(mail.send(box, payload()))


class TestSending:
    def test_a_message_goes_through_starttls_with_the_sign_in(self, fake: type[Fake]) -> None:
        sent = send()

        assert sent == Sent(ok=True, status=250)
        [connection] = fake.made
        assert (connection.host, connection.port) == ("smtp.example.com", 587)
        assert connection.options["timeout"] == mail.TIMEOUT
        assert [name for name, _ in connection.calls] == [
            "ehlo",
            "starttls",
            "ehlo",
            "login",
            "send",
            "quit",
        ]
        assert ("login", ("alerts", "correct horse")) in connection.calls
        starttls = dict(connection.calls)["starttls"]
        assert starttls.verify_mode == ssl.CERT_REQUIRED
        assert starttls.check_hostname

    def test_ssl_is_encrypted_from_the_start_and_never_asks_to_upgrade(
        self, fake: type[Fake]
    ) -> None:
        box = mail.Mailbox(
            dataclasses.replace(SERVER, security="ssl", port=465),
            "me@example.org",
        )

        assert send(box).ok

        [connection] = fake.made
        assert connection.options["context"].verify_mode == ssl.CERT_REQUIRED
        assert "starttls" not in [name for name, _ in connection.calls]

    def test_a_server_that_needs_no_sign_in_is_sent_to_without_one(self, fake: type[Fake]) -> None:
        open_server = mail.Server("relay.example.com", 25, "none", None, None, "a@example.com")

        assert send(mail.Mailbox(open_server, "me@example.org")).ok

        [connection] = fake.made
        assert [name for name, _ in connection.calls] == ["ehlo", "send", "quit"]

    def test_a_password_with_no_user_name_is_not_sent(self, fake: type[Fake]) -> None:
        server = mail.Server("relay.example.com", 587, "starttls", None, "secret", "a@example.com")

        send(mail.Mailbox(server, "me@example.org"))

        assert "login" not in [name for name, _ in fake.made[0].calls]

    @pytest.mark.parametrize(
        ("error", "retry", "gone", "words"),
        [
            (smtplib.SMTPAuthenticationError(535, b"no"), False, True, "user name and password"),
            (smtplib.SMTPRecipientsRefused({"x": (550, b"no")}), False, True, "recipient"),
            (smtplib.SMTPSenderRefused(553, b"no", "a@b.c"), False, True, "sender"),
            (smtplib.SMTPResponseException(451, b"later"), True, False, "answered 451"),
            (smtplib.SMTPResponseException(554, b"never"), False, False, "answered 554"),
            (smtplib.SMTPNotSupportedError("no tls"), False, True, "doesn't offer STARTTLS"),
            (ssl.SSLCertVerificationError("bad"), False, False, "encrypted connection"),
            (smtplib.SMTPServerDisconnected("gone"), True, False, "Couldn't reach"),
            (TimeoutError("slow"), True, False, "Couldn't reach"),
            (ConnectionRefusedError("no"), True, False, "Couldn't reach"),
        ],
    )
    def test_what_goes_wrong_is_said_in_words_and_whether_to_try_again(
        self, fake: type[Fake], error: Exception, retry: bool, gone: bool, words: str
    ) -> None:
        fake.fail_on, fake.error = "send", error

        sent = send()

        assert not sent.ok
        assert (sent.retry, sent.gone) == (retry, gone)
        assert sent.problem is not None
        assert words in sent.problem
        assert "correct horse" not in sent.problem

    def test_a_refused_sign_in_is_not_tried_again_and_names_the_settings(
        self, fake: type[Fake]
    ) -> None:
        fake.fail_on, fake.error = "login", smtplib.SMTPAuthenticationError(535, b"bad")

        sent = send()

        assert sent.gone
        assert sent.status == 535
        assert "send" not in [name for name, _ in fake.made[0].calls]

    def test_a_name_that_leads_nowhere_may_work_later(
        self, fake: type[Fake], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def lost(host: str, port: int) -> list[Any]:
            raise netguard.NotFound(f"Couldn't find {host}.")

        monkeypatch.setattr(netguard, "lookup", lost)

        sent = send()

        assert (sent.ok, sent.retry, sent.gone) == (False, True, False)
        assert sent.problem == "Couldn't find smtp.example.com."
        assert fake.made == []

    @pytest.mark.parametrize(
        "address", ["127.0.0.1", "::1", "169.254.169.254", "169.254.1.1", "0.1.2.3", "224.0.0.1"]
    )
    def test_a_server_on_this_machine_or_a_metadata_service_is_never_connected_to(
        self, fake: type[Fake], monkeypatch: pytest.MonkeyPatch, address: str
    ) -> None:
        leads_to(monkeypatch, address)

        sent = send()

        assert (sent.ok, sent.retry, sent.gone) == (False, False, True)
        assert "won't connect to it" in (sent.problem or "")
        assert fake.made == []

    @pytest.mark.parametrize("address", ["10.0.0.5", "192.168.1.9", "93.184.216.34"])
    def test_a_server_on_the_home_network_or_the_internet_is_fine(
        self, fake: type[Fake], monkeypatch: pytest.MonkeyPatch, address: str
    ) -> None:
        leads_to(monkeypatch, address)

        assert send().ok

    def test_a_message_that_cannot_be_written_is_a_failure_not_a_crash(
        self, fake: type[Fake]
    ) -> None:
        bad = mail.Server(
            "smtp.example.com", 587, "starttls", None, None, "bad\nsender@example.com"
        )

        sent = send(mail.Mailbox(bad, "me@example.org"))

        assert (sent.ok, sent.retry) == (False, False)
        assert sent.problem == "The message couldn't be written as an email."
        assert fake.made == []


class StubHandler(socketserver.StreamRequestHandler):
    """The few lines of SMTP a message needs, kept for the test to read."""

    def handle(self) -> None:
        received: list[bytes] = []
        self.wfile.write(b"220 stub ESMTP\r\n")
        data = False
        for line in self.rfile:
            if data:
                if line == b".\r\n":
                    data = False
                    self.wfile.write(b"250 queued\r\n")
                else:
                    received.append(line)
                continue
            word = line.strip().upper()
            if word.startswith(b"EHLO"):
                self.wfile.write(b"250 stub\r\n")
            elif word == b"DATA":
                data = True
                self.wfile.write(b"354 go on\r\n")
            elif word == b"QUIT":
                self.wfile.write(b"221 bye\r\n")
                break
            else:
                self.wfile.write(b"250 ok\r\n")
        self.server.mail = b"".join(received)  # type: ignore[attr-defined]


def test_a_message_reaches_a_real_mail_server_and_arrives_as_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), StubHandler)
    server.mail = b""  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # The product never connects to this machine; the test server is on it.
    monkeypatch.setattr(mail, "SERVER_POLICY", netguard.HOME_NETWORK_AND_LOOPBACK)
    plain = mail.Server("127.0.0.1", server.server_address[1], "none", None, None, "a@example.com")
    try:
        sent = asyncio.run(mail.send(mail.Mailbox(plain, "me@example.org"), payload()))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)

    assert sent == Sent(ok=True, status=250)
    arrived = message_from_bytes(server.mail)  # type: ignore[attr-defined]
    assert arrived["Subject"] == "[AresGate] Brute force on ssh"
    assert arrived["To"] == "me@example.org"
    body = arrived.get_payload(0).get_payload(decode=True).decode()  # type: ignore[union-attr]
    assert "Where: web1 (192.168.1.20)" in body


def test_nobody_listening_is_a_failure_to_try_again(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail, "SERVER_POLICY", netguard.HOME_NETWORK_AND_LOOPBACK)
    closed = mail.Server("127.0.0.1", 1, "none", None, None, "a@example.com")

    sent = asyncio.run(mail.send(mail.Mailbox(closed, "me@example.org"), payload()))

    assert (sent.ok, sent.retry) == (False, True)
    assert sent.problem == "Couldn't reach the mail server. Check its name and port."
