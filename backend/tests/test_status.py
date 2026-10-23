import os
import ssl
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import TextClause, text
from sqlalchemy.orm import Session

from app import status
from app.integrations import netguard
from app.integrations.netguard import CertificateInfo as Found
from tests.stubs import Answer, Seen, Serve, make_certificate

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)


def ok(_: Seen) -> Answer:
    return Answer(status=200, body="")


# ---- The database ------------------------------------------------------------------------


def test_the_newest_migration_is_found_in_the_directory(tmp_path: Path) -> None:
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "first.py").write_text('revision = "0001"\ndown_revision = None\n')
    (versions / "second.py").write_text('revision = "0002"\ndown_revision = "0001"\n')

    assert status.migration_head(tmp_path) == "0002"


def test_this_build_has_a_newest_migration() -> None:
    newest = max(path.name for path in (status.MIGRATIONS / "versions").glob("2*.py"))

    assert status.migration_head() == newest.split("_")[1]


def test_the_database_says_what_it_is_and_how_busy(session: Session) -> None:
    found = status.database_info(session, "0008")

    assert found.status == "ok"
    assert found.version is not None
    assert found.version.split(".")[0].isdigit()
    assert (found.size_bytes or 0) > 0
    assert 1 <= (found.connections or 0) <= (found.max_connections or 0)
    assert found.migration_head == "0008"


def test_a_database_that_migrations_did_not_make_has_no_migration(session: Session) -> None:
    assert status.database_info(session, "0008").migration is None
    # The failed question did not spoil the session for the next one.
    assert session.scalar(text("SELECT 1")) == 1


def test_the_database_says_which_migration_it_is_at(session: Session) -> None:
    session.execute(text("CREATE TABLE alembic_version (version_num varchar(32) NOT NULL)"))
    session.execute(text("INSERT INTO alembic_version VALUES ('0007')"))

    try:
        assert status.database_info(session, "0008").migration == "0007"
    finally:
        session.rollback()


def test_a_database_that_cannot_be_asked_is_unavailable(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:

    def not_a_query(_: str) -> TextClause:
        return text("SELECT * FROM a_table_that_is_not_there")

    monkeypatch.setattr(status, "text", not_a_query)

    found = status.database_info(session, "0008")

    assert found.status == "unavailable"
    assert (found.version, found.size_bytes, found.connections, found.migration) == (
        None,
        None,
        None,
        None,
    )
    assert found.migration_head == "0008"


# ---- The programs ------------------------------------------------------------------------

PACKAGES = """P:busybox
V:1.37.0-r5

P:nginx-mainline
V:1.29.1-r2
A:x86_64

P:nginx-mainline-config
V:1.29.1-r2
"""


def test_a_package_version_is_read_from_the_list_of_what_is_installed(tmp_path: Path) -> None:
    listing = tmp_path / "installed"
    listing.write_text(PACKAGES)

    assert status.packaged_version("nginx-mainline", listing) == "1.29.1"
    assert status.packaged_version("busybox", listing) == "1.37.0"


def test_a_package_that_is_not_installed_has_no_version(tmp_path: Path) -> None:
    listing = tmp_path / "installed"
    listing.write_text(PACKAGES)

    assert status.packaged_version("postgresql", listing) is None
    assert status.packaged_version("nginx-mainline", tmp_path / "missing") is None


def served(**changes: Any) -> Found:
    base: dict[str, Any] = {
        "fingerprint": "AA:BB",
        "subject": "CN=aresgate.example",
        "issuer": "CN=R11,O=Let's Encrypt",
        "not_before": NOW - timedelta(days=60),
        "not_after": NOW + timedelta(days=30, hours=3),
        "names": ["aresgate.example", "localhost"],
    }
    return Found(**{**base, **changes})


def test_the_certificate_nginx_presents_says_who_made_it_and_when_it_ends() -> None:
    seen: list[tuple[str, int, str]] = []

    def look_up(host: str, port: int, name: str) -> Found:
        seen.append((host, port, name))
        return served()

    found = status.certificate_info("aresgate.example", port=9443, now=NOW, look_up=look_up)

    assert seen == [("127.0.0.1", 9443, "aresgate.example")]
    assert found is not None
    assert found.issuer == "CN=R11,O=Let's Encrypt"
    assert found.names == ["aresgate.example", "localhost"]
    assert found.days_left == 30
    assert found.self_signed is False


def test_a_certificate_that_signed_itself_says_so() -> None:
    found = status.certificate_info(
        "localhost", now=NOW, look_up=lambda *_: served(issuer="CN=aresgate.example")
    )

    assert found is not None
    assert found.self_signed is True


def test_a_certificate_that_has_ended_has_no_days_left() -> None:
    found = status.certificate_info(
        "localhost", now=NOW, look_up=lambda *_: served(not_after=NOW - timedelta(days=3))
    )

    assert found is not None
    assert found.days_left == -3


def test_nothing_serving_a_certificate_is_not_an_error() -> None:
    assert status.certificate_info("localhost", now=NOW, look_up=lambda *_: None) is None


def test_the_served_certificate_is_the_one_a_server_presents(serve: Serve) -> None:
    certificate = make_certificate("aresgate.example")
    server = serve(ok, certificate)

    found = netguard.look_up_served_certificate("127.0.0.1", server.port, "aresgate.example")

    assert found is not None
    assert found.fingerprint == certificate.fingerprint
    assert found.names == ["aresgate.example", "127.0.0.1"]
    assert server.seen == []


def test_nothing_answering_means_no_certificate(serve: Serve) -> None:
    server = serve(ok, make_certificate())
    server.stop()

    assert netguard.look_up_served_certificate("127.0.0.1", server.port, "localhost") is None


def test_a_server_that_is_not_speaking_tls_means_no_certificate(serve: Serve) -> None:
    server = serve(ok)

    assert netguard.look_up_served_certificate("127.0.0.1", server.port, "localhost") is None


def test_a_connection_that_shows_no_certificate_means_no_certificate(
    serve: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = serve(ok, make_certificate())

    def shows_nothing(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(ssl.SSLSocket, "getpeercert", shows_nothing)

    assert netguard.look_up_served_certificate("127.0.0.1", server.port, "localhost") is None


# ---- The container -----------------------------------------------------------------------


def write(root: Path, name: str, content: str) -> None:
    (root / name).write_text(content)


def test_a_container_with_a_memory_limit_reports_against_it(tmp_path: Path) -> None:
    write(tmp_path, "memory.current", "104857600\n")
    write(tmp_path, "memory.max", "536870912\n")
    write(tmp_path, "meminfo", "MemTotal: 8388608 kB\nMemAvailable: 4194304 kB\nBuffers: 5 kB\n")

    found = status.memory_info(tmp_path, tmp_path)

    assert found == status.Memory(
        used_bytes=104857600, limit_bytes=536870912, total_bytes=8589934592
    )


def test_a_container_with_no_limit_reports_the_computers_memory(tmp_path: Path) -> None:
    write(tmp_path, "memory.current", "104857600\n")
    write(tmp_path, "memory.max", "max\n")
    write(tmp_path, "meminfo", "MemTotal: 8388608 kB\nMemAvailable: 4194304 kB\n")

    found = status.memory_info(tmp_path, tmp_path)

    assert found is not None
    assert found.limit_bytes is None
    assert found.total_bytes == 8589934592


def test_without_cgroups_memory_comes_from_the_computer(tmp_path: Path) -> None:
    write(tmp_path, "meminfo", "MemTotal: 8388608 kB\nMemAvailable: 4194304 kB\n")

    found = status.memory_info(tmp_path / "none", tmp_path)

    assert found == status.Memory(used_bytes=4294967296, limit_bytes=None, total_bytes=8589934592)


def test_cgroup_memory_is_reported_even_if_meminfo_cannot_be_read(tmp_path: Path) -> None:
    write(tmp_path, "memory.current", "1024")
    write(tmp_path, "memory.max", "2048")

    found = status.memory_info(tmp_path, tmp_path / "none")

    assert found == status.Memory(used_bytes=1024, limit_bytes=2048, total_bytes=None)


@pytest.mark.parametrize(
    "meminfo", ["", "MemTotal: 8388608 kB\n", "MemTotal: lots\nMemAvailable: 1 kB\n"]
)
def test_memory_nobody_can_tell_is_left_out(tmp_path: Path, meminfo: str) -> None:
    write(tmp_path, "meminfo", meminfo)

    assert status.memory_info(tmp_path / "none", tmp_path) is None


def test_no_memory_information_at_all_is_left_out(tmp_path: Path) -> None:
    assert status.memory_info(tmp_path / "none", tmp_path / "none") is None


def test_a_cpu_limit_is_the_quota_over_the_period(tmp_path: Path) -> None:
    write(tmp_path, "cpu.max", "150000 100000\n")

    assert status.cpu_count(tmp_path) == 1.5


@pytest.mark.parametrize("content", ["max 100000\n", "not numbers\n", "1 2 3\n"])
def test_without_a_cpu_limit_it_is_all_the_computer_has(tmp_path: Path, content: str) -> None:
    write(tmp_path, "cpu.max", content)

    assert status.cpu_count(tmp_path) == float(len(os.sched_getaffinity(0)))
    assert status.cpu_count(tmp_path / "none") == float(len(os.sched_getaffinity(0)))


def test_the_disk_is_measured_where_the_data_is(tmp_path: Path) -> None:
    found = status.disk_info(tmp_path)

    assert found is not None
    assert 0 < found.used_bytes <= found.total_bytes


def test_a_disk_that_cannot_be_measured_is_left_out(tmp_path: Path) -> None:
    assert status.disk_info(tmp_path / "none") is None


def test_the_load_is_three_averages() -> None:
    found = status.load_average()

    assert found is not None
    assert len(found) == 3


def test_a_computer_with_no_load_average_has_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse() -> tuple[float, float, float]:
        raise OSError

    monkeypatch.setattr(os, "getloadavg", refuse)

    assert status.load_average() is None


def test_the_container_is_measured_at_the_data_volume_if_there_is_one(tmp_path: Path) -> None:
    found = status.container_info(NOW, tmp_path)

    assert found.server_time == NOW
    assert found.disk is not None
    assert found.cpus is not None


def test_the_container_is_measured_at_the_root_when_there_is_no_data_volume(
    tmp_path: Path,
) -> None:
    found = status.container_info(NOW, tmp_path / "none")

    assert found.disk is not None


def test_the_container_uses_the_data_volume_path_by_default() -> None:
    assert status.container_info(NOW).disk is not None


# ---- Redaction and the text for a bug report ---------------------------------------------


@pytest.mark.parametrize(
    ("text_in", "text_out"),
    [
        ("could not reach https://192.168.1.2:5000/api", "could not reach [address]"),
        ("connect to 192.168.1.2:3000 failed", "connect to [address] failed"),
        ("connect to 192.168.1.2 failed", "connect to [address] failed"),
        ("host opnsense.home.arpa refused", "host [address] refused"),
        ("host fw.example.com:8443 refused", "host [address] refused"),
        ("address fe80:0:0:0:1:2:3:4 refused", "address [address] refused"),
        ("CN=R11,O=Let's Encrypt", "CN=R11,O=Let's Encrypt"),
        ("nginx 1.29.1 and PostgreSQL 18.1", "nginx 1.29.1 and PostgreSQL 18.1"),
        ("took 3 seconds at 12:00", "took 3 seconds at 12:00"),
    ],
)
def test_addresses_are_taken_out_of_text(text_in: str, text_out: str) -> None:
    assert status.redact(text_in) == text_out


@pytest.mark.parametrize(
    ("value", "words"),
    [
        (None, "unknown"),
        (0, "0 B"),
        (1023, "1023 B"),
        (1536, "1.5 KB"),
        (5 * 1024**2, "5.0 MB"),
        (3 * 1024**3, "3.0 GB"),
        (2 * 1024**4, "2.0 TB"),
    ],
)
def test_sizes_are_in_words(value: int | None, words: str) -> None:
    assert status.human_size(value) == words


@pytest.mark.parametrize(
    ("seconds", "words"),
    [(0, "0m"), (59, "0m"), (3600, "1h 0m"), (3 * 3600 + 12 * 60, "3h 12m"), (90061, "1d 1h 1m")],
)
def test_durations_are_in_words(seconds: int, words: str) -> None:
    assert status.human_duration(seconds) == words


# ---- The text for a bug report -----------------------------------------------------------


def a_report(**changes: Any) -> status.StatusReport:
    base: dict[str, Any] = {
        "aresgate": status.BuildInfo(
            version="1.2.3",
            commit="0123456789abcdef0123",
            built_at=datetime(2026, 10, 22, 8, 30, tzinfo=UTC),
            environment="production",
            started_at=NOW - timedelta(hours=3, minutes=12),
            uptime_seconds=3 * 3600 + 12 * 60,
        ),
        "stack": status.StackInfo(
            python="3.14.8",
            nginx="1.29.1",
            database=status.DatabaseInfo(
                status="ok",
                version="18.1",
                size_bytes=23 * 1024**2,
                connections=5,
                max_connections=100,
                migration="0008",
                migration_head="0008",
            ),
            certificate=status.CertificateInfo(
                subject="CN=aresgate.example",
                issuer="CN=R11,O=Let's Encrypt",
                names=["aresgate.example", "localhost"],
                not_before=NOW - timedelta(days=60),
                not_after=NOW + timedelta(days=30),
                days_left=30,
                self_signed=False,
            ),
        ),
        "container": status.ContainerInfo(
            cpus=2,
            load=[0.1, 0.25, 0.3],
            memory=status.Memory(
                used_bytes=312 * 1024**2, limit_bytes=2 * 1024**3, total_bytes=None
            ),
            disk=status.Disk(used_bytes=1024**3, total_bytes=20 * 1024**3),
            server_time=NOW,
        ),
        "parts": [
            status.Part(
                key="ntopng",
                name="ntopng",
                group="integration",
                state="ok",
                detail=None,
                last_success_at=NOW,
            ),
            status.Part(
                key="wazuh",
                name="Wazuh",
                group="integration",
                state="problem",
                detail="Couldn't reach https://192.168.1.2:55000.",
                last_success_at=None,
            ),
        ],
        "diagnostics": "",
    }
    return status.StatusReport(**{**base, **changes})


def test_the_text_for_a_bug_report_has_the_facts_and_no_addresses() -> None:
    text = status.diagnostics(a_report())

    assert text.splitlines() == [
        "AresGate diagnostics",
        "Version: 1.2.3 (commit 0123456789ab, built 2026-10-22 08:30 UTC)",
        "Environment: production",
        "Up for: 3h 12m",
        "Python 3.14.8, nginx 1.29.1",
        "Database: PostgreSQL 18.1, 23.0 MB, 5 of 100 connections, migration 0008 "
        "(this build expects 0008)",
        "Certificate: issued by CN=R11,O=Let's Encrypt, 2 names, 30 days left",
        "Memory: 312.0 MB of 2.0 GB",
        "Disk: 1.0 GB of 20.0 GB",
        "CPUs: 2, load 0.1 0.25 0.3",
        "Parts:",
        "- ntopng: ok, last worked 2026-10-23 12:00 UTC",
        "- Wazuh: problem (Couldn't reach [address].)",
    ]
    assert "aresgate.example" not in text
    assert "192.168.1.2" not in text


def test_the_text_says_what_it_does_not_know() -> None:
    report = a_report()
    quiet = report.model_copy(
        update={
            "aresgate": report.aresgate.model_copy(update={"commit": None, "built_at": None}),
            "stack": status.StackInfo(
                python="3.14.8",
                nginx=None,
                database=status.DatabaseInfo(
                    status="unavailable",
                    version=None,
                    size_bytes=None,
                    connections=None,
                    max_connections=None,
                    migration=None,
                    migration_head="0008",
                ),
                certificate=None,
            ),
            "container": status.ContainerInfo(
                cpus=None, load=None, memory=None, disk=None, server_time=NOW
            ),
            "parts": [],
        }
    )

    assert status.diagnostics(quiet).splitlines() == [
        "AresGate diagnostics",
        "Version: 1.2.3",
        "Environment: production",
        "Up for: 3h 12m",
        "Python 3.14.8, nginx unknown",
        "Database: unavailable",
        "Certificate: not served here",
        "Parts:",
    ]


def test_the_text_says_when_the_database_is_behind_and_the_certificate_signed_itself() -> None:
    report = a_report()
    stack = report.stack
    behind = report.model_copy(
        update={
            "stack": stack.model_copy(
                update={
                    "database": stack.database.model_copy(update={"migration": None}),
                    "certificate": stack.certificate
                    and stack.certificate.model_copy(update={"self_signed": True}),
                }
            ),
            "container": report.container.model_copy(
                update={
                    "memory": status.Memory(used_bytes=1024, limit_bytes=None, total_bytes=4096),
                    "load": None,
                }
            ),
        }
    )

    text = status.diagnostics(behind)

    assert "migration unknown (this build expects 0008)" in text
    assert "Certificate: self-signed, 2 names, 30 days left" in text
    assert "Memory: 1023 B of 4.0 KB" in text or "Memory: 1.0 KB of 4.0 KB" in text
    assert "CPUs: 2\n" in text + "\n"
