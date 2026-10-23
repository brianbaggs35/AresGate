"""What the install says about itself, for the status page: AresGate, the programs it runs on,
the container around them and the health of each part. Nothing here holds a secret, and the text
made for bug reports leaves out addresses as well."""

import os
import platform
import re
import shutil
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal

from alembic.script import ScriptDirectory
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.integrations import netguard

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"
# nginx listens here inside the container, whatever port it is published on.
NGINX_TLS_PORT = 8443
APK_DATABASE = Path("/lib/apk/db/installed")
CGROUP = Path("/sys/fs/cgroup")
PROC = Path("/proc")
DATA_DIRECTORY = Path("/data")

# A computer's clock more than this far from this one's is worth saying so.
CLOCK_TOLERANCE_SECONDS = 60
# A certificate this close to the end is worth saying so.
CERTIFICATE_WARNING_DAYS = 14

State = Literal["ok", "problem", "unknown", "off"]


class BuildInfo(BaseModel):
    version: str
    commit: str | None
    built_at: AwareDatetime | None
    environment: str
    started_at: AwareDatetime
    uptime_seconds: int


class DatabaseInfo(BaseModel):
    status: Literal["ok", "unavailable"]
    # PostgreSQL's own version, e.g. 18.1.
    version: str | None
    size_bytes: int | None
    connections: int | None
    max_connections: int | None
    # The migration the database is at, and the one this build expects. They differ while an
    # update is half done, or after an image older than the data is started.
    migration: str | None
    migration_head: str | None


class CertificateInfo(BaseModel):
    subject: str
    issuer: str
    names: list[str]
    not_before: AwareDatetime
    not_after: AwareDatetime
    days_left: int
    self_signed: bool


class StackInfo(BaseModel):
    python: str
    nginx: str | None
    database: DatabaseInfo
    # What nginx presents, or None where nothing is serving it (running from source).
    certificate: CertificateInfo | None


class Memory(BaseModel):
    used_bytes: int
    # None when nothing limits it but the computer's own memory, which is then the total.
    limit_bytes: int | None
    total_bytes: int | None


class Disk(BaseModel):
    used_bytes: int
    total_bytes: int


class ContainerInfo(BaseModel):
    # How many CPUs it may use: the limit it was given, or all the computer has.
    cpus: float | None
    # Processes waiting to run, averaged over the last 1, 5 and 15 minutes.
    load: list[float] | None
    memory: Memory | None
    disk: Disk | None
    # Its clock, for the page to compare with the browser's.
    server_time: AwareDatetime


class Part(BaseModel):
    """One part of AresGate that can be healthy or not. Integrations now; collectors, AI
    providers, notification channels and background jobs join them as they are built."""

    key: str
    name: str
    group: Literal["integration"]
    state: State
    detail: str | None
    last_success_at: AwareDatetime | None


class StatusReport(BaseModel):
    aresgate: BuildInfo
    stack: StackInfo
    container: ContainerInfo
    parts: list[Part]
    # The same facts as text to paste into a bug report, with addresses left out.
    diagnostics: str


# ---- The database ------------------------------------------------------------------------


def migration_head(directory: Path = MIGRATIONS) -> str | None:
    """The newest migration this build has."""
    return ScriptDirectory(str(directory)).get_current_head()


def database_info(db: Session, head: str | None) -> DatabaseInfo:
    try:
        # Some builds add their packaging to it, as in "18.1 (Debian 18.1-1)".
        version = db.scalar(text("SELECT split_part(current_setting('server_version'), ' ', 1)"))
        size = db.scalar(text("SELECT pg_database_size(current_database())"))
        connections = db.scalar(
            text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
        )
        limit = db.scalar(text("SELECT current_setting('max_connections')::int"))
    except SQLAlchemyError:
        return DatabaseInfo(
            status="unavailable",
            version=None,
            size_bytes=None,
            connections=None,
            max_connections=None,
            migration=None,
            migration_head=head,
        )
    return DatabaseInfo(
        status="ok",
        version=version,
        size_bytes=size,
        connections=connections,
        max_connections=limit,
        migration=_current_migration(db),
        migration_head=head,
    )


def _current_migration(db: Session) -> str | None:
    """Where the database is, or None for one that migrations didn't make (the tests')."""
    try:
        with db.begin_nested():
            return db.scalar(text("SELECT version_num FROM alembic_version"))
    except SQLAlchemyError:
        return None


# ---- The programs ------------------------------------------------------------------------


def packaged_version(name: str, database: Path = APK_DATABASE) -> str | None:
    """The version of a package of the container's operating system, such as 1.29.1, from the
    list Wolfi keeps of what it installed. Nothing is run to find it."""
    try:
        listing = database.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for block in listing.split("\n\n"):
        fields = dict(line.split(":", 1) for line in block.splitlines() if ":" in line)
        if fields.get("P") == name and (version := fields.get("V")):
            # 1.29.1-r0 is the version and the package's revision of it.
            return version.rsplit("-r", 1)[0]
    return None


def certificate_info(
    server_name: str,
    *,
    port: int = NGINX_TLS_PORT,
    now: datetime,
    look_up: Callable[..., netguard.CertificateInfo | None] | None = None,
) -> CertificateInfo | None:
    """The certificate nginx presents for AresGate's name, which is the one a browser sees."""
    found = (look_up or netguard.look_up_served_certificate)("127.0.0.1", port, server_name)
    if found is None:
        return None
    return CertificateInfo(
        subject=found.subject,
        issuer=found.issuer,
        names=found.names,
        not_before=found.not_before,
        not_after=found.not_after,
        days_left=(found.not_after - now).days,
        self_signed=found.subject == found.issuer,
    )


# ---- The container -----------------------------------------------------------------------


def _read_int(path: Path) -> int | None:
    """A number in a file, or None where there is no such file or it says something else (such
    as ``max``, for no limit)."""
    try:
        return int(path.read_text(encoding="ascii").strip())
    except OSError, ValueError:
        return None


def _meminfo(proc: Path) -> tuple[int, int] | None:
    """The computer's memory in use and in all, in bytes."""
    try:
        lines = (proc / "meminfo").read_text(encoding="ascii").splitlines()
    except OSError:
        return None
    sizes = {
        name: int(value.split()[0]) * 1024
        for name, _, value in (line.partition(":") for line in lines)
        if value.split()[:1] and value.split()[0].isdigit()
    }
    if "MemTotal" not in sizes or "MemAvailable" not in sizes:
        return None
    return sizes["MemTotal"] - sizes["MemAvailable"], sizes["MemTotal"]


def memory_info(cgroup: Path = CGROUP, proc: Path = PROC) -> Memory | None:
    """What the container uses, against what it may. Without a container's limits it is the
    computer's memory, as the programs in it see it."""
    computer = _meminfo(proc)
    used = _read_int(cgroup / "memory.current")
    limit = _read_int(cgroup / "memory.max")
    if used is None:
        return (
            None
            if computer is None
            else Memory(used_bytes=computer[0], limit_bytes=None, total_bytes=computer[1])
        )
    return Memory(used_bytes=used, limit_bytes=limit, total_bytes=computer[1] if computer else None)


def cpu_count(cgroup: Path = CGROUP) -> float | None:
    """How many CPUs the container may use: its limit, or else all the computer has."""
    try:
        quota, period = (cgroup / "cpu.max").read_text(encoding="ascii").split()
        if quota != "max":
            return round(int(quota) / int(period), 2)
    except OSError, ValueError:
        pass
    return float(len(os.sched_getaffinity(0))) or None


def disk_info(path: Path) -> Disk | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    return Disk(used_bytes=usage.used, total_bytes=usage.total)


def load_average() -> list[float] | None:
    try:
        return [round(value, 2) for value in os.getloadavg()]
    except OSError:
        return None


def container_info(now: datetime, data: Path | None = None) -> ContainerInfo:
    volume = data if data is not None else DATA_DIRECTORY
    return ContainerInfo(
        cpus=cpu_count(),
        load=load_average(),
        memory=memory_info(),
        disk=disk_info(volume if volume.exists() else Path("/")),
        server_time=now,
    )


# ---- Redaction and the text for a bug report ---------------------------------------------

_REDACTIONS: Sequence[re.Pattern[str]] = (
    # Up to the last character that can be part of the address, so the sentence's own full
    # stop or bracket after it stays.
    re.compile(r"[a-z][a-z0-9+.-]*://\S*[^\s.,;:)\]]", re.IGNORECASE),
    re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"),
    re.compile(r"\b(?:[0-9a-f]{1,4}:){3,7}[0-9a-f]{0,4}\b", re.IGNORECASE),
    # A name with dots in it that ends in letters, so 1.29.1 and 18.1 are left alone.
    re.compile(r"\b(?:[a-z0-9-]+\.)+[a-z][a-z0-9-]*(?::\d+)?\b", re.IGNORECASE),
)


def redact(value: str) -> str:
    """Takes the addresses out of some text: web addresses, IP addresses and host names."""
    for pattern in _REDACTIONS:
        value = pattern.sub("[address]", value)
    return value


def human_size(value: int | None) -> str:
    if value is None:
        return "unknown"
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if amount < 1024:
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"


def human_duration(seconds: int) -> str:
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    parts = [f"{days}d"] if days else []
    parts += [f"{hours}h"] if days or hours else []
    return " ".join([*parts, f"{minutes}m"])


def _database_line(database: DatabaseInfo) -> str:
    if database.status != "ok":
        return "Database: unavailable"
    migration = (
        f"migration {database.migration or 'unknown'} "
        f"(this build expects {database.migration_head})"
    )
    return (
        f"Database: PostgreSQL {database.version}, {human_size(database.size_bytes)}, "
        f"{database.connections} of {database.max_connections} connections, {migration}"
    )


def _certificate_line(certificate: CertificateInfo | None) -> str:
    if certificate is None:
        return "Certificate: not served here"
    kind = "self-signed" if certificate.self_signed else f"issued by {redact(certificate.issuer)}"
    return f"Certificate: {kind}, {len(certificate.names)} names, {certificate.days_left} days left"


def _container_lines(container: ContainerInfo) -> list[str]:
    lines: list[str] = []
    if container.memory:
        limit = container.memory.limit_bytes or container.memory.total_bytes
        lines.append(f"Memory: {human_size(container.memory.used_bytes)} of {human_size(limit)}")
    if container.disk:
        used, total = container.disk.used_bytes, container.disk.total_bytes
        lines.append(f"Disk: {human_size(used)} of {human_size(total)}")
    if container.cpus is not None:
        load = " ".join(str(value) for value in container.load or [])
        lines.append(f"CPUs: {container.cpus:g}" + (f", load {load}" if load else ""))
    return lines


def diagnostics(report: StatusReport) -> str:
    """The report as plain text for a bug report. It has versions, sizes, states and times,
    and never an address, a name or a secret: text that came from elsewhere is run through
    ``redact`` first."""
    build = report.aresgate
    stamps = [f"commit {build.commit[:12]}"] if build.commit else []
    stamps += [f"built {build.built_at:%Y-%m-%d %H:%M} UTC"] if build.built_at else []
    version = build.version + (f" ({', '.join(stamps)})" if stamps else "")
    lines = [
        "AresGate diagnostics",
        f"Version: {version}",
        f"Environment: {build.environment}",
        f"Up for: {human_duration(build.uptime_seconds)}",
        f"Python {report.stack.python}, nginx {report.stack.nginx or 'unknown'}",
        _database_line(report.stack.database),
        _certificate_line(report.stack.certificate),
        *_container_lines(report.container),
        "Parts:",
    ]
    for part in report.parts:
        line = f"- {part.name}: {part.state}"
        if part.last_success_at:
            line += f", last worked {part.last_success_at:%Y-%m-%d %H:%M} UTC"
        if part.detail:
            line += f" ({redact(part.detail)})"
        lines.append(line)
    return "\n".join(lines)


def python_version() -> str:
    return platform.python_version()
