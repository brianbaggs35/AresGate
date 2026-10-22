"""Application settings, read from ``ARESGATE_*`` environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARESGATE_", env_file=".env", extra="ignore")

    environment: Literal["production", "development", "test"] = "production"
    # The version a release image was built as, which the release workflow stamps in from
    # the release's tag. Builds from source report the version in app/__init__.py.
    release: str | None = None
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
    secret_key_file: Path = Path("/data/secrets/secret.key")

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

    @property
    def version(self) -> str:
        return self.release or __version__

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def public_origin(self) -> str:
        port = "" if self.https_port == 443 else f":{self.https_port}"
        return f"https://{self.server_name}{port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
