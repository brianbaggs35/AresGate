"""Passkeys (WebAuthn credentials) and the challenges that are waiting to be answered."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, ForeignKey, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, utcnow


class Passkey(Base):
    """A passkey an account can sign in with. Nothing here is secret: the private key never
    leaves the person's device, and what is kept is the public key that checks its signatures."""

    __tablename__ = "passkeys"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # What the person called it, such as "Work laptop".
    name: Mapped[str] = mapped_column(String(64))
    # What the device calls it. Signing in names the passkey this way, which also names the
    # account.
    credential_id: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    # The credential ID, the device model and the public key, as WebAuthn encodes them.
    credential_data: Mapped[bytes] = mapped_column(LargeBinary)
    # How many times the device says it has signed. It only goes up, so a copy of the passkey
    # that signs in is noticed.
    sign_count: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class PasskeyChallenge(Base):
    """What a device is asked to sign, kept until it answers or the time is up. It can be used
    once, so a recorded answer is no use to anyone."""

    __tablename__ = "passkey_challenges"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # "register" for adding a passkey, "sign_in" for using one.
    purpose: Mapped[str] = mapped_column(String(16))
    # Who is adding a passkey. Empty when signing in, which doesn't know who yet.
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), default=None
    )
    challenge: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
