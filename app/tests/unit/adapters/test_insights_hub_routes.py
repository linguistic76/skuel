"""The Insights cards' door (``adapters/inbound/insights_ui.py`` — ``/insights/hub/{question}``).

Driven through a real ``fast_app`` + TestClient so FastHTML's own binding of the
``question`` segment is what is tested. Pinned: the auth gate (401), an unknown
question (404), every ``HubQuestion`` answered as its card (200, the mount id, the
hub method of the same number asked), a failed rich-context read and a failed hub
answer rendered as the question's error card (200, never a 500), the titles a card
shows resolved from the rich context first and from one Ku batch for the rest, and
the ``/insights`` page mounting the section only when the hub is wired.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.insights_ui import create_insights_ui_routes
from core.models.context_types import (
    CrossDomainSynergy,
    LifePathAlignment,
    PathStep,
    ScheduleAwareRecommendation,
)
from core.models.enums import HubQuestion
from core.ports.query_types import PerceptionAnalysis
from core.services.user.unified_user_context import RichUserContext
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_hub_owner"
KU_IN_CONTEXT = "ku.hub.engaged"
KU_OUTSIDE = "ku.hub.unseen"
GOAL = "goal_hub_ship"


def _fake_auth(request: object) -> str:
    return _USER_UID


def _context() -> RichUserContext:
    """A rich context carrying one goal's and one engaged Ku's titles."""
    context = RichUserContext(user_uid=_USER_UID)
    context.entities_rich = {
        "goals": [{"entity": {"uid": GOAL, "title": "Ship the hub"}, "graph_context": {}}]
    }
    context.knowledge_units_rich = {
        KU_IN_CONTEXT: {"ku": {"uid": KU_IN_CONTEXT, "title": "Engaged concept"}}
    }
    return context


def _ku(uid: str, title: str) -> MagicMock:
    ku = MagicMock()
    ku.uid = uid
    ku.title = title
    return ku


def _hub() -> MagicMock:
    """Every hub method answers; each test overrides the one it asks."""
    hub = MagicMock()
    hub.get_optimal_next_path_steps = AsyncMock(
        return_value=Result.ok(
            [
                PathStep(ku_uid=KU_IN_CONTEXT, title=f"Knowledge Unit {KU_IN_CONTEXT}"),
                PathStep(ku_uid=KU_OUTSIDE, title=f"Knowledge Unit {KU_OUTSIDE}"),
            ]
        )
    )
    hub.get_unblocking_priority_order = AsyncMock(return_value=Result.ok([(KU_OUTSIDE, 2)]))
    hub.get_cross_domain_synergies = AsyncMock(
        return_value=Result.ok(
            [
                CrossDomainSynergy(
                    source_uid=KU_OUTSIDE,
                    source_domain="knowledge",
                    target_uids=(GOAL,),
                    target_domain="goal",
                    synergy_type="required by",
                    synergy_score=0.6,
                )
            ]
        )
    )
    hub.calculate_life_path_alignment = AsyncMock(
        return_value=Result.ok(
            LifePathAlignment(
                overall_score=0.5,
                alignment_level="exploring",
                knowledge_score=0.5,
                activity_score=0.5,
                goal_score=0.5,
                principle_score=0.5,
                momentum_score=0.5,
                life_path_uid="lp.hub.path",
                aligned_goals=(GOAL,),
                knowledge_gaps=(KU_OUTSIDE,),
            )
        )
    )
    hub.get_schedule_aware_recommendations = AsyncMock(
        return_value=Result.ok(
            [
                ScheduleAwareRecommendation(
                    uid=KU_OUTSIDE,
                    entity_type="knowledge",
                    recommendation_type="learn",
                    title=KU_OUTSIDE,
                    rationale="Prerequisites met, ready to learn",
                )
            ]
        )
    )
    hub.get_cross_domain_perception_analysis = AsyncMock(
        return_value=Result.ok(
            PerceptionAnalysis(
                per_domain={},
                over_rated_domains=[],
                under_rated_domains=[],
                accurate_domains=[],
                total_assessed_entities=0,
                insights=["No self-assessments recorded yet."],
                has_data=False,
            )
        )
    )
    return hub


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    user_service: MagicMock
    factory: MagicMock
    hub: MagicMock
    ku_service: MagicMock


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
    context: Result[RichUserContext] | None = None,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    store = MagicMock()
    store.get_active_insights = AsyncMock(return_value=Result.ok([]))
    store.filter_insights = MagicMock(return_value=[])

    user_service = MagicMock()
    user_service.get_rich_unified_context = AsyncMock(
        return_value=context if context is not None else Result.ok(_context())
    )
    hub = _hub()
    factory = MagicMock()
    factory.create = MagicMock(return_value=hub)
    ku_service = MagicMock()
    ku_service.get_kus_batch = AsyncMock(
        return_value=Result.ok([_ku(KU_OUTSIDE, "Unseen concept")])
    )

    if authenticated:
        monkeypatch.setattr("adapters.inbound.insights_ui.require_authenticated_user", _fake_auth)

    # BasePage needs the whole chrome; the page test reads what the route hands it.
    def _identity_page(content, **_kwargs):  # type: ignore[no-untyped-def]  # boundary: BasePage stub
        return content

    monkeypatch.setattr("adapters.inbound.insights_ui.BasePage", _identity_page)

    create_insights_ui_routes(
        None,
        rt,
        store,
        user_service=user_service,
        context_intelligence=factory,
        ku_service=ku_service,
    )
    return _Harness(TestClient(app), user_service, factory, hub, ku_service)


class TestRegistration:
    @pytest.mark.parametrize("absent", ["user_service", "context_intelligence", "ku_service"])
    def test_a_missing_hub_service_refuses_registration(self, absent: str) -> None:
        """The hub is wired in both tiers; a page without its cards is not a mode."""
        _app, rt = fast_app(pico=False, default_hdrs=False)
        services: dict[str, Any] = {
            "user_service": MagicMock(),
            "context_intelligence": MagicMock(),
            "ku_service": MagicMock(),
        }
        services[absent] = None
        with pytest.raises(ValueError, match=absent):
            create_insights_ui_routes(None, rt, MagicMock(), **services)


class TestTheDoor:
    def test_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)
        assert harness.client.get("/insights/hub/learn-next").status_code == 401

    def test_an_unknown_question_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        response = harness.client.get("/insights/hub/critical-path")
        assert response.status_code == 404
        harness.user_service.get_rich_unified_context.assert_not_awaited()

    @pytest.mark.parametrize("question", list(HubQuestion))
    def test_every_question_answers_as_its_card(
        self, monkeypatch: pytest.MonkeyPatch, question: HubQuestion
    ) -> None:
        harness = _make_harness(monkeypatch)
        response = harness.client.get(question.fragment_url())
        assert response.status_code == 200
        assert f'id="{question.mount_id()}"' in response.text
        assert question.label() in response.text
        harness.user_service.get_rich_unified_context.assert_awaited_once_with(_USER_UID)
        harness.factory.create.assert_called_once()

    def test_each_question_asks_the_hub_method_of_its_number(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked = {
            HubQuestion.LEARN_NEXT: "get_optimal_next_path_steps",
            HubQuestion.UNBLOCK_FIRST: "get_unblocking_priority_order",
            HubQuestion.SYNERGIES: "get_cross_domain_synergies",
            HubQuestion.ALIGNMENT: "calculate_life_path_alignment",
            HubQuestion.RIGHT_NOW: "get_schedule_aware_recommendations",
            HubQuestion.PERCEPTION: "get_cross_domain_perception_analysis",
        }
        for question, method in asked.items():
            harness = _make_harness(monkeypatch)
            harness.client.get(question.fragment_url())
            getattr(harness.hub, method).assert_awaited_once()
            others = [m for m in asked.values() if m != method]
            for other in others:
                getattr(harness.hub, other).assert_not_awaited()

    def test_a_failed_context_read_is_the_error_card_not_a_500(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(
            monkeypatch, context=Result.fail(Errors.system(message="graph away"))
        )
        response = harness.client.get("/insights/hub/synergies")
        assert response.status_code == 200
        assert 'id="hub-synergies"' in response.text
        assert "couldn't be answered" in response.text and "graph away" in response.text
        harness.factory.create.assert_not_called()

    def test_a_failed_hub_answer_is_the_error_card(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.hub.get_optimal_next_path_steps.return_value = Result.fail(
            Errors.not_found("PathStep", KU_OUTSIDE)
        )
        response = harness.client.get("/insights/hub/learn-next")
        assert response.status_code == 200
        assert 'id="hub-learn-next"' in response.text and "couldn't be answered" in response.text


class TestTitles:
    def test_context_titles_first_and_one_ku_batch_for_the_rest(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)
        response = harness.client.get("/insights/hub/learn-next")
        assert "Engaged concept" in response.text
        assert "Unseen concept" in response.text
        assert "Knowledge Unit" not in response.text
        # Only the uid the context lacked went to the graph.
        harness.ku_service.get_kus_batch.assert_awaited_once_with([KU_OUTSIDE])

    def test_a_record_saying_ku_instead_of_knowledge_resolves_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)
        harness.hub.get_schedule_aware_recommendations.return_value = Result.ok(
            [
                ScheduleAwareRecommendation(
                    uid=KU_OUTSIDE,
                    entity_type="ku",
                    recommendation_type="learn",
                    title=KU_OUTSIDE,
                    rationale="ready",
                )
            ]
        )
        response = harness.client.get("/insights/hub/right-now")
        assert "Unseen concept" in response.text
        harness.ku_service.get_kus_batch.assert_awaited_once_with([KU_OUTSIDE])

    def test_no_missing_title_means_no_ku_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.hub.get_optimal_next_path_steps.return_value = Result.ok(
            [PathStep(ku_uid=KU_IN_CONTEXT, title="placeholder")]
        )
        harness.client.get("/insights/hub/learn-next")
        harness.ku_service.get_kus_batch.assert_not_awaited()

    def test_a_failed_ku_batch_leaves_the_fallback_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)
        harness.ku_service.get_kus_batch.return_value = Result.fail(
            Errors.database(message="batch away", operation="get_many")
        )
        response = harness.client.get("/insights/hub/unblock-first")
        assert response.status_code == 200
        assert KU_OUTSIDE in response.text

    @pytest.mark.parametrize(
        "question",
        [HubQuestion.SYNERGIES, HubQuestion.ALIGNMENT, HubQuestion.RIGHT_NOW],
    )
    def test_knowledge_uids_on_the_other_records_resolve_too(
        self, monkeypatch: pytest.MonkeyPatch, question: HubQuestion
    ) -> None:
        harness = _make_harness(monkeypatch)
        response = harness.client.get(question.fragment_url())
        assert "Unseen concept" in response.text, question
        harness.ku_service.get_kus_batch.assert_awaited_once_with([KU_OUTSIDE])
        if question is HubQuestion.ALIGNMENT:
            assert "Ship the hub" in response.text  # the aligned goal, from the context


class TestThePage:
    def test_the_page_mounts_the_section(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        response = harness.client.get("/insights")
        assert response.status_code == 200
        assert 'id="insights-hub"' in response.text
        for question in HubQuestion:
            assert f'hx-get="{question.fragment_url()}"' in response.text, question
