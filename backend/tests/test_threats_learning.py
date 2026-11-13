"""Learning from what the owner decides: what they have decided of a kind, when a kind is offered
to be set aside or to be watched, and that a suggestion is never taken for them."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events.event import Severity
from app.models import Incident, IncidentChain, IncidentFamily, ReviewFeedback
from app.threats import learning, overview
from app.threats.settings import Tuning
from tests.test_ai_families import kind
from tests.test_ai_service import NOW

MINUTE = timedelta(minutes=1)


def members(session: Session, family: IncidentFamily) -> list[Incident]:
    return sorted(
        session.scalars(select(Incident).where(Incident.family_id == family.id)),
        key=lambda each: each.id,
    )


def decide(
    session: Session, family: IncidentFamily, *, dismissed: int = 0, loud: int = 0, **more: object
) -> None:
    """The owner dismisses the first ``dismissed`` incidents of the kind, then calls the next
    ``loud`` of them threats."""
    each = members(session, family)
    for found in each[:dismissed]:
        found.status = "dismissed"
    for found in each[dismissed : dismissed + loud]:
        found.verdict = "threat"
    for name, value in more.items():
        setattr(family, name, value)
    session.commit()


def disagree(session: Session, family: IncidentFamily, times: int = 1) -> None:
    for _ in range(times):
        session.add(
            ReviewFeedback(
                subject="family",
                subject_id=family.id,
                title="A scan",
                ai_class="probe",
                ai_confidence=90,
                answer="disagree",
            )
        )
    session.commit()


def item(session: Session, family: IncidentFamily) -> overview.Kind:
    [found] = overview.kinds(session, 35, Tuning(), family_id=family.id).items
    return found


class TestWhatTheOwnerDecided:
    def test_closing_an_incident_as_benign_or_dismissing_it_is_one_and_taking_it_up_is_the_other(
        self, session: Session
    ) -> None:
        family = kind(session, 8)
        first, second, third, fourth, fifth, sixth, *_ = members(session, family)
        first.verdict = "not_suspicious"
        second.verdict = "low_priority"
        third.status = "dismissed"
        fourth.verdict = "threat"
        fifth.status = "investigating"
        fifth.status_changed_at = NOW
        # Taking it up with no change on record is how it began, not a decision.
        sixth.status = "investigating"
        session.commit()

        assert learning.patterns(session, [family.id])[family.id] == learning.Pattern(3, 2)

    def test_taking_it_up_comes_before_dismissing_it(self, session: Session) -> None:
        family = kind(session, 1)
        [only] = members(session, family)
        only.verdict = "threat"
        only.status = "dismissed"
        session.commit()

        assert learning.patterns(session, [family.id])[family.id] == learning.Pattern(0, 1)

    def test_a_kind_is_counted_by_all_its_incidents_going_on_or_not(self, session: Session) -> None:
        family = kind(session, 3)
        for each in members(session, family):
            each.status = "resolved"
        members(session, family)[0].verdict = "low_priority"
        session.commit()

        assert learning.patterns(session, [family.id])[family.id].benign == 1

    def test_disagreeing_with_the_ai_about_a_kind_counts_as_taking_it_up(
        self, session: Session
    ) -> None:
        family = kind(session, 3)
        disagree(session, family, 2)

        assert learning.patterns(session, [family.id])[family.id] == learning.Pattern(0, 2)

    def test_the_kinds_with_enough_decided_are_found_without_asking_for_them(
        self, session: Session
    ) -> None:
        few = kind(session, 4, "ET SCAN few")
        many = kind(session, 4, "ET SCAN many")
        decide(session, few, dismissed=2)
        decide(session, many, dismissed=3)
        disagree(session, many)

        found = learning.patterns(session)

        assert found == {many.id: learning.Pattern(3, 1)}

    def test_nothing_decided_is_nothing(self, session: Session) -> None:
        family = kind(session, 3)

        assert learning.patterns(session, [family.id]) == {family.id: learning.Pattern()}
        assert learning.Pattern().decided == 0


class TestWhichKindsHaveHadAChain:
    def test_a_chain_two_stages_or_a_sign_it_worked_are_one(self, session: Session) -> None:
        plain = kind(session, 2, "ET SCAN plain")
        two = kind(session, 2, "ET SCAN two")
        worked = kind(session, 2, "ET SCAN worked")
        linked = kind(session, 2, "ET SCAN linked")
        members(session, two)[0].stages = ["recon", "access"]
        members(session, worked)[0].stages = ["foothold"]
        members(session, plain)[0].stages = ["recon"]
        session.commit()
        link = IncidentChain(device="192.168.1.20", first_seen_at=NOW, last_seen_at=NOW)
        session.add(link)
        session.flush()
        members(session, linked)[0].chain_id = link.id
        session.commit()

        assert learning.chained(session, [plain.id, two.id, worked.id, linked.id]) == {
            two.id,
            worked.id,
            linked.id,
        }
        assert learning.chained(session, []) == set()


class TestWhenAKindIsOffered:
    def test_a_kind_you_keep_dismissing_is_offered_as_always_background(
        self, session: Session
    ) -> None:
        family = kind(session, 8)
        decide(session, family, dismissed=5)

        offer = learning.of_kind(session, item(session, family))

        assert offer == learning.Suggestion(learning.BACKGROUND, 5, 0, 3)
        assert offer is not None
        assert offer.decided == 5
        assert offer.reason == (
            "You have closed 5 of the 5 incidents of this kind you decided as not suspicious, "
            "low priority or dismissed."
        )

    def test_most_has_to_be_benign_and_enough_decided(self, session: Session) -> None:
        family = kind(session, 12)
        decide(session, family, dismissed=4)
        assert learning.of_kind(session, item(session, family)) is None

        decide(session, family, dismissed=5)
        assert learning.of_kind(session, item(session, family)) is not None

        # Five benign of seven decided is less than four in five.
        decide(session, family, dismissed=5, loud=2)
        assert learning.of_kind(session, item(session, family)) is None

    def test_four_in_five_is_most(self, session: Session) -> None:
        family = kind(session, 12)
        decide(session, family, dismissed=8, loud=2)

        assert learning.of_kind(session, item(session, family)) == learning.Suggestion(
            learning.BACKGROUND, 8, 2, 4
        )

    def test_a_kind_that_has_had_a_chain_in_it_is_never_offered(self, session: Session) -> None:
        family = kind(session, 8)
        decide(session, family, dismissed=5)
        members(session, family)[7].stages = ["recon", "access"]
        session.commit()

        assert learning.of_kind(session, item(session, family)) is None

    def test_a_kind_you_have_called_is_not_offered(self, session: Session) -> None:
        family = kind(session, 8)
        decide(session, family, dismissed=5, owner_call="watch")

        assert learning.of_kind(session, item(session, family)) is None

    def test_a_kind_with_nothing_to_set_aside_is_not_offered(self, session: Session) -> None:
        family = kind(session, 5)
        decide(session, family, dismissed=5)

        assert (
            learning.suggestion_for(
                overview.Kind(family, 0, 0, 0, Severity.INFO, NOW, NOW, 0, 0, 0),
                learning.Pattern(5, 0),
                False,
            )
            is None
        )

    def test_a_kind_the_ai_cleared_that_you_keep_taking_up_is_offered_as_never_set_aside(
        self, session: Session
    ) -> None:
        family = kind(session, 8)
        decide(session, family, loud=3, ai_class="probe", ai_confidence=92, review="auto")

        offer = learning.of_kind(session, item(session, family))

        assert offer is not None
        assert (offer.call, offer.loud, offer.benign) == (learning.WATCH, 3, 0)
        assert offer.reason == (
            "The AI set this kind aside, and you have taken up 3 of the 3 incidents of it you "
            "decided, or disagreed with it."
        )

    def test_the_moves_are_those_it_would_bring_back_out_of_the_background(
        self, session: Session
    ) -> None:
        family = kind(session, 8, confidence=20)
        decide(session, family, loud=3, ai_class="probe", ai_confidence=92, review="auto")

        offer = learning.of_kind(session, item(session, family))

        assert offer is not None
        assert offer.moves == item(session, family).background

    def test_a_kind_the_ai_did_not_clear_is_not_offered_to_be_watched(
        self, session: Session
    ) -> None:
        family = kind(session, 8)
        decide(session, family, loud=3)
        assert learning.of_kind(session, item(session, family)) is None

        family.ai_class = "attack"
        family.ai_confidence = 90
        session.commit()
        assert learning.of_kind(session, item(session, family)) is None

        # One it set aside that you have not agreed with yet is not in effect, so not offered.
        family.ai_class = "probe"
        family.review = "pending"
        session.commit()
        assert learning.of_kind(session, item(session, family)) is None

    def test_taking_up_a_few_among_many_you_let_go_is_not_enough(self, session: Session) -> None:
        family = kind(session, 12)
        decide(session, family, dismissed=6, loud=3, ai_class="probe", ai_confidence=92)

        assert learning.of_kind(session, item(session, family)) is None

    def test_what_you_said_not_now_to_is_offered_again_only_when_you_have_decided_twice_as_many(
        self, session: Session
    ) -> None:
        family = kind(session, 14)
        decide(session, family, dismissed=5)
        offer = learning.of_kind(session, item(session, family))
        assert offer is not None

        learning.dismiss(family, offer)
        session.commit()

        assert (family.suggestion_dismissed, family.suggestion_dismissed_count) == ("background", 5)
        assert learning.of_kind(session, item(session, family)) is None
        decide(session, family, dismissed=9)
        assert learning.of_kind(session, item(session, family)) is None
        decide(session, family, dismissed=10)
        assert learning.of_kind(session, item(session, family)) is not None

    def test_saying_not_now_to_one_offer_leaves_the_other_open(self, session: Session) -> None:
        family = kind(session, 8)
        decide(session, family, loud=3, ai_class="probe", ai_confidence=92, review="auto")
        family.suggestion_dismissed = "background"
        family.suggestion_dismissed_count = 100
        session.commit()

        offer = learning.of_kind(session, item(session, family))

        assert offer is not None
        assert offer.call == learning.WATCH


class TestWhatThePageShows:
    def test_the_kinds_with_the_most_decided_come_first_and_no_more_than_a_few(
        self, session: Session
    ) -> None:
        kinds = [kind(session, 9, f"ET SCAN number {letter}") for letter in "abcde"]
        for number, family in enumerate(kinds):
            decide(session, family, dismissed=5 + number % 4)

        shown = learning.offers(session, 35, Tuning())

        assert len(shown) == learning.SHOWN
        assert [offer.decided for _, offer in shown] == sorted(
            (offer.decided for _, offer in shown), reverse=True
        )
        assert {offer.call for _, offer in shown} == {learning.BACKGROUND}

    def test_a_kind_with_nothing_going_on_or_nothing_to_offer_is_left_out(
        self, session: Session
    ) -> None:
        over = kind(session, 5, "ET SCAN over")
        for each in members(session, over):
            each.status = "dismissed"
        session.commit()
        called = kind(session, 8, "ET SCAN called")
        decide(session, called, dismissed=5, owner_call="background")
        offered = kind(session, 8, "ET SCAN offered")
        decide(session, offered, dismissed=5)

        shown = learning.offers(session, 35, Tuning())

        assert [found.family.id for found, _ in shown] == [offered.id]

    def test_nothing_decided_offers_nothing(self, session: Session) -> None:
        kind(session, 8)

        assert learning.offers(session, 35, Tuning()) == []
