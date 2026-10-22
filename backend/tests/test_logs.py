import io
import json
import logging
import time
from datetime import UTC, datetime

import pytest

from app import logs
from app.config import Settings
from app.logs import REDACTED, JsonFormatter, Redactor, TextFormatter

ARGON2 = "$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$RdescudvJCsgt3ub+b+dWRWJTmaaJObG"
KEY = "kQ9v3-an-app-secret-key-0123456789abcdef"


@pytest.fixture
def redactor() -> Redactor:
    return Redactor([KEY])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("password=hunter2 next", f"password={REDACTED} next"),
        ("password: hunter2", f"password: {REDACTED}"),
        (
            '{"password": "correct horse", "user": "brian"}',
            f'{{"password": {REDACTED}, "user": "brian"}}',
        ),
        (
            "{'password_hash': 'x y z', 'username': 'brian'}",
            f"{{'password_hash': {REDACTED}, 'username': 'brian'}}",
        ),
        ("csrf_token=abc123&next=/", f"csrf_token={REDACTED}&next=/"),
        ("X-CSRF-Token: abc123", f"X-CSRF-Token: {REDACTED}"),
        ("api_key = sk-123", f"api_key = {REDACTED}"),
        ("client_secret=shh", f"client_secret={REDACTED}"),
        ("totp: 123456", f"totp: {REDACTED}"),
        ("recovery_code=ABCD", f"recovery_code={REDACTED}"),
        ("Authorization: Bearer abc.def.ghi", f"Authorization: {REDACTED}"),
        ("authorization:Basic dXNlcjpwYXNz", f"authorization:{REDACTED}"),
        ("Cookie: __Host-aresgate_session=abc; theme=dark", f"Cookie: {REDACTED}"),
        ("Set-Cookie: a=b; HttpOnly", f"Set-Cookie: {REDACTED}"),
        ("sent Bearer abc.def-ghi_jkl to the server", f"sent {REDACTED} to the server"),
        (f"stored {ARGON2} for them", f"stored {REDACTED} for them"),
        ("the code was K7QD-3MWX-9HPA, once", f"the code was {REDACTED}, once"),
        ("jwt eyJhbGciOi.eyJzdWIiOiIx.c2ln here", f"jwt {REDACTED} here"),
        (
            "key\n-----BEGIN PRIVATE KEY-----\nMIIE\nabc\n-----END PRIVATE KEY-----\nend",
            f"key\n{REDACTED}\nend",
        ),
        ("-----BEGIN EC PRIVATE KEY-----\nMIIE cut off", REDACTED),
        (
            "connecting to postgresql://aresgate:s3cr3t@db/aresgate",
            f"connecting to postgresql://{REDACTED}@db/aresgate",
        ),
        (f"the key is {KEY}.", f"the key is {REDACTED}."),
    ],
)
def test_secrets_are_blanked_out_of_text(redactor: Redactor, text: str, expected: str) -> None:
    assert redactor.text(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "max_tokens=100",
        "tokens_used: 5",
        "status_code=401 method=GET",
        "footprint=small",
        "user=brian action=auth.login_failed",
        "ABCD-EFGH is not a setup code",
        "GET /api/health 200",
        "a=1, b=2; c: 3",
        "Cookies are good",
        "",
    ],
)
def test_ordinary_text_is_left_alone(redactor: Redactor, text: str) -> None:
    assert redactor.text(text) == text


def test_a_secret_that_contains_another_is_blanked_out_whole() -> None:
    redactor = Redactor(["abcdefgh", "abcdefgh-and-more"])

    assert redactor.text("x abcdefgh-and-more y") == f"x {REDACTED} y"


def test_a_value_too_short_to_be_a_secret_is_not_hunted_for() -> None:
    assert (
        Redactor(["short", ""]).text("a short, short, short text") == "a short, short, short text"
    )


def test_redaction_takes_linear_time() -> None:
    redactor = Redactor([KEY])
    texts = [
        "a" * 200_000,
        "a=a " * 50_000,
        "password=" + "'" * 50_000,
        '"' * 100_000,
        "-----BEGIN PRIVATE KEY-----" * 5_000,
        "-" * 100_000,
    ]

    started = time.perf_counter()
    for text in texts:
        redactor.text(text)

    assert time.perf_counter() - started < 5


def test_structured_data_is_redacted_by_name_and_by_content(redactor: Redactor) -> None:
    data = {
        "user": "brian",
        "password": "hunter2",
        "attempts": 3,
        "token": 123456,
        "nested": {"api_key": ["a", "b"], "note": f"used {KEY}"},
        "items": ({"cookie": "x"}, "Bearer abc.def", 7),
        1: "one",
    }

    assert redactor.data(data) == {
        "user": "brian",
        "password": REDACTED,
        "attempts": 3,
        "token": REDACTED,
        "nested": {"api_key": REDACTED, "note": f"used {REDACTED}"},
        "items": [{"cookie": REDACTED}, REDACTED, 7],
        "1": "one",
    }


def test_values_that_are_neither_text_nor_a_collection_pass_through(redactor: Redactor) -> None:
    when = datetime(2026, 10, 22, tzinfo=UTC)

    assert redactor.data(when) is when
    assert redactor.data(None) is None
    assert redactor.data(True) is True


@pytest.fixture
def stream() -> io.StringIO:
    return io.StringIO()


def emit(formatter: logging.Formatter, text: str, *args: object, **fields: object) -> str:
    """A log line as the formatter writes it."""
    record = logging.getLogger("aresgate.test").makeRecord(
        "aresgate.test", logging.INFO, __file__, 1, text, args, None, extra=fields or None
    )
    record.created = datetime(2026, 10, 22, 12, 30, 5, 123_000, tzinfo=UTC).timestamp()
    return formatter.format(record)


class TestJson:
    def test_one_line_of_json_for_each_record(self, redactor: Redactor) -> None:
        line = emit(JsonFormatter(redactor), "signed in %s", "brian", attempts=2)

        assert "\n" not in line
        assert json.loads(line) == {
            "time": "2026-10-22T12:30:05.123Z",
            "level": "info",
            "logger": "aresgate.test",
            "message": "signed in brian",
            "attempts": 2,
        }

    def test_the_request_is_named_when_there_is_one(self, redactor: Redactor) -> None:
        token = logs.request_id.set("abc123def456")
        try:
            entry = json.loads(emit(JsonFormatter(redactor), "hello"))
        finally:
            logs.request_id.reset(token)

        assert entry["request_id"] == "abc123def456"

    def test_secrets_are_blanked_out_of_the_message_and_the_fields(
        self, redactor: Redactor
    ) -> None:
        line = emit(
            JsonFormatter(redactor),
            "login password=%s",
            "hunter2",
            password="hunter2",
            note=f"key {KEY}",
        )

        entry = json.loads(line)
        assert entry["message"] == f"login password={REDACTED}"
        assert entry["password"] == REDACTED
        assert entry["note"] == f"key {REDACTED}"
        assert "hunter2" not in line
        assert KEY not in line

    def test_a_newline_in_the_text_does_not_start_another_line(self, redactor: Redactor) -> None:
        line = emit(JsonFormatter(redactor), 'evil\n{"level": "critical"}', path="/a\r\nb")

        assert "\n" not in line
        assert json.loads(line)["message"] == 'evil\n{"level": "critical"}'

    def test_what_the_caller_adds_cannot_replace_what_the_line_says_for_itself(
        self, redactor: Redactor
    ) -> None:
        entry = json.loads(emit(JsonFormatter(redactor), "real", time="fake", level="fake"))

        assert (entry["message"], entry["level"]) == ("real", "info")
        assert entry["time"].endswith("Z")
        assert (entry["extra_time"], entry["extra_level"]) == ("fake", "fake")

    def test_an_error_has_its_traceback_with_secrets_blanked_out(self, redactor: Redactor) -> None:
        try:
            raise ValueError(f"bad value, password=hunter2 and {KEY}")
        except ValueError as error:
            record = logging.LogRecord(
                "aresgate.test",
                logging.ERROR,
                __file__,
                1,
                "failed",
                None,
                (type(error), error, error.__traceback__),
            )

        entry = json.loads(JsonFormatter(redactor).format(record))

        assert "ValueError" in entry["exception"]
        assert "Traceback" in entry["exception"]
        assert "hunter2" not in entry["exception"]
        assert KEY not in entry["exception"]

    def test_what_cannot_be_encoded_is_written_as_text(self, redactor: Redactor) -> None:
        entry = json.loads(emit(JsonFormatter(redactor), "x", thing=object))

        assert entry["thing"] == "<class 'object'>"


class TestText:
    def test_a_readable_line(self, redactor: Redactor) -> None:
        line = emit(TextFormatter(redactor), "signed in %s", "brian")

        assert line == "2026-10-22 12:30:05 info    aresgate.test signed in brian"

    def test_the_request_is_named_when_there_is_one(self, redactor: Redactor) -> None:
        token = logs.request_id.set("abc123def456")
        try:
            line = emit(TextFormatter(redactor), "hello")
        finally:
            logs.request_id.reset(token)

        assert line.endswith("hello request_id=abc123def456")

    def test_secrets_are_blanked_out_and_a_newline_does_not_start_another_line(
        self, redactor: Redactor
    ) -> None:
        line = emit(TextFormatter(redactor), "password=hunter2\nfake line\r%s", KEY)

        assert "\n" not in line
        assert line.endswith(f"password={REDACTED}\\nfake line\\r{REDACTED}")

    def test_an_error_follows_its_line_with_secrets_blanked_out(self, redactor: Redactor) -> None:
        try:
            raise ValueError("token=abc123")
        except ValueError as error:
            record = logging.LogRecord(
                "aresgate.test",
                logging.ERROR,
                __file__,
                1,
                "failed",
                None,
                (type(error), error, error.__traceback__),
            )

        line = TextFormatter(redactor).format(record)

        first, _, rest = line.partition("\n")
        assert first.endswith("failed")
        assert "Traceback" in rest
        assert f"token={REDACTED}" in rest


@pytest.mark.usefixtures("untouched_logging")
class TestConfigure:
    def test_logs_go_to_the_stream_as_json_with_secrets_blanked_out(
        self, stream: io.StringIO
    ) -> None:
        logs.configure(Settings(log_format="json"), secrets=[KEY], stream=stream)

        logging.getLogger("aresgate.test").info("hello %s", KEY)

        entry = json.loads(stream.getvalue())
        assert entry["message"] == f"hello {REDACTED}"

    def test_or_as_text(self, stream: io.StringIO) -> None:
        logs.configure(Settings(log_format="text"), stream=stream)

        logging.getLogger("aresgate.test").info("hello")

        assert stream.getvalue().endswith(" info    aresgate.test hello\n")

    def test_the_level_is_the_settings(self, stream: io.StringIO) -> None:
        logs.configure(Settings(log_level="warning"), stream=stream)

        logging.getLogger("aresgate.test").info("hidden")
        logging.getLogger("aresgate.test").warning("shown")

        assert [json.loads(line)["message"] for line in stream.getvalue().splitlines()] == ["shown"]

    def test_configuring_again_replaces_its_own_handler_and_nobody_elses(
        self, stream: io.StringIO
    ) -> None:
        mine = logging.NullHandler()
        logging.getLogger().addHandler(mine)
        logs.configure(Settings(), stream=io.StringIO())
        logs.configure(Settings(), stream=stream)

        ours = [h for h in logging.getLogger().handlers if getattr(h, "_aresgate_handler", False)]
        assert len(ours) == 1
        assert mine in logging.getLogger().handlers
        logging.getLogger("aresgate.test").info("once")
        assert len(stream.getvalue().splitlines()) == 1

    def test_uvicorns_own_logs_are_written_the_same_way(self, stream: io.StringIO) -> None:
        uvicorn = logging.getLogger("uvicorn.error")
        uvicorn.addHandler(logging.StreamHandler(io.StringIO()))

        logs.configure(Settings(), stream=stream)
        uvicorn.info("Application startup complete.", extra={"color_message": "\x1b[1mAnd more"})

        assert uvicorn.handlers == []
        entry = json.loads(stream.getvalue())
        assert entry["logger"] == "uvicorn.error"
        assert "color_message" not in entry

    def test_uvicorns_access_log_is_silent_since_each_request_is_logged_by_the_api(
        self, stream: io.StringIO
    ) -> None:
        logs.configure(Settings(), stream=stream)

        logging.getLogger("uvicorn.access").info(
            '127.0.0.1 - "GET /api/health?secret=1 HTTP/1.1" 200'
        )

        assert stream.getvalue() == ""
