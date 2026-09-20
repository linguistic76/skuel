"""PsAdaptiveService — the SEL category level, readiness, and the journey snapshot.

The learner's level in a category is `learning_level_for` over the category's
mastered steps, counted by uid membership in the mastery map: uid strings are
opaque (ADR-013 never-sniff), so authored (`ku.mind.attention`) and generated
(`ku_labeling_a1b2c3d4`) uids count alike. The same count and the same readiness
predicate feed both the recommendations and the journey snapshot.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import LearningLevel, SELCategory
from core.models.pathways.mastery import LearningVelocity, Mastery, MasteryLevel
from core.models.pathways.path_step import PathStep
from core.models.user.user_intelligence import UserLearningIntelligence
from core.services.ps.ps_adaptive_service import PsAdaptiveService
from core.utils.result_simplified import Result


def make_mastery(knowledge_uid: str, sel_category: str | None) -> Mastery:
    """Minimal Mastery for level-determination fixtures."""
    now = datetime.now()
    return Mastery(
        uid=f"mastery_user_test_{knowledge_uid}",
        user_uid="user_test",
        knowledge_uid=knowledge_uid,
        sel_category=sel_category,
        mastery_level=MasteryLevel.PROFICIENT,
        confidence_score=0.8,
        mastery_score=0.7,
        learning_velocity=LearningVelocity.MODERATE,
        time_to_mastery_hours=None,
        review_frequency_days=None,
        mastery_evidence=[],
        last_reviewed=now,
        last_practiced=None,
        learning_path_context=None,
        difficulty_experienced=None,
        preferred_learning_method=None,
        created_at=now,
        updated_at=now,
    )


def make_intelligence(masteries: dict[str, Mastery]) -> UserLearningIntelligence:
    return UserLearningIntelligence(user_uid="user_test", current_masteries=masteries)


@pytest.fixture
def service() -> PsAdaptiveService:
    return PsAdaptiveService(backend=Mock(), user_service=Mock())


def _steps(uids: list[str]) -> list[PathStep]:
    return [PathStep(uid=uid, title=uid) for uid in uids]


class TestCategoryLevel:
    """`_category_level` counts the category's steps the learner has mastered — by
    uid membership in the mastery map, never by anything the uid string spells."""

    def test_authored_and_generated_uids_both_count(self, service: PsAdaptiveService) -> None:
        """None of these uids starts with ``ku.self_awareness``; a uid-prefix sniff
        would count 0 of them."""
        category = _steps(
            [
                "ku.mind.attention",
                "ku.yoga.breath",
                "ku.sel.body-scan",
                "ku_labeling_a1b2c3d4",
                "ku_noticing_e5f6a7b8",
                "ku.sel.unmastered",
            ]
        )
        masteries = {
            m.knowledge_uid: m
            for m in [make_mastery(ps.uid, SELCategory.SELF_AWARENESS.value) for ps in category[:5]]
            + [
                # Mastered, but not a step of THIS category — must not count.
                make_mastery("ku.sel.empathy", SELCategory.SOCIAL_AWARENESS.value),
            ]
        }

        level = service._category_level(make_intelligence(masteries), category)

        assert level == LearningLevel.INTERMEDIATE  # 5 mastered → >= 5

    def test_no_mastered_step_is_beginner(self, service: PsAdaptiveService) -> None:
        masteries = {
            m.knowledge_uid: m
            for m in [make_mastery("ku.sel.empathy", SELCategory.SOCIAL_AWARENESS.value)]
        }

        level = service._category_level(make_intelligence(masteries), _steps(["ku.sel.a"]))

        assert level == LearningLevel.BEGINNER

    def test_twelve_mastered_is_advanced(self, service: PsAdaptiveService) -> None:
        category = _steps([f"ku_concept-{i}_{i:08d}" for i in range(12)])
        masteries = {
            m.knowledge_uid: m
            for m in [make_mastery(ps.uid, SELCategory.SELF_MANAGEMENT.value) for ps in category]
        }

        level = service._category_level(make_intelligence(masteries), category)

        assert level == LearningLevel.ADVANCED


class TestQueryUserMasteriesCarriesSelCategory:
    @pytest.mark.asyncio
    async def test_sel_category_flows_from_backend_record_to_mastery(self) -> None:
        """The backend row's ``sel_category`` (the mastered node's field) lands
        on the Mastery model — the data path _determine_user_level counts on."""
        backend = Mock()
        backend.query_user_masteries = AsyncMock(
            return_value=Result.ok(
                [
                    {
                        "ku_uid": "ku.mind.attention",
                        "sel_category": SELCategory.SELF_AWARENESS.value,
                        "mastery_level": "proficient",
                        "learning_velocity": "moderate",
                    },
                    {
                        "ku_uid": "ku_labeling_a1b2c3d4",
                        "sel_category": None,
                        "mastery_level": "introduced",
                        "learning_velocity": "moderate",
                    },
                ]
            )
        )
        service = PsAdaptiveService(backend=backend, user_service=Mock())

        masteries = await service._query_user_masteries("user_test")

        assert masteries["ku.mind.attention"].sel_category == SELCategory.SELF_AWARENESS.value
        assert masteries["ku_labeling_a1b2c3d4"].sel_category is None


class TestSelJourneyCompletion:
    @pytest.mark.asyncio
    async def test_journey_completion_is_derived_from_mastered_over_total(self) -> None:
        """Two of four Self-Awareness steps mastered reads 50% for the category, 10%
        overall (one of five categories), ONE step available (s2: unmastered with its
        prerequisite mastered; s3 waits on s2 — the same readiness predicate the
        curriculum route applies), and the level the recommendation filter uses; the
        recommendation moves past the category. The counts are the ONLY input —
        nothing sets a percentage the service could forget."""
        steps = _steps([f"ps.sel.s{i}" for i in range(4)])

        async def find_by(**kwargs: str) -> Result[list[PathStep]]:
            if kwargs["sel_category"] == SELCategory.SELF_AWARENESS.value:
                return Result.ok(steps)
            return Result.ok([])

        backend = Mock()
        backend.find_by = find_by
        # s3 requires s2 (unmastered) — so it is NOT available; s2 requires s0 (mastered).
        backend.query_prerequisite_uids = AsyncMock(
            return_value=Result.ok({"ps.sel.s2": ["ps.sel.s0"], "ps.sel.s3": ["ps.sel.s2"]})
        )
        service = PsAdaptiveService(backend=backend, user_service=Mock())
        intel = make_intelligence(
            {
                "ps.sel.s0": make_mastery("ps.sel.s0", SELCategory.SELF_AWARENESS.value),
                "ps.sel.s1": make_mastery("ps.sel.s1", SELCategory.SELF_AWARENESS.value),
            }
        )
        service._load_user_intelligence = AsyncMock(return_value=intel)  # type: ignore[method-assign]

        result = await service.get_sel_journey("user_test")

        journey = result.value
        awareness = journey.category_progress[SELCategory.SELF_AWARENESS]
        assert (awareness.steps_mastered, awareness.total_steps) == (2, 4)
        assert awareness.steps_available == 1
        assert awareness.completion_percentage == 50.0
        assert awareness.current_level == service._category_level(intel, steps)
        # The prerequisite read is ONE round trip for the category, not one per step.
        assert backend.query_prerequisite_uids.await_count == 1
        assert journey.overall_completion == pytest.approx(10.0)
        assert journey.get_next_recommended_category() == SELCategory.SELF_MANAGEMENT

    def test_derived_fields_reach_the_json_boundary_and_refuse_a_constructor_value(self) -> None:
        """The JSON route serializes dataclass FIELDS, so the derived pair must be fields —
        and derived, so no constructor can hand them a value the counts disagree with."""
        from pydantic_core import to_jsonable_python

        from core.models.pathways.learning_progress import CurriculumProgress

        progress = CurriculumProgress(
            user_uid="user_test",
            sel_category=SELCategory.SELF_AWARENESS,
            steps_mastered=12,
            total_steps=16,
        )
        payload = to_jsonable_python(progress)
        assert payload["completion_percentage"] == 75.0
        assert payload["current_level"] == LearningLevel.ADVANCED.value
        with pytest.raises(TypeError):
            CurriculumProgress(  # type: ignore[call-arg]
                user_uid="user_test",
                sel_category=SELCategory.SELF_AWARENESS,
                completion_percentage=1.0,
            )
