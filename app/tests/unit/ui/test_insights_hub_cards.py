"""Render tests for the Insights cards (``ui/insights/hub_cards.py``).

Server-rendered, so everything is asserted on the markup. The contract: the section
mounts one lazy fragment per ``HubQuestion`` and names the staged seventh question as
a note, never a card; every card swaps into the mount its question owns; a uid is
never shown when a title is known, and an entity links to its detail page by its
record's domain; each empty state names the door that feeds the question.
"""

from __future__ import annotations

from fastcore.xml import to_xml  # type: ignore[import-untyped]

from core.models.context_types import (
    CrossDomainSynergy,
    LifePathAlignment,
    PathStep,
    ScheduleAwareRecommendation,
)
from core.models.enums import HubQuestion
from core.ports.query_types import PerceptionAnalysis, PerceptionDomainRollup
from ui.insights.hub_cards import (
    STAGED_CRITICAL_PATH_NOTE,
    render_alignment_card,
    render_hub_card_error,
    render_hub_section,
    render_learn_next_card,
    render_perception_card,
    render_right_now_card,
    render_synergies_card,
    render_unblock_first_card,
)

TITLES = {
    "ku.t.alpha": "Alpha concept",
    "goal_t_ship": "Ship the thing",
    "habit_t_run": "Morning run",
    "task_t_bills": "Pay the bills",
}


def _html(fragment) -> str:  # type: ignore[no-untyped-def]  # boundary: FT in, markup out
    return to_xml(fragment)


class TestTheSection:
    def test_mounts_one_lazy_fragment_per_question(self) -> None:
        html = _html(render_hub_section())
        for question in HubQuestion:
            assert f'hx-get="{question.fragment_url()}"' in html, question
            assert f'id="{question.mount_id()}"' in html, question
        assert html.count('hx-trigger="load"') == len(HubQuestion)

    def test_the_critical_path_is_a_note_not_a_card(self) -> None:
        html = _html(render_hub_section())
        assert STAGED_CRITICAL_PATH_NOTE in html
        assert "/insights/hub/critical-path" not in html


class TestEveryCardOwnsItsMount:
    def test_each_card_swaps_into_its_questions_mount(self) -> None:
        cards = {
            HubQuestion.LEARN_NEXT: render_learn_next_card([], TITLES),
            HubQuestion.UNBLOCK_FIRST: render_unblock_first_card([], TITLES),
            HubQuestion.SYNERGIES: render_synergies_card([], TITLES),
            HubQuestion.ALIGNMENT: render_alignment_card(_no_life_path(), TITLES),
            HubQuestion.RIGHT_NOW: render_right_now_card([], TITLES),
            HubQuestion.PERCEPTION: render_perception_card(_perception(has_data=False)),
        }
        assert set(cards) == set(HubQuestion)
        for question, card in cards.items():
            html = _html(card)
            assert f'id="{question.mount_id()}"' in html, question
            assert question.label() in html, question
            assert f"Question {question.number()}" in html, question

    def test_the_error_card_keeps_the_question_and_says_why(self) -> None:
        html = _html(render_hub_card_error(HubQuestion.SYNERGIES, "the graph is away"))
        assert f'id="{HubQuestion.SYNERGIES.mount_id()}"' in html
        assert HubQuestion.SYNERGIES.label() in html
        assert "the graph is away" in html


class TestLearnNext:
    def test_a_step_shows_its_title_and_links_the_ku_page(self) -> None:
        step = PathStep(
            ku_uid="ku.t.alpha",
            title="Knowledge Unit ku.t.alpha",  # the ZPD source's placeholder
            rationale="Helps with 1 active goals",
            prerequisites_met=False,
            aligns_with_goals=("goal_t_ship",),
            unlocks_count=2,
            estimated_time_minutes=45,
            priority_score=0.75,
        )
        html = _html(render_learn_next_card([step], TITLES))
        assert "Alpha concept" in html
        assert "Knowledge Unit ku.t.alpha" not in html
        assert 'href="/explore/ku/ku.t.alpha"' in html
        assert "~45 min" in html and "unlocks 2" in html and "prerequisites pending" in html
        assert "serves 1 goals" in html and "Helps with 1 active goals" in html

    def test_an_unknown_title_falls_back_to_the_steps_own(self) -> None:
        step = PathStep(ku_uid="ku.t.unknown", title="Knowledge Unit ku.t.unknown")
        html = _html(render_learn_next_card([step], TITLES))
        assert "Knowledge Unit ku.t.unknown" in html

    def test_empty_points_at_explore(self) -> None:
        html = _html(render_learn_next_card([], TITLES))
        assert "Nothing is ready to learn yet" in html
        assert 'href="/explore"' in html


class TestUnblockFirst:
    def test_rows_name_the_prerequisite_and_what_it_unlocks(self) -> None:
        html = _html(render_unblock_first_card([("ku.t.alpha", 3), ("ku.t.beta", 1)], TITLES))
        assert "Alpha concept" in html and "unlocks 3 units" in html
        assert "ku.t.beta" in html and "unlocks 1 unit<" in html  # no title known → uid

    def test_empty_says_nothing_is_held_back(self) -> None:
        assert "holding anything" in _html(render_unblock_first_card([], TITLES))


class TestSynergies:
    def test_a_synergy_links_its_source_by_domain_and_counts_its_targets(self) -> None:
        synergy = CrossDomainSynergy(
            source_uid="habit_t_run",
            source_domain="habit",
            target_uids=("goal_t_ship", "goal_t_other"),
            target_domain="goal",
            synergy_type="supports",
            synergy_score=0.5,
            rationale="This habit supports 2 goals simultaneously",
            recommendations=("Build consistency", "High-leverage habit!", "a third tip"),
        )
        html = _html(render_synergies_card([synergy], TITLES))
        assert "Morning run" in html and 'href="/habits/detail?uid=habit_t_run"' in html
        assert "supports 2 goals" in html
        assert "This habit supports 2 goals simultaneously" in html
        assert "Build consistency" in html and "a third tip" not in html  # two tips shown

    def test_a_knowledge_source_links_the_ku_page(self) -> None:
        synergy = CrossDomainSynergy(
            source_uid="ku.t.alpha", source_domain="knowledge", target_domain="task"
        )
        html = _html(render_synergies_card([synergy], TITLES))
        assert 'href="/explore/ku/ku.t.alpha"' in html and "Alpha concept" in html

    def test_empty_points_at_the_link_doors(self) -> None:
        html = _html(render_synergies_card([], TITLES))
        assert "No cross-domain leverage yet" in html and 'href="/goals"' in html


def _no_life_path() -> LifePathAlignment:
    return LifePathAlignment(
        overall_score=0.0,
        alignment_level="undefined",
        knowledge_score=0.0,
        activity_score=0.0,
        goal_score=0.0,
        principle_score=0.0,
        momentum_score=0.0,
        gaps=("No life path defined - consider defining your ultimate direction",),
    )


class TestAlignment:
    def test_no_life_path_points_at_designating_one(self) -> None:
        html = _html(render_alignment_card(_no_life_path(), TITLES))
        assert "haven't designated a life path" in html
        assert 'href="/lifepath"' in html
        assert "progressbar" not in html

    def test_an_aligned_user_sees_the_score_the_dimensions_and_named_entities(self) -> None:
        alignment = LifePathAlignment(
            overall_score=0.55,
            alignment_level="exploring",
            knowledge_score=0.2,
            activity_score=0.4,
            goal_score=0.6,
            principle_score=0.8,
            momentum_score=1.0,
            gaps=("Knowledge gaps in life path areas",),
            recommendations=("Focus on learning life path prerequisites",),
            life_path_uid="lp.t.path",
            aligned_goals=("goal_t_ship",),
            knowledge_gaps=("ku.t.alpha",),
        )
        html = _html(render_alignment_card(alignment, TITLES))
        assert "55%" in html and "exploring" in html
        assert html.count('role="progressbar"') == 5
        for label in ("Knowledge", "Activity", "Goals", "Principles", "Momentum"):
            assert label in html, label
        assert "Ship the thing" in html and 'href="/goals/detail?uid=goal_t_ship"' in html
        assert "Alpha concept" in html and 'href="/explore/ku/ku.t.alpha"' in html
        assert "Knowledge gaps in life path areas" in html
        assert "Focus on learning life path prerequisites" in html


class TestRightNow:
    def test_a_recommendation_shows_the_title_the_kind_and_the_fit(self) -> None:
        rec = ScheduleAwareRecommendation(
            uid="task_t_bills",
            entity_type="task",
            recommendation_type="task",
            title="Pay the bills",
            rationale="This task is overdue and needs attention",
            estimated_duration_minutes=30,
            fits_available_time=False,
            overall_score=0.96,
            streak_at_risk=False,
            life_path_aligned=True,
        )
        html = _html(render_right_now_card([rec], TITLES))
        assert "Pay the bills" in html and 'href="/tasks/detail?uid=task_t_bills"' in html
        assert "This task is overdue" in html
        assert "~30 min" in html and "longer than the time you have" in html
        assert "life path" in html and "streak at risk" not in html

    def test_a_knowledge_recommendation_takes_the_resolved_title(self) -> None:
        rec = ScheduleAwareRecommendation(
            uid="ku.t.alpha",
            entity_type="knowledge",
            recommendation_type="learn",
            title="ku.t.alpha",  # the hub's fallback when the context has no title
            rationale="Prerequisites met, ready to learn",
        )
        html = _html(render_right_now_card([rec], TITLES))
        assert "Alpha concept" in html and 'href="/explore/ku/ku.t.alpha"' in html

    def test_rest_is_a_recommendation_without_a_link(self) -> None:
        rec = ScheduleAwareRecommendation(
            uid="rest",
            entity_type="meta",
            recommendation_type="rest",
            title="Take a Break",
            rationale="Workload is at 90%+ capacity. Consider taking a break.",
        )
        html = _html(render_right_now_card([rec], TITLES))
        assert "Take a Break" in html and "href=" not in html

    def test_empty_names_the_candidates(self) -> None:
        assert "Nothing is pressing" in _html(render_right_now_card([], TITLES))


def _perception(*, has_data: bool) -> PerceptionAnalysis:
    if not has_data:
        return PerceptionAnalysis(
            per_domain={},
            over_rated_domains=[],
            under_rated_domains=[],
            accurate_domains=[],
            total_assessed_entities=0,
            insights=["No self-assessments recorded yet."],
            has_data=False,
        )
    return PerceptionAnalysis(
        per_domain={
            "goals": PerceptionDomainRollup(
                label="Goals",
                assessed_count=2,
                direction_counts={"user_higher": 2, "system_higher": 0, "aligned": 0},
                avg_gap=0.3,
                dominant_direction="user_higher",
            ),
            "habits": PerceptionDomainRollup(
                label="Habits",
                assessed_count=0,
                direction_counts={"user_higher": 0, "system_higher": 0, "aligned": 0},
                avg_gap=0.0,
                dominant_direction=None,
            ),
            "knowledge": PerceptionDomainRollup(
                label="Knowledge",
                assessed_count=1,
                direction_counts={"user_higher": 0, "system_higher": 1, "aligned": 0},
                avg_gap=-0.2,
                dominant_direction="system_higher",
            ),
        },
        over_rated_domains=["Goals"],
        under_rated_domains=["Knowledge"],
        accurate_domains=[],
        total_assessed_entities=3,
        insights=["You tend to rate yourself higher than your tracked actions on Goals."],
        has_data=True,
    )


class TestPerception:
    def test_no_data_links_the_self_checkin(self) -> None:
        html = _html(render_perception_card(_perception(has_data=False)))
        assert "No self-assessments yet" in html
        assert 'href="/self-checkin"' in html

    def test_assessed_domains_carry_their_direction_and_unassessed_ones_are_absent(
        self,
    ) -> None:
        html = _html(render_perception_card(_perception(has_data=True)))
        assert "You tend to rate yourself higher" in html
        assert "Goals" in html and "over-rated" in html and "2 assessed" in html
        assert "Knowledge" in html and "under-rated" in html
        assert "Habits" not in html
        assert 'href="/self-checkin"' in html
