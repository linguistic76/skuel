"""Unit tests for ``_PsValidator`` (Phase 4 — pure-function validator).

The validator runs six checks (not_active, target_missing, wrong_type,
self_reference, cross_ps, cycle). These tests exercise each one against synthetic
TemplateBundles — no Neo4j, no I/O, deterministic.

Integration tests covering the engage-spawn-complete-abandon round trip
require a Neo4j test fixture and live in tests/integration/ (deferred — see
the Phase 4 verification section of the plan).
"""

from __future__ import annotations

from core.models.enums.entity_enums import EntityStatus
from core.models.templates.choice_template import ChoiceTemplate
from core.models.templates.event_template import EventTemplate
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.habit_template import HabitTemplate
from core.models.templates.principle_template import PrincipleTemplate
from core.models.templates.task_template import TaskTemplate
from core.services.ps_engagement._template_bundle import TemplateBundle
from core.services.ps_engagement._validator import _PsValidator

_ACTIVE = EntityStatus.ACTIVE  # all test templates must be ACTIVE for non-status checks to run


def _empty_bundle(ps_uid: str = "ps_test") -> TemplateBundle:
    return TemplateBundle(
        ps_uid=ps_uid, tasks=(), goals=(), habits=(), events=(), choices=(), principles=()
    )


class TestEmptyBundle:
    def test_empty_bundle_has_no_violations(self) -> None:
        v = _PsValidator()
        assert v.validate(_empty_bundle()) == []


class TestTargetMissing:
    """Cross-template ref points to a UID not attached to this PS."""

    def test_task_fulfills_unknown_goal_template(self) -> None:
        v = _PsValidator()
        tt = TaskTemplate(
            uid="ttpl_t1",
            title="Practice",
            status=_ACTIVE,
            fulfills_goal_template_uid="gtpl_does_not_exist",
        )
        bundle = TemplateBundle(
            ps_uid="ps_x", tasks=(tt,), goals=(), habits=(), events=(), choices=(), principles=()
        )
        violations = v.validate(bundle)
        assert len(violations) == 1
        assert violations[0]["violation"] == "target_missing"
        assert violations[0]["field"] == "fulfills_goal_template_uid"
        assert violations[0]["referenced_uid"] == "gtpl_does_not_exist"
        assert violations[0]["template_type"] == "TaskTemplate"

    def test_goal_inspired_by_unknown_choice(self) -> None:
        v = _PsValidator()
        gt = GoalTemplate(
            uid="gtpl_g1",
            title="Master fundamentals",
            status=_ACTIVE,
            inspired_by_choice_template_uid="ctpl_missing",
        )
        bundle = TemplateBundle(
            ps_uid="ps_x", tasks=(), goals=(gt,), habits=(), events=(), choices=(), principles=()
        )
        violations = v.validate(bundle)
        assert len(violations) == 1
        assert violations[0]["violation"] == "target_missing"
        assert violations[0]["field"] == "inspired_by_choice_template_uid"


class TestWrongType:
    """Cross-template ref resolves to an attached template of the wrong type."""

    def test_task_fulfills_a_habit_not_a_goal(self) -> None:
        v = _PsValidator()
        ht = HabitTemplate(uid="htpl_morning", title="Morning routine", status=_ACTIVE)
        tt = TaskTemplate(
            uid="ttpl_x",
            title="Confused task",
            status=_ACTIVE,
            fulfills_goal_template_uid="htpl_morning",  # habit, not goal
        )
        bundle = TemplateBundle(
            ps_uid="ps_x",
            tasks=(tt,),
            goals=(),
            habits=(ht,),
            events=(),
            choices=(),
            principles=(),
        )
        violations = v.validate(bundle)
        assert len(violations) == 1
        assert violations[0]["violation"] == "wrong_type"
        assert violations[0]["field"] == "fulfills_goal_template_uid"
        assert "expected GoalTemplate, got HabitTemplate" in (violations[0]["hint"] or "")

    def test_event_milestone_for_a_choice_not_a_goal(self) -> None:
        v = _PsValidator()
        ct = ChoiceTemplate(uid="ctpl_path", title="Pick a path", status=_ACTIVE)
        et = EventTemplate(
            uid="etpl_party",
            title="Celebration",
            status=_ACTIVE,
            milestone_celebration_for_goal_template_uid="ctpl_path",
        )
        bundle = TemplateBundle(
            ps_uid="ps_x",
            tasks=(),
            goals=(),
            habits=(),
            events=(et,),
            choices=(ct,),
            principles=(),
        )
        violations = v.validate(bundle)
        assert len(violations) == 1
        assert violations[0]["violation"] == "wrong_type"


class TestSelfReference:
    def test_task_parent_is_itself(self) -> None:
        v = _PsValidator()
        tt = TaskTemplate(
            uid="ttpl_selfish",
            title="Self-referential",
            status=_ACTIVE,
            parent_template_uid="ttpl_selfish",
        )
        bundle = TemplateBundle(
            ps_uid="ps_x",
            tasks=(tt,),
            goals=(),
            habits=(),
            events=(),
            choices=(),
            principles=(),
        )
        violations = v.validate(bundle)
        # Self-ref takes priority and short-circuits the type check.
        assert any(x["violation"] == "self_reference" for x in violations)


class TestCycleDetection:
    """Task parent_template_uid chains can form cycles."""

    def test_two_node_cycle(self) -> None:
        v = _PsValidator()
        a = TaskTemplate(uid="ttpl_a", title="A", status=_ACTIVE, parent_template_uid="ttpl_b")
        b = TaskTemplate(uid="ttpl_b", title="B", status=_ACTIVE, parent_template_uid="ttpl_a")
        bundle = TemplateBundle(
            ps_uid="ps_x",
            tasks=(a, b),
            goals=(),
            habits=(),
            events=(),
            choices=(),
            principles=(),
        )
        violations = v.validate(bundle)
        cycle_violations = [x for x in violations if x["violation"] == "cycle"]
        assert {x["template_uid"] for x in cycle_violations} == {"ttpl_a", "ttpl_b"}

    def test_no_cycle_when_chain_terminates(self) -> None:
        v = _PsValidator()
        root = TaskTemplate(uid="ttpl_root", title="Root", parent_template_uid=None)
        child = TaskTemplate(uid="ttpl_child", title="Child", parent_template_uid="ttpl_root")
        bundle = TemplateBundle(
            ps_uid="ps_x",
            tasks=(root, child),
            goals=(),
            habits=(),
            events=(),
            choices=(),
            principles=(),
        )
        cycle = [x for x in v.validate(bundle) if x["violation"] == "cycle"]
        assert cycle == []


class TestAllValid:
    """Realistic PS bundle with valid cross-refs across all 6 domains."""

    def test_full_bundle_no_violations(self) -> None:
        v = _PsValidator()
        ct = ChoiceTemplate(uid="ctpl_pick", title="Pick a path", status=_ACTIVE)
        ht = HabitTemplate(uid="htpl_daily", title="Daily practice", status=_ACTIVE)
        pt = PrincipleTemplate(uid="ptpl_mantra", title="Mantra", status=_ACTIVE)
        gt = GoalTemplate(
            uid="gtpl_goal",
            title="Reach mastery",
            status=_ACTIVE,
            inspired_by_choice_template_uid="ctpl_pick",
        )
        et = EventTemplate(
            uid="etpl_check",
            title="Checkpoint",
            status=_ACTIVE,
            reinforces_habit_template_uid="htpl_daily",
            milestone_celebration_for_goal_template_uid="gtpl_goal",
        )
        tt = TaskTemplate(
            uid="ttpl_task",
            title="Task",
            status=_ACTIVE,
            fulfills_goal_template_uid="gtpl_goal",
            reinforces_habit_template_uid="htpl_daily",
            scheduled_event_template_uid="etpl_check",
        )
        bundle = TemplateBundle(
            ps_uid="ps_realistic",
            tasks=(tt,),
            goals=(gt,),
            habits=(ht,),
            events=(et,),
            choices=(ct,),
            principles=(pt,),
        )
        assert v.validate(bundle) == []


class TestErrorReportShape:
    """Ensure the result wraps cleanly into Errors.ps_validation_report."""

    def test_violations_pack_into_error_context(self) -> None:
        from core.utils.result_simplified import ErrorCategory, Errors

        v = _PsValidator()
        tt = TaskTemplate(
            uid="ttpl_broken",
            title="Bad",
            fulfills_goal_template_uid="gtpl_nope",
        )
        bundle = TemplateBundle(
            ps_uid="ps_x",
            tasks=(tt,),
            goals=(),
            habits=(),
            events=(),
            choices=(),
            principles=(),
        )
        violations = v.validate(bundle)
        ctx = Errors.ps_validation_report(violations)
        assert ctx.category == ErrorCategory.BUSINESS
        assert ctx.code == "BUSINESS_PS_TEMPLATE_VALIDATION"
        assert ctx.details["violations"] == violations
