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

Completion triggers (decision pinned 2026-05-11): two paths.
- Student-declared via ``complete_pathstep`` with an explicit keep/discard
  review (the original V1 path).
- Auto-completion via ``check_auto_complete`` when all engaged siblings reach
  engagement-terminal status. Subscribed to TaskCompleted / GoalAchieved /
  CalendarEventCompleted / ChoiceMade (see ``_auto_completion_handler``).
  Equivalent to ``complete_pathstep`` with an empty review — auto-keep all.
  Mastery-based auto-completion remains deferred.
"""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, kw_only=True)
class ReviewItem:
    """One row's worth of data for the completion review screen.

    Per the contract pinned 2026-05-11, the review is keyed by ``template_uid``
    (one decision applies to every instance sharing that template, even if a
    future spawn fans 1→N). ``instance_uid`` is a representative used by the
    UI to look up additional details; ``label`` is the activity-domain Neo4j
    label (``Task``, ``Habit``, …) for badge rendering.
    """

    template_uid: str
    instance_uid: str
    label: str
    title: str


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
    # T3 (auto) — Auto-complete when all engaged siblings reach terminal
    # ========================================================================

    async def check_auto_complete(
        self, student_uid: str, instance_uid: str
    ) -> Result[Engagement | None]:
        """If this instance is part of an active engagement and *all* its
        engaged siblings are now engagement-terminal, auto-complete the
        engagement with an empty review (auto-keep all).

        Returns:
            ``Result.ok(None)`` — instance isn't part of an active engagement,
                or some siblings are still pending.
            ``Result.ok(Engagement)`` — auto-completion fired; the resulting
                completed Engagement.
            ``Result.fail(...)`` — propagates query or completion errors.

        Idempotent: completion edges are filtered by ``state='engaged'``, so
        re-firing after the edge has transitioned is a no-op (returns None).

        Per ``_terminal_status_rules``: Principles never block, Habits and
        Principles never trigger (no clean entity-terminal event to subscribe
        to). The 4 subscribed trigger events are ``TaskCompleted``,
        ``GoalAchieved``, ``CalendarEventCompleted``, ``ChoiceMade``.
        """
        from core.models.enums.entity_enums import EntityStatus, EntityType

        from ._terminal_status_rules import is_engagement_terminal

        # One query: anchor on the just-changed instance, walk to its PS, find
        # all sibling instances still in engagement_state='engaged' under an
        # ACTIVE engagement edge.
        query = """
        MATCH (n {uid: $instance_uid, user_uid: $student_uid})
        WHERE n.template_uid IS NOT NULL
          AND n.engagement_state = 'engaged'
        MATCH (t {uid: n.template_uid})
        MATCH (ps)-[:HAS_TASK_TEMPLATE
                    |HAS_GOAL_TEMPLATE
                    |HAS_HABIT_TEMPLATE
                    |HAS_EVENT_TEMPLATE
                    |HAS_CHOICE_TEMPLATE
                    |HAS_PRINCIPLE_TEMPLATE]->(t)
        MATCH (u:User {uid: $student_uid})-[e:ENGAGED_WITH]->(ps)
        WHERE e.state = 'engaged'
        WITH ps
        MATCH (ps)-[:HAS_TASK_TEMPLATE
                    |HAS_GOAL_TEMPLATE
                    |HAS_HABIT_TEMPLATE
                    |HAS_EVENT_TEMPLATE
                    |HAS_CHOICE_TEMPLATE
                    |HAS_PRINCIPLE_TEMPLATE]->(other_t)
        MATCH (other_n {template_uid: other_t.uid, user_uid: $student_uid})
        WHERE other_n.engagement_state = 'engaged'
        RETURN ps.uid AS ps_uid,
               collect({
                 entity_type: other_n.entity_type,
                 status: other_n.status
               }) AS siblings
        LIMIT 1
        """
        res: Result[list[dict[str, Any]]] = await self._executor.execute(
            query=query,
            params={"student_uid": student_uid, "instance_uid": instance_uid},
            operation="check_auto_complete",
        )
        if res.is_error:
            return Result.fail(res)
        if not res.value:
            # Instance isn't part of any active engagement (or template_uid is null,
            # or engagement_state isn't 'engaged'). Nothing to do.
            return Result.ok(None)

        row = res.value[0]
        ps_uid = row["ps_uid"]
        siblings = row.get("siblings") or []

        for sibling in siblings:
            try:
                et = EntityType(sibling["entity_type"])
                st = EntityStatus(sibling["status"])
            except (KeyError, ValueError) as exc:
                # Defensive: malformed property — skip auto-complete, let the
                # student declare. Not a hard failure of the calling event.
                self.logger.warning(
                    f"check_auto_complete skipping malformed sibling "
                    f"(student={student_uid}, ps={ps_uid}): {exc}"
                )
                return Result.ok(None)
            if not is_engagement_terminal(et, st):
                # Something still pending — don't fire.
                return Result.ok(None)

        # All siblings terminal → auto-complete with empty review (keep all).
        completed = await self.complete_pathstep(student_uid, ps_uid, review={})
        if completed.is_error:
            return Result.fail(completed)
        self.logger.info(
            f"Auto-completed engagement: student={student_uid} ps={ps_uid} "
            f"({len(siblings)} instances kept)"
        )
        return Result.ok(completed.value)

    # ========================================================================
    # Read — engagement edge lookup
    # ========================================================================

    async def find_active(self, student_uid: str, ps_uid: str) -> Result[Engagement | None]:
        """Read-only access to the active engagement edge, if any.

        Returns the Engagement when ``ENGAGED_WITH`` exists for (student, ps),
        otherwise ``Result.ok(None)``. Used by Askesis to bias bundle context
        toward engaged PathSteps without bringing the gateway into a public API.
        """
        return await self._gateway.find_active(student_uid, ps_uid)

    async def list_review_items(self, student_uid: str, ps_uid: str) -> Result[list[ReviewItem]]:
        """Rich per-instance rows for the completion review screen.

        Returns one ``ReviewItem`` per spawned instance currently in
        ``engagement_state IN ['engaged', 'owned']`` for this (student, PS).
        Mirrors ``_fetch_engaged_instances`` but also pulls ``title`` so the
        UI can render meaningful rows without a second round-trip.
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
        RETURN t.uid          AS template_uid,
               n.uid           AS instance_uid,
               labels(n)       AS labels,
               coalesce(n.title, n.uid) AS title
        """
        res: Result[list[dict[str, Any]]] = await self._executor.execute(
            query=query,
            params={"student_uid": student_uid, "ps_uid": ps_uid},
            operation="list_review_items",
        )
        if res.is_error:
            return Result.fail(res)
        out: list[ReviewItem] = []
        for record in res.value:
            labels = record.get("labels") or []
            domain_label = next(
                (lab for lab in labels if lab != "Entity"),
                labels[0] if labels else "Entity",
            )
            out.append(
                ReviewItem(
                    template_uid=str(record["template_uid"]),
                    instance_uid=str(record["instance_uid"]),
                    label=str(domain_label),
                    title=str(record["title"]),
                )
            )
        return Result.ok(out)

    async def list_engaged(self, student_uid: str) -> Result[list[Engagement]]:
        """Return all active engagements for a student, with spawned instance UIDs.

        For each ``state='engaged'`` edge, fetches the activity instances spawned
        by that engagement (via ``template_uid`` join against templates attached
        to the PS) and populates ``Engagement.spawned_instance_uids``.

        Called by ``UserContextBuilder.build_rich_user_context`` to populate
        ``RichUserContext.active_ps_engagements``; ``DailyPlanningMixin`` then
        reads that field to bucket the daily plan by originating PS (ADR-059).
        """
        from dataclasses import replace

        listed = await self._gateway.list_engaged(student_uid)
        if listed.is_error:
            return Result.fail(listed)

        enriched: list[Engagement] = []
        for engagement in listed.value:
            instances = await self._fetch_engaged_instances(student_uid, engagement.ps_uid)
            if instances.is_error:
                return Result.fail(instances)
            instance_uids = tuple(uid for _t, uid, _l in instances.value)
            enriched.append(replace(engagement, spawned_instance_uids=instance_uids))
        return Result.ok(enriched)

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
