"""The account, its sign-ins, and the record of failed attempts that slows down guessing."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UTCDateTime, utcnow

USERS_ID = "users.id"


class User(Base):
    """The one account that runs this install. Usernames are stored lowercase."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    # An Argon2id hash, which carries its own salt and settings.
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    password_changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class UserSession(Base):
    """A browser that is signed in. The cookie holds a random token; only its hash is kept."""

    __tablename__ = "user_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey(USERS_ID, ondelete="CASCADE"), index=True)
    # Pages send this back in a header on every change they ask for, which another website
    # can't read.
    csrf_token: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # The latest this sign-in can last, however busy it is.
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)

    user: Mapped[User] = relationship()


class LoginThrottle(Base):
    """Failed attempts to sign in or to use the setup code, counted per account and per address.
    ``key_hash`` is a hash of the username or address, so the table never holds either."""

    __tablename__ = "login_throttles"

    scope: Mapped[str] = mapped_column(String(16), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    last_failure_at: Mapped[datetime] = mapped_column(UTCDateTime)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class TotpCredential(Base):
    """An account's authenticator app. It starts out unconfirmed, while the person is adding it
    to their app, and only counts once a code from the app has proved it works."""

    __tablename__ = "totp_credentials"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey(USERS_ID, ondelete="CASCADE"), primary_key=True
    )
    # The key, sealed with the app secret key (see app/security/vault.py).
    secret_sealed: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    # The latest 30-second period a code was accepted for. A period works once.
    last_used_period: Mapped[int | None] = mapped_column(BigInteger, default=None)


class RecoveryCode(Base):
    """A code for signing in once without the authenticator app, kept as a keyed hash."""

    __tablename__ = "recovery_codes"
    __table_args__ = (
        UniqueConstraint("user_id", "code_hash", name="uq_recovery_codes_user_id_code_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # The unique constraint's index starts with the account, so looking its codes up needs no
    # index of its own.
    user_id: Mapped[UUID] = mapped_column(ForeignKey(USERS_ID, ondelete="CASCADE"))
    code_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
