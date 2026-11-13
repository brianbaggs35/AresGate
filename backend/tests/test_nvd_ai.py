"""What the AI is told of the CVEs an incident names: the sentences, the triage prompt, and the
tool that looks one up."""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.ai import tools, triage
from app.ai.redaction import Level, Redactor
from app.ai.tools import Args
from app.models import IncidentSignal
from app.nvd import said
from tests.nvd_body import LOG4SHELL
from tests.nvd_support import NOW, kept
from tests.test_ai_triage import incident, signals

BLUEKEEP = "CVE-2019-0708"


def redact(text: str, limit: int) -> str:
    return text[:limit]


def tell(session: Session, cve_id: str, args: Args | None = None) -> tools.Found:
    tool = tools.by_name("vulnerability")
    assert tool is not None
    return tool.run(session, Redactor(session, Level.LOCAL, NOW), args or Args(name=cve_id), NOW)


class TestTheSentence:
    def test_a_cve_nvd_was_never_asked_about_says_so(self) -> None:
        assert said.said(None, LOG4SHELL, redact) == f"{LOG4SHELL}: NVD has not been asked about it"

    def test_a_cve_nvd_has_no_record_of_says_that_little_is_known(self, session: Session) -> None:
        from app.nvd import lookup, store

        row = store.keep(session, BLUEKEEP, lookup.Unknown(), NOW)

        assert said.said(row, BLUEKEEP, redact) == f"{BLUEKEEP}: {said.NOT_RECORDED}"

    def test_an_exploited_cve_says_its_score_the_list_it_is_on_and_what_it_is(
        self, session: Session
    ) -> None:
        row = kept(session)

        sentence = said.said(row, LOG4SHELL, redact)

        assert sentence.startswith(f"{LOG4SHELL}: CVSS 3.1 score 10.0, rated CRITICAL; ")
        assert "on CISA's Known Exploited Vulnerabilities list since 2021-12-10" in sentence
        assert "seen exploited in the wild" in sentence
        assert "weakness CWE-917" in sentence
        assert "described as: Apache Log4j2" in sentence

    def test_one_not_yet_scored_says_so_and_its_state(self, session: Session) -> None:
        row = kept(
            session,
            score=None,
            severity=None,
            cvss_version=None,
            status="Awaiting Analysis",
            exploited=False,
            exploited_on=None,
            weaknesses=[],
            description=None,
        )

        assert said.said(row, LOG4SHELL, redact) == (
            f"{LOG4SHELL}: no CVSS score yet (Awaiting Analysis)"
        )

    def test_a_score_with_no_state_and_an_unscored_cve_with_none_are_both_said(
        self, session: Session
    ) -> None:
        row = kept(session, score=None, severity=None, cvss_version=None, status=None)
        row.exploited = True
        row.exploited_on = None

        sentence = said.said(row, LOG4SHELL, redact)

        assert "no CVSS score yet (not analysed)" in sentence
        assert "list, so it has been seen exploited in the wild" in sentence
        assert " since " not in sentence

    def test_a_rejected_cve_is_said_not_to_be_a_real_vulnerability(self, session: Session) -> None:
        row = kept(session, status="Rejected", exploited=False, exploited_on=None)

        assert "NVD marks it Rejected, so it is not a real vulnerability" in said.said(
            row, LOG4SHELL, redact
        )

    def test_the_description_goes_through_the_redaction(self, session: Session) -> None:
        row = kept(session, description="x" * 500)

        sentence = said.said(row, LOG4SHELL, lambda text, limit: f"[{limit}]")

        assert sentence.endswith("described as: [300]")

    def test_only_three_weaknesses_are_named(self, session: Session) -> None:
        row = kept(session, weaknesses=["CWE-1", "CWE-2", "CWE-3", "CWE-4"])

        assert "weakness CWE-1, CWE-2, CWE-3;" in said.said(row, LOG4SHELL, redact)


class TestTheCvesNamed:
    def test_each_is_given_once_with_what_is_kept_of_it(self, session: Session) -> None:
        found = incident(session)
        signals(session, found, 1, summary=f"Exploit of {LOG4SHELL} and {LOG4SHELL.lower()}")
        signals(session, found, 1, summary="Nothing", signature=f"ET {BLUEKEEP}")
        row = kept(session)
        session.flush()

        named = said.named_in(session, list(session.query(IncidentSignal)))

        assert [cve_id for cve_id, _ in named] == [LOG4SHELL, BLUEKEEP]
        assert named[0][1] is not None
        assert named[0][1].cve_id == row.cve_id
        assert named[1][1] is None

    def test_no_more_than_the_most_are_given(self, session: Session) -> None:
        found = incident(session)
        text = " ".join(f"CVE-2021-{1000 + n}" for n in range(said.MOST + 4))
        signals(session, found, 1, summary=text)

        named = said.named_in(session, list(session.query(IncidentSignal)))

        assert len(named) == said.MOST


class TestTheTriagePrompt:
    def prompt(self, session: Session, found: object) -> str:
        redactor = Redactor(session, Level.BALANCED, NOW)
        return redactor.finish(triage.prompt_for(session, found, redactor))  # type: ignore[arg-type]

    def test_what_nvd_says_is_given_under_its_own_heading(self, session: Session) -> None:
        found = incident(session)
        signals(session, found, 1, summary=f"Exploit of {LOG4SHELL}")
        kept(session)

        prompt = self.prompt(session, found)

        assert said.HEADING in prompt
        assert f"- {LOG4SHELL}: CVSS 3.1 score 10.0, rated CRITICAL" in prompt
        assert "National Vulnerability Database" in triage.SYSTEM
        assert prompt.index(said.HEADING) < prompt.index("oldest first")

    def test_a_cve_not_asked_about_yet_is_said_to_be_unasked(self, session: Session) -> None:
        found = incident(session)
        signals(session, found, 1, summary=f"Exploit of {BLUEKEEP}")

        assert f"- {BLUEKEEP}: NVD has not been asked about it" in self.prompt(session, found)

    def test_an_incident_naming_no_cve_has_no_such_heading(self, session: Session) -> None:
        found = incident(session)
        signals(session, found, 2)

        assert said.HEADING not in self.prompt(session, found)


class TestTheTool:
    def test_it_tells_what_nvd_says_of_the_cve_asked_for(self, session: Session) -> None:
        kept(session, exploited_on=date(2021, 12, 10), checked=timedelta(hours=1))

        found = tell(session, f"  {LOG4SHELL.lower()} ")

        assert found.summary == f"NVD's record of {LOG4SHELL}"
        [line] = found.lines
        assert line.startswith(f"{LOG4SHELL}: CVSS 3.1 score 10.0, rated CRITICAL")
        assert line.endswith(".")

    def test_a_cve_not_asked_about_is_said_to_be_so(self, session: Session) -> None:
        assert tell(session, BLUEKEEP).lines == [f"{BLUEKEEP}: NVD has not been asked about it."]

    def test_something_that_is_not_a_cve_asks_for_one(self, session: Session) -> None:
        for name in ("", "log4shell", "CVE-1-2"):
            found = tell(session, name)
            assert found.summary == "no CVE given"
            assert found.lines == ["Give the CVE to look up, such as CVE-2021-44228."]

    def test_no_name_at_all_asks_for_one(self, session: Session) -> None:
        assert tell(session, "", Args()).summary == "no CVE given"
