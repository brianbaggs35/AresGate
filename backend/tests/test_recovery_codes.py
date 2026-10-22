from uuid import uuid4

from app.config import Settings
from app.security import recovery_codes, setup_code


def test_a_code_is_three_groups_of_four_from_the_unambiguous_alphabet() -> None:
    code = recovery_codes.generate()

    groups = code.split("-")
    assert [len(group) for group in groups] == [4, 4, 4]
    assert set("".join(groups)) <= set(setup_code.ALPHABET)


def test_codes_are_different_each_time() -> None:
    assert len({recovery_codes.generate() for _ in range(50)}) == 50


def test_however_a_code_is_typed_it_is_the_same_code() -> None:
    assert recovery_codes.normalize(" k7qd 3mwx-9hpa ") == "K7QD3MWX9HPA"
    assert recovery_codes.looks_like_code("k7qd3mwx9hpa")
    assert not recovery_codes.looks_like_code("K7QD-3MWX")
    assert not recovery_codes.looks_like_code("123456")


def test_what_is_kept_depends_on_the_account_and_not_on_how_the_code_was_typed(
    settings: Settings,
) -> None:
    user, other = uuid4(), uuid4()
    kept = recovery_codes.hash_code(settings, user, "K7QD-3MWX-9HPA")

    assert kept == recovery_codes.hash_code(settings, user, "k7qd 3mwx 9hpa")
    assert kept != recovery_codes.hash_code(settings, other, "K7QD-3MWX-9HPA")
    assert "K7QD" not in kept
