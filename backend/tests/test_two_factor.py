from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import RecoveryCode, TotpCredential, User, utcnow
from app.security import recovery_codes, totp, two_factor, vault
from app.security.two_factor import Method
from tests.helpers import turn_on_two_factor


def code_at(secret: str, now: object, offset: int = 0) -> str:
    return totp.code_for(secret, totp.current_period(now) + offset)  # type: ignore[arg-type]


def test_a_new_account_has_no_authenticator_app(session: Session, account: User) -> None:
    assert not two_factor.is_enabled(session, account.id)
    assert two_factor.recovery_codes_left(session, account.id) == 0


def test_starting_gives_a_key_and_the_address_for_a_qr_code(
    session: Session, settings: Settings, account: User
) -> None:
    secret, uri = two_factor.start_enrollment(session, settings, account, utcnow())

    assert uri.startswith("otpauth://totp/AresGate:")
    assert f"secret={secret}" in uri
    assert uri.split("?")[0].endswith(account.username)


def test_the_key_is_kept_sealed(session: Session, settings: Settings, account: User) -> None:
    secret, _ = two_factor.start_enrollment(session, settings, account, utcnow())
    session.commit()

    sealed = session.scalars(select(TotpCredential.secret_sealed)).one()
    assert secret not in sealed
    assert vault.unseal(settings, "authenticator-key", sealed, str(account.id)) == secret.encode()


def test_the_account_is_not_protected_until_a_code_from_the_app_is_confirmed(
    session: Session, settings: Settings, account: User
) -> None:
    two_factor.start_enrollment(session, settings, account, utcnow())
    session.commit()

    assert not two_factor.is_enabled(session, account.id)


def test_starting_again_replaces_a_key_that_was_never_confirmed(
    session: Session, settings: Settings, account: User
) -> None:
    now = utcnow()
    first, _ = two_factor.start_enrollment(session, settings, account, now)
    second, _ = two_factor.start_enrollment(session, settings, account, now)
    session.commit()

    assert first != second
    assert session.scalar(select(func.count()).select_from(TotpCredential)) == 1
    assert (
        two_factor.confirm_enrollment(session, settings, account, code_at(first, now), now) is None
    )
    assert (
        two_factor.confirm_enrollment(session, settings, account, code_at(second, now), now)
        is not None
    )


def test_a_right_code_turns_it_on_and_gives_ten_recovery_codes(
    session: Session, settings: Settings, account: User
) -> None:
    secret, codes = turn_on_two_factor(session, settings, account)

    assert two_factor.is_enabled(session, account.id)
    assert len(codes) == len(set(codes)) == recovery_codes.COUNT == 10
    assert two_factor.recovery_codes_left(session, account.id) == 10
    assert secret


def test_only_a_hash_of_each_recovery_code_is_kept(
    session: Session, settings: Settings, account: User
) -> None:
    _, codes = turn_on_two_factor(session, settings, account)

    kept = set(session.scalars(select(RecoveryCode.code_hash)))
    assert kept == {recovery_codes.hash_code(settings, account.id, code) for code in codes}
    assert not any(code.replace("-", "") in hashed for code in codes for hashed in kept)


def test_a_wrong_code_does_not_turn_it_on(
    session: Session, settings: Settings, account: User
) -> None:
    now = utcnow()
    secret, _ = two_factor.start_enrollment(session, settings, account, now)

    assert (
        two_factor.confirm_enrollment(
            session, settings, account, code_at(secret, now, offset=5), now
        )
        is None
    )
    assert not two_factor.is_enabled(session, account.id)
    assert two_factor.recovery_codes_left(session, account.id) == 0


def test_confirming_needs_a_key_to_have_been_made(
    session: Session, settings: Settings, account: User
) -> None:
    now = utcnow()

    with pytest.raises(two_factor.NotEnrolling):
        two_factor.confirm_enrollment(session, settings, account, "123456", now)


def test_confirming_twice_is_refused_like_not_having_started(
    session: Session, settings: Settings, account: User
) -> None:
    turn_on_two_factor(session, settings, account)

    now = utcnow()

    with pytest.raises(two_factor.NotEnrolling):
        two_factor.confirm_enrollment(session, settings, account, "123456", now)


def test_it_cannot_be_started_again_while_on(
    session: Session, settings: Settings, account: User
) -> None:
    turn_on_two_factor(session, settings, account)

    now = utcnow()

    with pytest.raises(two_factor.AlreadyEnabled):
        two_factor.start_enrollment(session, settings, account, now)


def test_the_code_that_confirmed_it_cannot_sign_in(
    session: Session, settings: Settings, account: User
) -> None:
    now = utcnow()
    secret, _ = turn_on_two_factor(session, settings, account, now)

    assert two_factor.accept_code(session, settings, account.id, code_at(secret, now), now) is None


def test_the_next_code_is_accepted_once(
    session: Session, settings: Settings, account: User
) -> None:
    now = utcnow()
    secret, _ = turn_on_two_factor(session, settings, account, now)
    later = now + timedelta(seconds=30)
    code = code_at(secret, later)

    accepted = two_factor.accept_code(session, settings, account.id, code, later)

    assert accepted == two_factor.Accepted(Method.AUTHENTICATOR)
    assert two_factor.accept_code(session, settings, account.id, code, later) is None
    # Not even a little later, while the same period is still within the clock allowance.
    assert (
        two_factor.accept_code(session, settings, account.id, code, later + timedelta(seconds=30))
        is None
    )


def test_a_code_may_have_a_space_in_it(session: Session, settings: Settings, account: User) -> None:
    now = utcnow()
    secret, _ = turn_on_two_factor(session, settings, account, now)
    later = now + timedelta(seconds=30)
    code = code_at(secret, later)

    assert two_factor.accept_code(session, settings, account.id, f"{code[:3]} {code[3:]}", later)


def test_a_wrong_code_is_not_accepted(session: Session, settings: Settings, account: User) -> None:
    now = utcnow() + timedelta(seconds=30)
    secret, _ = turn_on_two_factor(session, settings, account)

    assert (
        two_factor.accept_code(session, settings, account.id, code_at(secret, now, 9), now) is None
    )
    assert two_factor.accept_code(session, settings, account.id, "hello", now) is None
    assert two_factor.accept_code(session, settings, account.id, "", now) is None


def test_an_account_without_one_accepts_no_code(
    session: Session, settings: Settings, account: User
) -> None:
    now = utcnow()

    assert two_factor.accept_code(session, settings, account.id, "123456", now) is None
    assert two_factor.accept_code(session, settings, account.id, "K7QD-3MWX-9HPA", now) is None


def test_a_key_still_being_added_does_not_sign_anyone_in(
    session: Session, settings: Settings, account: User
) -> None:
    now = utcnow()
    secret, _ = two_factor.start_enrollment(session, settings, account, now)

    assert two_factor.accept_code(session, settings, account.id, code_at(secret, now), now) is None


def test_a_recovery_code_works_once_however_it_is_typed(
    session: Session, settings: Settings, account: User
) -> None:
    _, codes = turn_on_two_factor(session, settings, account)
    code = codes[0]

    accepted = two_factor.accept_code(
        session, settings, account.id, code.lower().replace("-", " "), utcnow()
    )

    assert accepted == two_factor.Accepted(Method.RECOVERY_CODE, recovery_codes_left=9)
    assert two_factor.recovery_codes_left(session, account.id) == 9
    assert two_factor.accept_code(session, settings, account.id, code, utcnow()) is None
    assert (
        two_factor.accept_code(
            session, settings, account.id, codes[1], utcnow()
        ).recovery_codes_left  # type: ignore[union-attr]
        == 8
    )


def test_a_made_up_recovery_code_is_refused(
    session: Session, settings: Settings, account: User
) -> None:
    turn_on_two_factor(session, settings, account)

    assert two_factor.accept_code(session, settings, account.id, "AAAA-AAAA-AAAA", utcnow()) is None


def test_a_recovery_code_belongs_to_one_account(
    session: Session, settings: Settings, account: User
) -> None:
    _, codes = turn_on_two_factor(session, settings, account)

    assert two_factor.accept_code(session, settings, uuid4(), codes[0], utcnow()) is None


def test_new_recovery_codes_end_the_old_ones(
    session: Session, settings: Settings, account: User
) -> None:
    _, old = turn_on_two_factor(session, settings, account)

    new = two_factor.replace_recovery_codes(session, settings, account.id, utcnow())
    session.commit()

    assert len(new) == 10
    assert two_factor.recovery_codes_left(session, account.id) == 10
    assert two_factor.accept_code(session, settings, account.id, old[0], utcnow()) is None
    assert two_factor.accept_code(session, settings, account.id, new[0], utcnow()) is not None


def test_turning_it_off_removes_the_key_and_the_codes(
    session: Session, settings: Settings, account: User
) -> None:
    turn_on_two_factor(session, settings, account)

    two_factor.disable(session, account.id)
    session.commit()

    assert not two_factor.is_enabled(session, account.id)
    assert two_factor.recovery_codes_left(session, account.id) == 0
    assert session.scalar(select(func.count()).select_from(TotpCredential)) == 0
    assert session.scalar(select(func.count()).select_from(RecoveryCode)) == 0


def test_turning_it_off_on_an_account_without_one_changes_nothing(
    session: Session, account: User
) -> None:
    two_factor.disable(session, account.id)

    assert not two_factor.is_enabled(session, account.id)


def test_deleting_the_account_deletes_what_it_had(
    session: Session, settings: Settings, account: User
) -> None:
    turn_on_two_factor(session, settings, account)

    session.delete(account)
    session.commit()

    assert session.scalar(select(func.count()).select_from(TotpCredential)) == 0
    assert session.scalar(select(func.count()).select_from(RecoveryCode)) == 0


def test_a_challenge_names_the_account_for_a_few_minutes(settings: Settings) -> None:
    user_id, now = uuid4(), utcnow()
    challenge = two_factor.make_challenge(settings, user_id, now)

    assert two_factor.read_challenge(settings, challenge, now) == user_id
    assert two_factor.read_challenge(settings, challenge, now + timedelta(minutes=4)) == user_id
    assert two_factor.read_challenge(settings, challenge, now + timedelta(minutes=5)) is None
    assert two_factor.read_challenge(settings, challenge, now + timedelta(days=1)) is None


def test_a_challenge_made_with_another_key_is_refused(settings: Settings) -> None:
    other = settings.model_copy(
        update={"secret_key": SecretStr("another key, also long enough to be used")}
    )
    now = utcnow()
    challenge = two_factor.make_challenge(settings, uuid4(), now)

    assert two_factor.read_challenge(other, challenge, now) is None


def test_a_changed_challenge_is_refused(settings: Settings) -> None:
    now = utcnow()
    account, expires, signature = two_factor.make_challenge(settings, uuid4(), now).split(".")
    other_account = str(uuid4())
    later = int(expires) + 86400

    assert (
        two_factor.read_challenge(settings, f"{other_account}.{expires}.{signature}", now) is None
    )
    assert two_factor.read_challenge(settings, f"{account}.{later}.{signature}", now) is None
    assert two_factor.read_challenge(settings, f"{account}.{expires}.{signature[:-1]}", now) is None


@pytest.mark.parametrize("challenge", ["", "a.b", "a.b.c.d", "....", "not a challenge"])
def test_a_challenge_with_the_wrong_shape_is_refused(settings: Settings, challenge: str) -> None:
    assert two_factor.read_challenge(settings, challenge, utcnow()) is None


@pytest.mark.parametrize(
    ("account", "expires"), [("not-a-uuid", "9999999999"), (str(uuid4()), "soon")]
)
def test_a_correctly_signed_challenge_with_nonsense_in_it_is_refused(
    settings: Settings, account: str, expires: str
) -> None:
    body = f"{account}.{expires}"
    signed = f"{body}.{vault.keyed_hash(settings, 'sign-in-challenge', body)}"

    assert two_factor.read_challenge(settings, signed, utcnow()) is None
