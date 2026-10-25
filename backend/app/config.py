"""Application settings, read from ``ARESGATE_*`` environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__

# Where the container keeps the secret key it makes on its first start.
DEFAULT_SECRET_KEY_FILE = Path("/data/secrets/secret.key")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARESGATE_", env_file=".env", extra="ignore")

    environment: Literal["production", "development", "test"] = "production"
    # The version a release image was built as, which the release workflow stamps in from
    # the release's tag. Builds from source report the version in app/__init__.py.
    release: str | None = None
    # Which commit the image was built from and when, which the status page shows. A release
    # image has them stamped in; a build from source has no way to know, and shows neither.
    commit: Annotated[str, Field(max_length=64)] | None = None
    built_at: AwareDatetime | None = None
    # The bundled Postgres only listens on its unix socket, and the API connects with peer
    # auth, so there's no password (sonar-project.properties tells SonarQube so).
    database_url: str = "postgresql+psycopg://aresgate@/aresgate?host=/run/postgresql"
    database_echo: bool = False
    # Interactive OpenAPI docs are off unless explicitly enabled.
    enable_docs: bool = False

    # The app secret key, which encrypts what AresGate stores. The container makes one in its
    # data volume the first time it starts, so it's only set to bring a key from somewhere else
    # (a restored backup, a secret manager). Either the key itself or a file holding it, such as
    # a Docker secret: app/secret_key.py has the rules.
    secret_key: SecretStr | None = None
    secret_key_file: Path = DEFAULT_SECRET_KEY_FILE

    # The name people browse to and the host port it's served on. Passkeys and the check that
    # requests really come from AresGate's own pages are bound to this address.
    server_name: str = "localhost"
    https_port: Annotated[int, Field(ge=1, le=65535)] = 443

    # What the logs look like: one JSON object a line, or plain text for reading while developing.
    log_format: Literal["json", "text"] = "json"
    log_level: Literal["debug", "info", "warning", "error"] = "info"

    # How long a sign-in lasts: until it has been idle for this long, or this long after it
    # began, whichever comes first.
    session_idle_minutes: Annotated[int, Field(ge=1)] = 30
    session_max_hours: Annotated[int, Field(ge=1)] = 12

    # How long the audit log keeps an event before the API deletes it.
    audit_retention_days: Annotated[int, Field(ge=1, le=3650)] = 365
    # How long the API log keeps a request made to an integration. It is much busier than the
    # audit log, and only useful while it is recent.
    api_log_retention_days: Annotated[int, Field(ge=1, le=365)] = 30

    # How long events from the integrations are kept, for a source that has no setting of its own.
    event_retention_days: Annotated[int, Field(ge=1, le=3650)] = 30
    # The same for the numbers they measure: a firewall's load, an interface's traffic.
    metric_retention_days: Annotated[int, Field(ge=1, le=3650)] = 30

    # Whether the worker collects from the integrations. Turned off, it keeps running and says
    # so on the status page, which is how to pause collecting without stopping the container.
    collectors_enabled: bool = True

    @field_validator("release", "commit", "built_at", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        """A build argument that wasn't given is an empty variable, which means it isn't set."""
        return None if value == "" else value

    @property
    def version(self) -> str:
        return self.release or __version__

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def public_origin(self) -> str:
        return f"https://{self.server_name}{self._port_suffix}"

    @property
    def own_origins(self) -> tuple[str, ...]:
        """Every address AresGate answers at, the server name first. nginx also answers to
        localhost, so it works on the computer that runs AresGate whatever the server name is
        (and nothing else is let in: an IP address, or any other name, is refused by nginx)."""
        return tuple(dict.fromkeys([self.public_origin, f"https://localhost{self._port_suffix}"]))

    @property
    def _port_suffix(self) -> str:
        return "" if self.https_port == 443 else f":{self.https_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
