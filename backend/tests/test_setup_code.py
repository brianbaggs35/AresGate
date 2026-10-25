import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import SystemInfo, User
from app.security import setup_code


def test_a_code_is_three_groups_of_four(session: Session) -> None:
    code = setup_code.generate()

    groups = code.split("-")
    assert [len(group) for group in groups] == [4, 4, 4]
    assert set(code.replace("-", "")) <= set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")


def test_codes_are_not_repeated() -> None:
    assert len({setup_code.generate() for _ in range(50)}) == 50


def test_only_a_hash_is_kept(session: Session) -> None:
    code = setup_code.issue(session)
    session.commit()

    stored = session.get(SystemInfo, setup_code.KEY)
    assert stored is not None
    assert stored.value != code
    assert code.replace("-", "") not in stored.value


def test_the_code_matches_however_it_is_typed(session: Session) -> None:
    code = setup_code.issue(session)
    session.commit()
    stored = setup_code.lock(session)
    assert stored is not None

    assert setup_code.matches(stored, code)
    assert setup_code.matches(stored, code.lower())
    assert setup_code.matches(stored, code.replace("-", " "))
    assert setup_code.matches(stored, f"  {code}\n")
    assert not setup_code.matches(stored, "AAAA-AAAA-AAAA")
    assert not setup_code.matches(stored, "")


def test_a_new_code_replaces_the_old_one(session: Session) -> None:
    old = setup_code.issue(session)
    new = setup_code.issue(session)
    session.commit()
    stored = setup_code.lock(session)
    assert stored is not None

    assert setup_code.matches(stored, new)
    assert not setup_code.matches(stored, old)
    assert len(list(session.scalars(select(SystemInfo)))) == 1


def test_there_is_no_code_to_lock_until_one_is_issued(session: Session) -> None:
    assert setup_code.lock(session) is None


def test_a_used_code_is_gone(session: Session) -> None:
    setup_code.issue(session)

    setup_code.consume(session)
    session.commit()

    assert setup_code.lock(session) is None


def test_a_code_can_be_chosen(session: Session) -> None:
    setup_code.store(session, "TEST-2222-ABCD")
    session.commit()
    stored = setup_code.lock(session)
    assert stored is not None

    assert setup_code.matches(stored, "test-2222-abcd")


def test_the_log_shows_the_code_and_where_to_use_it() -> None:
    lines = setup_code.banner("K7QD-3MWX-9HPA", ["https://aresgate.example.com"]).splitlines()

    assert any(line.strip() == "K7QD-3MWX-9HPA" for line in lines)
    assert any(
        line.strip() == "Open https://aresgate.example.com and enter this setup code:"
        for line in lines
    )


def test_the_log_names_every_address_that_works() -> None:
    addresses = ["https://aresgate.example.com", "https://localhost"]

    lines = setup_code.banner("K7QD-3MWX-9HPA", addresses).splitlines()

    assert any(
        line.strip()
        == "Open https://aresgate.example.com or https://localhost and enter this setup code:"
        for line in lines
    )


@pytest.fixture
def announcing(engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    """Runs announce() against the test database, with the settings the tests use."""
    monkeypatch.setattr(
        setup_code, "get_sessionmaker", lambda: sessionmaker(bind=engine, expire_on_commit=False)
    )
    monkeypatch.setattr(setup_code, "get_settings", lambda: settings)


def test_a_fresh_install_prints_a_code_that_works(
    announcing: None, session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    setup_code.announce()

    shown = capsys.readouterr().out
    code = next(line.strip() for line in shown.splitlines() if line.strip().count("-") == 2)
    stored = setup_code.lock(session)
    assert stored is not None
    assert setup_code.matches(stored, code)
    assert any(
        line.strip() == "Open https://aresgate.test or https://localhost and enter this setup code:"
        for line in shown.splitlines()
    )


def test_each_start_prints_a_new_code(
    announcing: None, session: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    setup_code.announce()
    first = capsys.readouterr().out
    setup_code.announce()
    second = capsys.readouterr().out

    assert first != second
    assert len(list(session.scalars(select(SystemInfo)))) == 1


def test_an_install_with_an_account_prints_nothing(
    announcing: None,
    session: Session,
    capsys: pytest.CaptureFixture[str],
    account: User,
) -> None:
    setup_code.announce()

    assert capsys.readouterr().out == ""
    assert setup_code.lock(session) is None
