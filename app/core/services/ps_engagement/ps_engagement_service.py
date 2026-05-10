"""PsEngagementService — facade for the 4-transition lifecycle.

Phase 4 of the PathStep + Activity Templates build (see plan at
``/home/mike/.claude/plans/skip-when-do-idempotent-shell.md``).

Surface (matches the contract in project_pathstep_lifecycle_contract.md):

    publish_pathstep(ps_uid)             -> Result[PathStep]    # T1
    engage_pathstep(student, ps)         -> Result[Engagement]  # T2
    complete_pathstep(student, ps, rev)  -> Result[Engagement]  # T3
    abandon_pathstep(student, ps)        -> Result[Engagement]  # T4

Concrete facade pattern (per CLAUDE.md "Facade IS the contract"):
the class itself is the route-facing type — no parallel protocol.

Invariants enforced:
- T1 fails fast if any template's cross-template references are broken
  (returns ``Errors.ps_validation_report`` with a typed ``list[Violation]``).
- T2 refuses if an active engagement already exists for (student, PS).
- T2 spawns transactionally — partial spawn is rolled back on failure.
- T3 marks kept instances ``engagement_state="owned"`` and deletes discarded
  ones; engagement edge transitions to ``state="completed"``.
- T4 deletes all spawned instances (engaged or owned-by-this-engagement);
  engagement edge transitions to ``state="abandoned"`` (preserved for audit).

Completion trigger (decision pinned 2026-05-09): student-declared only for
V1. Mastery-based auto-completion is deferred to a later phase.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from core.models.choice.choice import Choice
from core.models.enums import EntityStatus
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.habit.habit import Habit
from core.models.principle.principle import Principle
from core.models.task.task import Task
from core.models.templates.choice_template import ChoiceTemplate
from core.models.templates.event_template import EventTemplate
from core.models.templates.goal_template import GoalTemplate
from core.models.templates.habit_template import HabitTemplate
from core.models.templates.principle_template import PrincipleTemplate
from core.models.templates.task_template import TaskTemplate
from core.ports import CrudOperations
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

from ._engagement_gateway import _EngagementGateway
from ._spawn_orchestrator import ActivityBackends, _SpawnOrchestrator
from ._template_loader import _TemplateLoader
from ._validator import TemplateBundle, _PsValidator
from .engagement import Engagement

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.models.pathways.path_step import PathStep

logger = get_logger(__name__)


ReviewDecision = Literal["keep", "discard"]
"""Per-template student decision passed to ``complete_pathstep``.

Keys are template UIDs (the originals authored on the PS), values are the
student's keep/discard call.
"""


class PsEngagementService:
    """Concrete facade — coordinates validator, loader, spawn, gateway, ps_service."""

    def __init__(
        self,
        executor: Neo4jQueryExecutor,
        ps_service: Any,
        task_template_backend: CrudOperations[TaskTemplate],
        goal_template_backend: CrudOperations[GoalTemplate],
        habit_template_backend: CrudOperations[HabitTemplate],
        event_template_backend: CrudOperations[EventTemplate],
        choice_template_backend: CrudOperations[ChoiceTemplate],
        principle_template_backend: CrudOperations[PrincipleTemplate],
        tasks_backend: CrudOperations[Task],
        goals_backend: CrudOperations[Goal],
        habits_backend: CrudOperations[Habit],
        events_backend: CrudOperations[Event],
        choices_backend: CrudOperations[Choice],
        principles_backend: CrudOperations[Principle],
    ) -> None:
        if executor is None or ps_service is None:
            raise ValueError(
                "PsEngagementService requires both executor and ps_service "
                "(SKUEL fail-fast — no graceful degradation)."
            )
        self._executor = executor
        self._ps_service = ps_service

        self._validator = _PsValidator()
        self._loader = _TemplateLoader(
            executor=executor,
            task_template_backend=task_template_backend,
            goal_template_backend=goal_template_backend,
            habit_template_backend=habit_template_backend,
            event_template_backend=event_template_backend,
            choice_template_backend=choice_template_backend,
            principle_template_backend=principle_template_backend,
        )
        self._instance_backends = ActivityBackends(
            tasks=tasks_backend,
            goals=goals_backend,
            habits=habits_backend,
            events=events_backend,
            choices=choices_backend,
            principles=principles_backend,
        )
        self._orchestrator = _SpawnOrchestrator(self._instance_backends)
        self._gateway = _EngagementGateway(executor)
        self.logger = logger
        logger.debug("PsEngagementService initialized (Phase 4)")

    # ========================================================================
    # T1 — Publish
    # ========================================================================

    async def publish_pathstep(self, ps_uid: str) -> Result[PathStep]:
        """Validate the PS's templates and mark it published.

        Free-order authoring + deferred validation: refs may have been left
        unresolved during draft. Save-time validation produces the structured
        ``list[Violation]`` rendered by ``Errors.ps_validation_report``.
        """
        bundle_res = await self._loader.load(ps_uid)
        if bundle_res.is_error:
            return Result.fail(bundle_res)

        violations = self._validator.validate(bundle_res.value)
        if violations:
            return Result.fail(Errors.ps_validation_report(violations))

        # Validation passed — flip the status to PUBLISHED.
        from core.models.enums.learning_enums import KnowledgeStatus

        # PsService exposes update via .core.update; we use the executor for
        # a focused single-property update so we don't tug on the full PS
        # update validation path.
        update_res: Result[list[dict[str, Any]]] = await self._executor.execute_write(
            query="""
            MATCH (ps {uid: $uid})
            SET ps.status = $status,
                ps.updated_at = $updated_at
            RETURN ps
            """,
            params={
                "uid": ps_uid,
                "status": KnowledgeStatus.PUBLISHED.value,
                "updated_at": datetime.now(UTC).isoformat(),
            },
            operation="publish_pathstep",
        )
        if update_res.is_error:
            return Result.fail(update_res)
        if not update_res.value:
            return Result.fail(Errors.not_found("PathStep", ps_uid))

        # Hand back the freshly-loaded PathStep model.
        ps_res = await self._ps_service.core.get(ps_uid)
        if ps_res.is_error:
            return Result.fail(ps_res)
        return Result.ok(ps_res.value)

    # ========================================================================
    # T2 — Engage
    # ========================================================================

    async def engage_pathstep(self, student_uid: str, ps_uid: str) -> Result[Engagement]:
        """Spawn instances and open the engagement edge.

        Steps:
            1. Refuse if (student, PS) already has an active engagement.
            2. Re-validate the PS (defensive — templates may have changed
               since publish).
            3. Open the engagement edge → use its ``since`` as the spawn anchor.
            4. Spawn all instances via the 4-layer orchestrator.
            5. On spawn failure: roll back the engagement edge.
        """
        active = await self._gateway.find_active(student_uid, ps_uid)
        if active.is_error:
            return Result.fail(active)
        if active.value is not None:
            return Result.fail(
                Errors.business(
                    rule="engagement_already_active",
                    message=(
                        f"User {student_uid} already has an active engagement "
                        f"with PathStep {ps_uid}."
                    ),
                )
            )

        bundle_res = await self._loader.load(ps_uid)
        if bundle_res.is_error:
            return Result.fail(bundle_res)
        bundle = bundle_res.value

        violations = self._validator.validate(bundle)
        if violations:
            return Result.fail(Errors.ps_validation_report(violations))

        if _bundle_is_empty(bundle):
            return Result.fail(
                Errors.business(
                    rule="empty_pathstep",
                    message=(
                        f"PathStep {ps_uid} has no Activity Templates attached — "
                        "nothing to engage with."
                    ),
                )
            )

        engagement_res = await self._gateway.open_engagement(student_uid, ps_uid)
        if engagement_res.is_error:
            return Result.fail(engagement_res)
        engagement = engagement_res.value

        spawn_res = await self._orchestrator.spawn(
            student_uid=student_uid,
            ps_uid=ps_uid,
            bundle=bundle,
            engagement_anchor=engagement.since,
        )
        if spawn_res.is_error:
            # Roll back the engagement edge — orchestrator already rolled back
            # any partially-created instances.
            rollback = await self._gateway.mark_abandoned(student_uid, ps_uid)
            if rollback.is_error:
                self.logger.error(
                    f"Spawn failed AND engagement-edge rollback failed for "
                    f"student={student_uid} ps={ps_uid} — manual cleanup needed"
                )
            return Result.fail(spawn_res)

        spawn_result = spawn_res.value
        return Result.ok(
            Engagement(
                student_uid=engagement.student_uid,
                ps_uid=engagement.ps_uid,
                state=engagement.state,
                since=engagement.since,
                completed_at=engagement.completed_at,
                abandoned_at=engagement.abandoned_at,
                spawned_instance_uids=tuple(spawn_result.instance_uids),
            )
        )

    # ========================================================================
    # T3 — Complete
    # ========================================================================

    async def complete_pathstep(
        self,
        student_uid: str,
        ps_uid: str,
        review: dict[str, ReviewDecision],
    ) -> Result[Engagement]:
        """Apply the student's keep/discard review and close the engagement.

        ``review`` keys are template UIDs (as authored on the PS). Spawned
        instances whose ``template_uid`` maps to ``"keep"`` transition to
        ``engagement_state="owned"``; instances mapped to ``"discard"`` are
        deleted. Templates not present in ``review`` default to ``"keep"``
        (forgiving — the student didn't object).
        """
        active = await self._gateway.find_active(student_uid, ps_uid)
        if active.is_error:
            return Result.fail(active)
        if active.value is None:
            return Result.fail(
                Errors.not_found(
                    "active engagement",
                    f"student={student_uid} ps={ps_uid}",
                )
            )

        # Find spawned instances by querying for engaged-state instances that
        # carry a template_uid matching one attached to this PS. See orchestrator
        # docstring for the rationale (only one active engagement at a time).
        spawned = await self._fetch_engaged_instances(student_uid, ps_uid)
        if spawned.is_error:
            return Result.fail(spawned)

        for template_uid, instance_uid, _label in spawned.value:
            decision = review.get(template_uid, "keep")
            if decision == "discard":
                del_res: Result[list[dict[str, Any]]] = await self._executor.execute_write(
                    query="MATCH (n {uid: $uid}) DETACH DELETE n",
                    params={"uid": instance_uid},
                    operation="discard_instance",
                )
                if del_res.is_error:
                    return Result.fail(del_res)
            else:
                upd_res: Result[list[dict[str, Any]]] = await self._executor.execute_write(
                    query="""
                    MATCH (n {uid: $uid})
                    SET n.engagement_state = 'owned',
                        n.updated_at = $updated_at
                    RETURN n.uid AS uid
                    """,
                    params={
                        "uid": instance_uid,
                        "updated_at": datetime.now(UTC).isoformat(),
                    },
                    operation="own_instance",
                )
                if upd_res.is_error:
                    return Result.fail(upd_res)

        return await self._gateway.mark_completed(student_uid, ps_uid)

    # ========================================================================
    # T4 — Abandon
    # ========================================================================

    async def abandon_pathstep(self, student_uid: str, ps_uid: str) -> Result[Engagement]:
        """Delete all instances spawned by this engagement and mark abandoned.

        Per the lifecycle contract: the engagement edge is preserved with
        state='abandoned' for audit, but every spawned instance is removed
        regardless of engaged-vs-owned state (the student is walking away
        from the whole engagement, not just the unfinished parts).
        """
        active = await self._gateway.find_active(student_uid, ps_uid)
        if active.is_error:
            return Result.fail(active)
        if active.value is None:
            return Result.fail(
                Errors.not_found(
                    "active engagement",
                    f"student={student_uid} ps={ps_uid}",
                )
            )

        # Delete all instances belonging to this engagement — both engaged AND
        # owned, since 'owned' instances spawned by THIS engagement edge
        # haven't yet outlived it.
        spawned = await self._fetch_engaged_instances(student_uid, ps_uid)
        if spawned.is_error:
            return Result.fail(spawned)
        for _template_uid, instance_uid, _label in spawned.value:
            del_res: Result[list[dict[str, Any]]] = await self._executor.execute_write(
                query="MATCH (n {uid: $uid}) DETACH DELETE n",
                params={"uid": instance_uid},
                operation="abandon_instance",
            )
            if del_res.is_error:
                return Result.fail(del_res)

        return await self._gateway.mark_abandoned(student_uid, ps_uid)

    # ========================================================================
    # Read — engagement edge lookup
    # ========================================================================

    async def find_active(
        self, student_uid: str, ps_uid: str
    ) -> Result[Engagement | None]:
        """Read-only access to the active engagement edge, if any.

        Returns the Engagement when ``ENGAGED_WITH`` exists for (student, ps),
        otherwise ``Result.ok(None)``. Used by Askesis to bias bundle context
        toward engaged PathSteps without bringing the gateway into a public API.
        """
        return await self._gateway.find_active(student_uid, ps_uid)

    # ========================================================================
    # Internal — instance discovery
    # ========================================================================

    async def _fetch_engaged_instances(
        self, student_uid: str, ps_uid: str
    ) -> Result[list[tuple[str, str, str]]]:
        """Return [(template_uid, instance_uid, neo_label), ...] for this engagement.

        Defining "this engagement's instances" as: instances owned by this
        student whose ``template_uid`` is a template currently attached to
        this PS. Safe because the at-most-one-active invariant ensures the
        only engaged instances belong to the current engagement.
        """
        query = """
        MATCH (ps {uid: $ps_uid})-[:HAS_TASK_TEMPLATE
                                   |HAS_GOAL_TEMPLATE
                                   |HAS_HABIT_TEMPLATE
                                   |HAS_EVENT_TEMPLATE
                                   |HAS_CHOICE_TEMPLATE
                                   |HAS_PRINCIPLE_TEMPLATE]->(t)
        MATCH (n {user_uid: $student_uid, template_uid: t.uid})
        WHERE n.engagement_state IN ['engaged', 'owned']
        RETURN t.uid AS template_uid, n.uid AS instance_uid, labels(n) AS labels
        """
        res: Result[list[dict[str, Any]]] = await self._executor.execute(
            query=query,
            params={"student_uid": student_uid, "ps_uid": ps_uid},
            operation="fetch_engaged_instances",
        )
        if res.is_error:
            return Result.fail(res)
        out: list[tuple[str, str, str]] = []
        for record in res.value:
            labels = record.get("labels") or []
            domain_label = next(
                (lab for lab in labels if lab != "Entity"), labels[0] if labels else "Entity"
            )
            out.append((record["template_uid"], record["instance_uid"], domain_label))
        return Result.ok(out)


def _bundle_is_empty(bundle: TemplateBundle) -> bool:
    return not (
        bundle.tasks
        or bundle.goals
        or bundle.habits
        or bundle.events
        or bundle.choices
        or bundle.principles
    )


# Re-exported so ``from core.services.ps_engagement.ps_engagement_service import EntityStatus``
# works in tests if needed.
__all__ = ["EntityStatus", "PsEngagementService", "ReviewDecision"]
