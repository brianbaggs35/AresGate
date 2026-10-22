import pytest
from sqlalchemy.orm import Session

from app.models import User
from app.security.accounts import (
    UsernameError,
    any_user_exists,
    check_username,
    find_user,
    normalize_username,
)
from tests.helpers import ACCOUNT_USERNAME


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("brian", "brian"),
        ("  Brian ", "brian"),
        ("BRIAN@Example.COM", "brian@example.com"),
        ("\uff42\uff52\uff49\uff41\uff4e", "brian"),  # full-width letters
    ],
)
def test_usernames_are_compared_in_one_form(typed: str, stored: str) -> None:
    assert normalize_username(typed) == stored


@pytest.mark.parametrize("username", ["bob", "brian.baggs", "b_r-i@n", "a" * 64, "007"])
def test_a_username_that_follows_the_rules_is_accepted(username: str) -> None:
    check_username(username)


@pytest.mark.parametrize("username", ["", "ab", "a" * 65, "has space", "slash/slash", "ünï", "a;b"])
def test_a_username_that_breaks_the_rules_is_refused(username: str) -> None:
    with pytest.raises(UsernameError, match=r"3 to 64"):
        check_username(username)


def test_no_account_until_there_is_one(session: Session) -> None:
    assert not any_user_exists(session)
    assert find_user(session, ACCOUNT_USERNAME) is None


def test_the_account_is_found_by_its_username(session: Session, account: User) -> None:
    assert any_user_exists(session)
    assert find_user(session, ACCOUNT_USERNAME) == account
    assert find_user(session, "someone-else") is None


@pytest.mark.parametrize("name", ["a\x00b", "", "ab", "Brian", "has space", "x" * 65])
def test_a_name_no_account_can_have_finds_nothing_and_asks_nothing_of_the_database(
    session: Session, account: User, name: str
) -> None:
    assert find_user(session, name) is None
