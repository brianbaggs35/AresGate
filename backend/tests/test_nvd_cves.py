"""Finding the CVEs an incident names."""

from app.nvd import cves


def test_a_cve_is_found_in_text_and_written_in_capitals() -> None:
    found = cves.ids_in("ET EXPLOIT Apache Log4j RCE (cve-2021-44228) attempt")

    assert found == ["CVE-2021-44228"]


def test_each_cve_is_listed_once_in_the_order_it_first_appears() -> None:
    found = cves.ids_in("CVE-2019-0708 then CVE-2021-44228", "CVE-2019-0708 and CVE-2014-0160")

    assert found == ["CVE-2019-0708", "CVE-2021-44228", "CVE-2014-0160"]


def test_text_that_only_looks_like_a_cve_is_not_one() -> None:
    assert (
        cves.ids_in("XCVE-2021-44228", "CVE-2021-123", "CVE-1998-1234", "CVE-2021-12345678") == []
    )


def test_nothing_is_found_in_no_text() -> None:
    assert cves.ids_in(None, "", "no vulnerability") == []


def test_a_signal_that_lists_thousands_names_only_the_first_few() -> None:
    text = " ".join(f"CVE-2020-{number}" for number in range(1000, 1100))

    assert len(cves.ids_in(text)) == cves.PER_SIGNAL


def test_a_signal_names_the_cves_of_its_summary_its_signature_and_its_evidence() -> None:
    found = cves.named_by(
        "Blocked an exploit of CVE-2021-44228",
        "ET EXPLOIT CVE-2019-0708 BlueKeep",
        {"indicators": [{"kind": "cve", "value": "CVE-2014-0160"}], "facts": [["Fix", "none"]]},
    )

    assert found == ["CVE-2021-44228", "CVE-2019-0708", "CVE-2014-0160"]


def test_a_signal_with_no_evidence_names_only_what_it_says() -> None:
    assert cves.named_by("scan", None, None) == []
    assert cves.named_by("scan", None, {}) == []


def test_one_cve_and_nothing_more_is_a_cve() -> None:
    assert cves.is_cve(" cve-2021-44228 ")
    assert not cves.is_cve("CVE-2021-44228 and more")
    assert not cves.is_cve("CVE-1998-1234")
    assert not cves.is_cve("2021-44228")


def test_groups_merge_into_one_list_without_repeats() -> None:
    assert cves.merge([["CVE-2021-0001"], ["CVE-2021-0002", "CVE-2021-0001"]]) == [
        "CVE-2021-0001",
        "CVE-2021-0002",
    ]
