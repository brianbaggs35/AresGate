from datetime import UTC, datetime

import pytest

from app.metrics.sample import MAX_LABEL_VALUE, MAX_LABELS, fingerprint
from tests.helpers import new_sample

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


class TestWhatASampleNeeds:
    @pytest.mark.parametrize("field", ["source", "connection"])
    @pytest.mark.parametrize("value", ["", "OPNsense", "a b", "x" * 33, "-start"])
    def test_a_source_and_a_connection_are_short_lowercase_names(
        self, field: str, value: str
    ) -> None:
        with pytest.raises(ValueError, match=field):
            new_sample(**{field: value})

    @pytest.mark.parametrize(
        "name", ["", "Load", "1m", "system load", "system-load", ".load", "a" * 65]
    )
    def test_what_is_measured_is_lowercase_words_joined_by_dots_or_underscores(
        self, name: str
    ) -> None:
        with pytest.raises(ValueError, match="measures"):
            new_sample(name=name)

    @pytest.mark.parametrize("name", ["load", "system.load_1m", "interface.bytes_in", "a" * 64])
    def test_a_name_that_fits_is_accepted(self, name: str) -> None:
        assert new_sample(name=name).name == name

    def test_the_time_needs_a_time_zone(self) -> None:
        naive = datetime(2026, 10, 25, 12, 0)

        with pytest.raises(ValueError, match="time zone"):
            new_sample(sampled_at=naive)

    @pytest.mark.parametrize("label", ["", "Interface", "1st", "inter-face", "x" * 33])
    def test_a_labels_name_is_a_short_lowercase_name(self, label: str) -> None:
        with pytest.raises(ValueError, match="label"):
            new_sample(labels={label: "igc0"})

    def test_there_are_only_so_many_labels(self) -> None:
        fits = {f"label_{index}": "x" for index in range(MAX_LABELS)}

        assert new_sample(labels=fits).labels == fits
        with pytest.raises(ValueError, match="labels"):
            new_sample(labels={**fits, "one_more": "x"})

    def test_it_needs_no_labels(self) -> None:
        assert new_sample().labels == {}
        assert new_sample().clean_labels == {}


class TestTheLabels:
    def test_a_value_is_cleaned_like_any_text_from_a_program(self) -> None:
        sample = new_sample(labels={"interface": " igc0\x00\n", "zone": "wan\u2028lan"})

        assert sample.clean_labels == {"interface": "igc0", "zone": "wan lan"}

    def test_a_long_value_is_cut_to_fit(self) -> None:
        sample = new_sample(labels={"description": "x" * (MAX_LABEL_VALUE + 50)})

        assert sample.clean_labels == {"description": "x" * MAX_LABEL_VALUE}

    def test_text_that_cant_be_encoded_is_replaced(self) -> None:
        sample = new_sample(labels={"interface": "igc\ud800"})

        assert sample.clean_labels == {"interface": "igc?"}

    def test_a_label_with_nothing_in_it_is_left_out(self) -> None:
        sample = new_sample(labels={"interface": "igc0", "zone": "  ", "gateway": ""})

        assert sample.clean_labels == {"interface": "igc0"}

    def test_they_come_back_in_order_of_name(self) -> None:
        sample = new_sample(labels={"zone": "wan", "interface": "igc0"})

        assert list(sample.clean_labels) == ["interface", "zone"]


class TestTheFingerprint:
    def test_the_same_series_has_the_same_one_whatever_the_value_or_time(self) -> None:
        first = new_sample(value=1.0, sampled_at=NOW)
        second = new_sample(value=2.0, sampled_at=datetime(2026, 10, 25, 13, 0, tzinfo=UTC))

        assert first.fingerprint == second.fingerprint
        assert len(first.fingerprint) == 64

    def test_it_doesnt_depend_on_the_order_the_labels_are_given_in(self) -> None:
        one = new_sample(labels={"interface": "igc0", "zone": "wan"})
        other = new_sample(labels={"zone": "wan", "interface": "igc0"})

        assert one.fingerprint == other.fingerprint

    def test_it_depends_on_the_source_the_connection_the_name_and_each_label(self) -> None:
        base = new_sample(labels={"interface": "igc0"})
        different = [
            new_sample(labels={"interface": "igc0"}, source="ntopng"),
            new_sample(labels={"interface": "igc0"}, connection="other"),
            new_sample(labels={"interface": "igc0"}, name="system.load_5m"),
            new_sample(labels={"interface": "igc1"}),
            new_sample(labels={"zone": "igc0"}),
            new_sample(),
        ]

        assert all(sample.fingerprint != base.fingerprint for sample in different)
        assert len({sample.fingerprint for sample in different}) == len(different)

    def test_labels_that_clean_up_to_the_same_text_are_one_series(self) -> None:
        one = new_sample(labels={"interface": "igc0"})
        other = new_sample(labels={"interface": " igc0\n", "zone": ""})

        assert one.fingerprint == other.fingerprint

    def test_the_parts_cannot_run_together(self) -> None:
        assert fingerprint("a", "b", "c.d", {}) != fingerprint("a", "bc", ".d", {})
        assert fingerprint("a", "b", "c", {"x": "yz"}) != fingerprint("a", "b", "c", {"xy": "z"})
