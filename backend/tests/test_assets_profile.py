from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.assets import profile

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)


class TestTheKinds:
    def test_every_kind_is_in_a_group_the_page_shows(self) -> None:
        groups = {key for key, _ in profile.GROUPS}

        assert {kind.group for kind in profile.KINDS} <= groups
        assert len(profile.BY_KEY) == len(profile.KINDS)

    def test_the_pieces_of_the_network_carry_other_things_traffic(self) -> None:
        carrying = {kind.key for kind in profile.KINDS if kind.carries}

        assert carrying == {"router", "firewall", "modem", "switch", "access_point"}


class TestGuessing:
    @pytest.mark.parametrize(
        ("hostname", "vendor", "kind"),
        [
            ("Home-Router", None, "router"),
            ("diskstation", "Synology Inc.", "nas"),
            ("front-cam", None, "camera"),
            ("Brians-iPhone", "Apple, Inc.", "phone"),
            ("living-room-tv", None, "tv"),
            (None, "Brother Industries", "printer"),
            ("sonos-kitchen", None, "speaker"),
            ("PS5", None, "game_console"),
            (None, "Espressif Inc.", "smart_home"),
            ("macbook-pro", None, "laptop"),
        ],
    )
    def test_a_name_or_a_maker_can_say_what_it_is(
        self, hostname: str | None, vendor: str | None, kind: str
    ) -> None:
        assert profile.suggest(hostname, vendor) == kind

    def test_a_short_word_has_to_be_a_whole_word(self) -> None:
        # "tv" is in "activity" and "cam" in "campbell", and neither is a TV or a camera.
        assert profile.suggest("activity-box", None) is None
        assert profile.suggest("campbell", None) is None

    def test_nothing_said_is_nothing_guessed(self) -> None:
        assert profile.suggest(None, None) is None
        assert profile.suggest("box-17", "Example Devices Inc.") is None


class TestWhatTheOwnerSaid:
    def test_it_is_kept_and_read_back(self, session: Session) -> None:
        said = profile.save(session, "device-1", "camera", "  Watches the front door ", NOW)

        assert (said.kind, said.purpose, said.label, said.carries) == (
            "camera",
            "Watches the front door",
            "Camera or doorbell",
            False,
        )
        assert profile.load(session) == {"device-1": said}

    def test_saying_it_again_replaces_it(self, session: Session) -> None:
        profile.save(session, "host-3", "server", "Old", NOW)
        profile.save(session, "host-3", "router", "   ", NOW)

        (kept,) = profile.load(session).values()

        assert (kept.kind, kept.purpose, kept.carries) == ("router", None, True)

    def test_it_can_be_taken_back_once(self, session: Session) -> None:
        profile.save(session, "device-1", "tv", None, NOW)
        session.flush()

        assert profile.clear(session, "device-1") is True
        assert profile.clear(session, "device-1") is False
        assert profile.load(session) == {}

    def test_what_was_said_of_devices_is_found_by_their_ids(self, session: Session) -> None:
        profile.save(session, "device-1", "tv", None, NOW)
        profile.save(session, "device-2", "laptop", None, NOW)
        profile.save(session, "host-1", "server", None, NOW)

        found = profile.for_devices(session, [1, 3])

        assert list(found) == [1]
        assert profile.for_devices(session, []) == {}


class TestDescribing:
    def test_it_is_a_clause_for_a_line_about_the_asset(self) -> None:
        said = profile.Profile("camera", "Watches the front door", NOW)

        assert profile.describe(said, lambda text, limit: text[:limit]) == (
            ", which the owner says is a camera or doorbell (Watches the front door)"
        )

    def test_a_kind_with_no_purpose_says_only_the_kind(self) -> None:
        assert profile.describe(profile.Profile("tv", None, NOW), lambda text, limit: text) == (
            ", which the owner says is a tv"
        )

    def test_nothing_said_is_nothing_added(self) -> None:
        assert profile.describe(None, lambda text, limit: text) == ""
