"""
Learning Intelligence Mixin
============================

Methods 1-4 of UserContextIntelligence:
1. get_optimal_next_path_steps() - What should I learn next?
2. get_learning_path_critical_path() - Fastest route to life path?
3. get_knowledge_application_opportunities() - Where can I apply this?
4. get_unblocking_priority_order() - What unlocks the most?

These methods synthesize KU, Goals, Tasks, and Context to determine
optimal learning priorities.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING, Any

from core.constants import LearningTimeEstimate, NextStepRanking
from core.models.context_types import PathStep
from core.models.enums.entity_enums import EntityStatus
from core.services.user.intelligence._base import IntelligenceMixinBase
from core.services.user.rich_context import find_rich_entity_item
from core.utils.neo4j_temporal import convert_neo4j_time
from core.utils.result_simplified import Result
from core.utils.sort_functions import get_priority_score
from core.utils.timestamp_helpers import day_of, parse_stamp, wall_clock_in
from core.utils.zone_context import current_zone

if TYPE_CHECKING:
    from core.models.context_types import ContextualKnowledge
    from core.models.zpd.zpd_assessment import ZPDAction, ZPDAssessment


def _action_priority(action: ZPDAction) -> float:
    return action.priority


class LearningIntelligenceMixin(IntelligenceMixinBase):
    """
    Mixin providing learning intelligence methods.

    Requires self.context (UserContext) and self.tasks, self.ps (relationship services).
    Optional: self.vector_search (Neo4jVectorSearchService) for semantic/learning-aware search.
    Optional: self.zpd_service (ZPDOperations) for curriculum-graph-aware step ranking.
    """

    # =========================================================================
    # METHOD 1: Optimal Next Learning Steps
    # =========================================================================

    async def get_optimal_next_path_steps(
        self,
        max_steps: int = 5,
        consider_goals: bool = True,
        consider_capacity: bool = True,
    ) -> Result[list[PathStep]]:
        """
        THE CORE METHOD - determine what to learn next based on ALL factors.

        **Priority order:**
        1. ZPDService (when wired): curriculum-graph-aware ranking via proximal zone +
           readiness scores. Returns immediately when assessment is non-empty.
        2. Learning-aware vector search (when available): semantic/mastery-boosted results.
        3. KU relationship service: prerequisite-aware candidates.
        4. Context fallback: ready_to_learn UIDs from UserContext.

        Each source scores its own candidates (readiness, learning state, life path
        alignment, unblocking potential — read the source). The two flags then mean the
        same thing whichever source answered; ``_rank_steps`` is the one place they act.

        Args:
            max_steps: Maximum number of steps to return
            consider_goals: Weight by goal alignment. On, each goal a step serves adds
                ``NextStepRanking.GOAL_WEIGHT_PER_GOAL`` to its ``priority_score``, up to
                ``GOAL_WEIGHT_MAX``, and the weight lifts a score no higher than 1.0. Off,
                goal alignment adds nothing to a score and moves no step.
                ``aligns_with_goals`` and the rationale name the goals either way — they
                are information, not ranking.
            consider_capacity: Respect user capacity limits. On, the returned steps fit
                ``context.available_minutes_daily`` together: walking the ranking, a step
                is kept when its ``estimated_time_minutes`` fits in what is left of the
                day. Off, no step is dropped or scored for time.

        Returns:
            Result[list[PathStep]] in descending ``priority_score`` order
        """
        # ── ZPD path (highest priority when available) ─────────────────────────
        if self.zpd_service is not None:
            assessment_result = await self.zpd_service.assess_zone(self.context.user_uid)
            if not assessment_result.is_error:
                assessment = assessment_result.value
                if not assessment.is_empty():
                    return await self._rank_by_zpd(
                        assessment, max_steps, consider_goals, consider_capacity
                    )

        # ── Activity-based path (fallback) ──────────────────────────────────────
        return await self._rank_by_activity(max_steps, consider_goals, consider_capacity)

    async def _rank_by_zpd(
        self,
        assessment: ZPDAssessment,
        max_steps: int,
        consider_goals: bool,
        consider_capacity: bool,
    ) -> Result[list[PathStep]]:
        """Rank path steps using ZPD proximal zone, readiness scores, and evidence.

        Uses ZPDAssessment.top_proximal_ku_uids() to get candidates, then enriches
        each with application opportunities, goal alignment, unblocking counts,
        life path alignment, and zone evidence confidence.

        See: core/models/zpd/zpd_assessment.py — ZPDAssessment
        """
        # If recommended_actions are pre-computed, use them directly
        if assessment.recommended_actions:
            learn_actions = sorted(
                [a for a in assessment.recommended_actions if a.action_type == "learn"],
                key=_action_priority,
                reverse=True,
            )
            if learn_actions:
                path_steps = []
                for action in learn_actions[: max_steps * 2]:
                    ku_uid: str = action.entity_uid
                    applications_result = await self._get_application_opportunities_for_ku(ku_uid)
                    if applications_result.is_error:
                        return Result.fail(applications_result)
                    applications = applications_result.value
                    unlocks_count = self._count_items_unlocked_by(ku_uid)
                    aligned_goals = self._find_aligned_goals(ku_uid)
                    readiness_score = assessment.readiness_scores.get(ku_uid, 0.0)

                    step = PathStep(
                        ku_uid=ku_uid,
                        title=f"Knowledge Unit {ku_uid}",
                        rationale=action.rationale,
                        prerequisites_met=readiness_score >= 1.0,
                        aligns_with_goals=tuple(aligned_goals),
                        unlocks_count=unlocks_count,
                        estimated_time_minutes=self.context.estimated_minutes(
                            ku_uid, LearningTimeEstimate.NEXT_STEP_MINUTES
                        ),
                        priority_score=action.priority,
                        application_opportunities={k: tuple(v) for k, v in applications.items()},
                    )
                    path_steps.append(step)

                return Result.ok(
                    self._rank_steps(path_steps, max_steps, consider_goals, consider_capacity)
                )

        proximal_uids = assessment.top_proximal_ku_uids(max_steps * 2)
        if not proximal_uids:
            # ZPD produced an assessment but proximal zone is empty — use activity path
            return await self._rank_by_activity(max_steps, consider_goals, consider_capacity)

        path_steps = []
        for ku_uid in proximal_uids:
            readiness_score = assessment.readiness_scores.get(ku_uid, 0.0)
            # Priority formula: readiness * 0.5 + life_path * 0.3 + behavioral * 0.2
            priority_score = round(
                readiness_score * 0.5
                + assessment.life_path_alignment * 0.3
                + assessment.behavioral_readiness * 0.2,
                3,
            )

            # Compound evidence on THIS unit (2+ signal types) lifts its priority.
            # Its prerequisites' confirmation is already in readiness_score — the
            # ZPD computes readiness from the prerequisite DAG — so no second
            # prerequisite term is added here.
            evidence = assessment.zone_evidence.get(ku_uid)
            if evidence and evidence.is_confirmed:
                priority_score = min(1.0, priority_score + 0.05)

            applications_result = await self._get_application_opportunities_for_ku(ku_uid)
            if applications_result.is_error:
                return Result.fail(applications_result)
            applications = applications_result.value
            unlocks_count = self._count_items_unlocked_by(ku_uid)
            aligned_goals = self._find_aligned_goals(ku_uid)

            step = PathStep(
                ku_uid=ku_uid,
                title=f"Knowledge Unit {ku_uid}",
                rationale=self._generate_learning_rationale(
                    ku_uid, aligned_goals, unlocks_count, applications
                ),
                prerequisites_met=readiness_score >= 1.0,
                aligns_with_goals=tuple(aligned_goals),
                unlocks_count=unlocks_count,
                estimated_time_minutes=self.context.estimated_minutes(
                    ku_uid, LearningTimeEstimate.NEXT_STEP_MINUTES
                ),
                priority_score=priority_score,
                application_opportunities={k: tuple(v) for k, v in applications.items()},
            )
            path_steps.append(step)

        return Result.ok(self._rank_steps(path_steps, max_steps, consider_goals, consider_capacity))

    async def _rank_by_activity(
        self,
        max_steps: int,
        consider_goals: bool,
        consider_capacity: bool,
    ) -> Result[list[PathStep]]:
        """Activity-based path step ranking.

        Tries vector search → ``ps`` service → context fallback, in that order.
        """
        # Try learning-aware search first (if available)
        if self.vector_search and getattr(self.vector_search, "learning_aware_search", None):
            # Use semantic/learning-aware search to find optimal next steps
            # This personalizes based on mastery state (MASTERED, IN_PROGRESS, etc.)
            search_query = self._generate_learning_query()
            vector_result = await self.vector_search.learning_aware_search(
                label="Entity",
                text=search_query,
                user_uid=self.context.user_uid,
                prefer_unmastered=True,
                limit=max_steps * 2,
            )

            if vector_result.is_ok and vector_result.value:
                # Convert vector results to path steps
                return await self._vector_results_to_path_steps(
                    vector_result.value, max_steps, consider_goals, consider_capacity
                )

        # Fallback: Get knowledge ready to learn from KU relationship service
        ready_result = await self.ps.get_ready_to_learn_for_user(self.context, limit=max_steps * 2)

        if ready_result.is_error or not ready_result.value:
            # Fall back to context-based approach
            return Result.ok(
                self._rank_steps(
                    self._get_path_steps_from_context(max_steps),
                    max_steps,
                    consider_goals,
                    consider_capacity,
                )
            )

        path_steps = []
        contextual_knowledge_list: list[ContextualKnowledge] = ready_result.value

        for contextual_ku in contextual_knowledge_list:
            applications_result = await self._get_application_opportunities_for_ku(
                contextual_ku.uid
            )
            if applications_result.is_error:
                return Result.fail(applications_result)
            applications = applications_result.value

            # Count unlocks
            unlocks_count = self._count_items_unlocked_by(contextual_ku.uid)

            # Find aligned goals
            aligned_goals = self._find_aligned_goals(contextual_ku.uid)

            step = PathStep(
                ku_uid=contextual_ku.uid,
                title=contextual_ku.title,
                rationale=self._generate_learning_rationale(
                    contextual_ku.uid, aligned_goals, unlocks_count, applications
                ),
                prerequisites_met=contextual_ku.prerequisites_met,
                aligns_with_goals=tuple(aligned_goals),
                unlocks_count=unlocks_count,
                estimated_time_minutes=self.context.estimated_minutes(
                    contextual_ku.uid, LearningTimeEstimate.NEXT_STEP_MINUTES
                ),
                priority_score=contextual_ku.priority_score,
                application_opportunities={k: tuple(v) for k, v in applications.items()},
            )

            path_steps.append(step)

        return Result.ok(self._rank_steps(path_steps, max_steps, consider_goals, consider_capacity))

    def _get_path_steps_from_context(self, max_steps: int) -> list[PathStep]:
        """Fallback candidates from the context's own ready-to-learn list, unranked."""
        ready_uids = self.context.get_ready_to_learn()

        if not ready_uids:
            return []

        path_steps = []

        for ku_uid in ready_uids[: max_steps * 2]:
            priority_score = self._context_priority(ku_uid)

            # NOTE: This is a fallback path - no application discovery
            # when main KU service is unavailable (fail-fast principle)
            applications: dict[str, list[str]] = {
                "tasks": [],
                "habits": [],
                "goals": [],
                "events": [],
            }
            unlocks_count = self._count_items_unlocked_by(ku_uid)
            aligned_goals = self._find_aligned_goals(ku_uid)

            step = PathStep(
                ku_uid=ku_uid,
                title=f"Knowledge Unit {ku_uid}",
                rationale=self._generate_learning_rationale(
                    ku_uid, aligned_goals, unlocks_count, applications
                ),
                prerequisites_met=True,
                aligns_with_goals=tuple(aligned_goals),
                unlocks_count=unlocks_count,
                estimated_time_minutes=self.context.estimated_minutes(
                    ku_uid, LearningTimeEstimate.NEXT_STEP_MINUTES
                ),
                priority_score=priority_score,
                application_opportunities={k: tuple(v) for k, v in applications.items()},
            )

            path_steps.append(step)

        return path_steps

    def _context_priority(self, ku_uid: str) -> float:
        """Score a context-fallback candidate (0.0-1.0) before the flags act on it."""
        score = 0.5  # Base score

        # Unblocking potential (25% weight)
        unlocks_count = self._count_items_unlocked_by(ku_uid)
        if unlocks_count > 0:
            unblocking_weight = min(0.25, unlocks_count * 0.05)
            score += unblocking_weight

        # Knowledge the life path holds (25% weight)
        if ku_uid in self.context.life_path_knowledge_uids:
            score += 0.25

        return min(1.0, score)

    def _rank_steps(
        self,
        steps: list[PathStep],
        max_steps: int,
        consider_goals: bool,
        consider_capacity: bool,
    ) -> list[PathStep]:
        """Turn one source's candidates into the answer: weigh goals, order, fit the day, cut.

        Every candidate source ends here, so ``consider_goals`` and ``consider_capacity``
        have one meaning. Candidates that tie keep the order their source gave them.
        """
        if consider_goals:
            steps = [self._with_goal_weight(step) for step in steps]

        ranked = sorted(steps, key=get_priority_score, reverse=True)

        if consider_capacity:
            ranked = self._filter_by_capacity(ranked)

        return ranked[:max_steps]

    def _with_goal_weight(self, step: PathStep) -> PathStep:
        """Raise a step's score by the goals it serves; a step serving none is returned as is."""
        if not step.aligns_with_goals:
            return step

        goal_weight = min(
            NextStepRanking.GOAL_WEIGHT_MAX,
            len(step.aligns_with_goals) * NextStepRanking.GOAL_WEIGHT_PER_GOAL,
        )
        # A vector score can sit above 1.0 (similarity times a learning-state boost);
        # the ceiling applies to what the weight adds and never lowers a score.
        weighted = max(step.priority_score, min(1.0, step.priority_score + goal_weight))
        return replace(step, priority_score=weighted)

    def _generate_learning_rationale(
        self,
        ku_uid: str,
        aligned_goals: list[str],
        unlocks_count: int,
        applications: dict[str, list[str]],
    ) -> str:
        """Generate human-readable rationale for why to learn this."""
        reasons = []

        if aligned_goals:
            reasons.append(f"Helps with {len(aligned_goals)} active goals")

        if unlocks_count > 0:
            reasons.append(f"Unlocks {unlocks_count} blocked items")

        total_apps = sum(len(items) for items in applications.values())
        if total_apps > 0:
            reasons.append(f"{total_apps} opportunities to apply this knowledge")

        if ku_uid in self.context.life_path_knowledge_uids:
            reasons.append("Part of your life path")

        return "; ".join(reasons) if reasons else "Ready to learn"

    def _find_aligned_goals(self, ku_uid: str) -> list[str]:
        """Find active goals that require this knowledge."""
        return self.context.active_goals_requiring(ku_uid)

    def _count_items_unlocked_by(self, ku_uid: str) -> int:
        """Count the blocked Kus whose one remaining unmet prerequisite is this KU."""
        return sum(
            1 for unmet in self.context.unmet_prerequisites_by_ku().values() if unmet == {ku_uid}
        )

    async def _get_application_opportunities_for_ku(
        self, ku_uid: str
    ) -> Result[dict[str, list[str]]]:
        """
        Where this knowledge is applied — tasks, habits, events from the graph, goals from context.

        The three graph reads are REQUIRED: a failed read fails the answer, so a
        ranking never carries an opportunity list that is silently empty
        because the graph could not be asked. ``ku_uid`` is whatever the source
        handed over — a Ku uid (ZPD, vector search) or a PathStep uid (the
        ready-to-learn read); the reads take either.

        Returns:
            Result of a dict with keys: tasks, habits, goals, events (all list[str])
        """
        opportunities: dict[str, list[str]] = {
            "tasks": [],
            "habits": [],
            "goals": [],
            "events": [],
        }

        tasks_result = await self.tasks.get_learning_tasks_for_user(
            self.context, knowledge_focus=[ku_uid]
        )
        if tasks_result.is_error:
            return Result.fail(tasks_result)
        opportunities["tasks"] = [t.uid for t in (tasks_result.value or [])[:5]]

        habits_result = await self.ps.find_habits_reinforcing_knowledge(
            ku_uid, self.context.user_uid, only_active=True
        )
        if habits_result.is_error:
            return Result.fail(habits_result)
        opportunities["habits"] = habits_result.value[:5]

        events_result = await self.ps.find_events_applying_knowledge(
            ku_uid, self.context.user_uid, upcoming_only=True
        )
        if events_result.is_error:
            return Result.fail(events_result)
        opportunities["events"] = events_result.value[:5]

        # Goals aligned with this knowledge come from the context, not a read.
        opportunities["goals"] = self._find_aligned_goals(ku_uid)

        return Result.ok(opportunities)

    def _filter_by_capacity(self, steps: list[PathStep]) -> list[PathStep]:
        """Keep, in order, each step that fits in what is left of the day's minutes.

        A step too long for the remainder is skipped and the walk continues, so a shorter
        step ranked below it can be kept.
        """
        available = self.context.available_minutes_daily
        filtered = []
        total_time = 0

        for step in steps:
            if total_time + step.estimated_time_minutes <= available:
                filtered.append(step)
                total_time += step.estimated_time_minutes

        return filtered

    # =========================================================================
    # METHOD 2: Learning Path Critical Path
    # =========================================================================

    async def get_learning_path_critical_path(
        self,
    ) -> Result[
        list[str]
    ]:  # skuel-lint: disable=SKUEL029 -- askesis_protocols protocol method + facade-delegated
        """
        What's the fastest route to life path alignment?

        Reads the context only: the life path's knowledge the user has not mastered
        (``life_path_knowledge_uids`` less ``mastered_knowledge_uids``), ordered so each
        Ku follows its prerequisites (``life_path_prerequisites``, started or not). Of the
        Kus ready at each step, the one that unlocks the most of the rest comes first — a
        Ku whose one unmet prerequisite it is — and a tie goes by uid. A Ku whose unmet
        prerequisite lies outside that set is left off. The path's step order and
        the LP backend's critical path are not read; see
        ``/docs/roadmap/lp-backend-recommendation-methods.md``.

        Returns:
            Result containing ordered list of KU UIDs representing critical path
        """
        critical_path = []
        remaining = self.context.life_path_knowledge_uids - self.context.mastered_knowledge_uids
        completed = set(self.context.mastered_knowledge_uids)

        def unmet(ku_uid: str) -> set[str]:
            return self.context.life_path_prerequisites.get(ku_uid, set()) - completed

        def unlocks(ku_uid: str) -> int:
            return sum(1 for other in remaining if unmet(other) == {ku_uid})

        while remaining:
            ready = [ku_uid for ku_uid in sorted(remaining) if not unmet(ku_uid)]
            if not ready:
                break

            best_ku = max(ready, key=unlocks)
            critical_path.append(best_ku)
            remaining.remove(best_ku)
            completed.add(best_ku)

        return Result.ok(critical_path)

    # =========================================================================
    # METHOD 3: Knowledge Application Opportunities
    # =========================================================================

    async def get_knowledge_application_opportunities(  # skuel-lint: disable=SKUEL029 -- askesis_protocols protocol method + facade-delegated
        self, ku_uid: str
    ) -> Result[dict[str, list[str]]]:
        """
        Where can I apply this knowledge in my life?

        Every activity linked to the Ku, from the context's own links (a link to a
        PathStep counts for each Ku it composes) — no graph read, so no read can fail:
        - Tasks: the active tasks that apply it
        - Goals: the active goals that require it
        - Habits: the active habits that apply or reinforce it, then the active
          habits supporting those goals
        - Events: the upcoming events that apply it, then the upcoming events
          reinforcing those habits — an event still to end, never a cancelled,
          completed or failed one (``_is_still_ahead``)
        - Choices: the pending choices it informs
        - Principles: the active principles grounded in it

        Args:
            ku_uid: Knowledge unit UID

        Returns:
            Result containing dict of {domain: [uid_list]} showing application opportunities
        """
        context = self.context
        opportunities: dict[str, list[str]] = {}

        opportunities["tasks"] = [
            uid
            for uid in context.active_task_uids
            if ku_uid in context.task_knowledge_applied.get(uid, ())
        ]

        goals = self._find_aligned_goals(ku_uid)
        opportunities["goals"] = goals

        habits = [
            uid
            for uid in context.active_habit_uids
            if ku_uid in context.habit_knowledge_applied.get(uid, ())
        ]
        habits += [
            uid
            for uid in context.active_habit_uids
            if uid not in habits
            and any(uid in context.get_habits_for_goal(goal_uid) for goal_uid in goals)
        ]
        opportunities["habits"] = habits

        upcoming = [uid for uid in context.upcoming_event_uids if self._is_still_ahead(uid)]
        events = [uid for uid in upcoming if ku_uid in context.event_knowledge_applied.get(uid, ())]
        events += [
            uid
            for uid in upcoming
            if uid not in events
            and any(uid in context.events_by_habit.get(habit_uid, ()) for habit_uid in habits)
        ]
        opportunities["events"] = events

        opportunities["choices"] = [
            uid
            for uid in context.pending_choice_uids
            if ku_uid in context.choice_knowledge_informed.get(uid, ())
        ]
        opportunities["principles"] = [
            uid
            for uid in context.core_principle_uids
            if ku_uid in context.principle_knowledge_grounded.get(uid, ())
        ]

        return Result.ok(opportunities)

    def _is_still_ahead(self, event_uid: str) -> bool:
        """Whether an upcoming event can still be attended: not ended, not terminal.

        ``upcoming_event_uids`` is every event dated today or later; this reads the
        event's rich record for its status and its end on the wall clock (its day and
        end time, as the calendar places it). An event the context holds no record
        for, or whose end it cannot place, is kept, as dated.
        """
        item = find_rich_entity_item(self.context, "events", event_uid)
        if item is None:
            return True
        entity = item.get("entity", {})
        status = EntityStatus.from_string(str(entity.get("status") or ""))
        if status is not None and status.is_terminal():
            return False
        zone = current_zone()
        stamp = parse_stamp(entity.get("event_date"))
        day = day_of(stamp, zone) if isinstance(stamp, datetime) else stamp
        end_time = convert_neo4j_time(entity.get("end_time"))
        if day is None or end_time is None:
            return True
        return datetime.combine(day, end_time) > wall_clock_in(zone)

    # =========================================================================
    # METHOD 4: Unblocking Priority Order
    # =========================================================================

    async def get_unblocking_priority_order(
        self,
    ) -> Result[
        list[tuple[str, int]]
    ]:  # skuel-lint: disable=SKUEL029 -- askesis_protocols protocol method + facade-delegated
        """
        What should I learn first to unlock the most items?

        Reads the context's per-Ku prerequisite map (``ku_prerequisites``): each
        unmastered prerequisite scores the number of blocked Kus it holds back.

        Returns:
            Result containing list of (ku_uid, blocked_count) sorted by impact (highest first)
        """
        blocker_counts: dict[str, int] = {}

        for unmet in self.context.unmet_prerequisites_by_ku().values():
            for prereq in unmet:
                blocker_counts[prereq] = blocker_counts.get(prereq, 0) + 1

        from core.utils.sort_functions import get_second_item

        return Result.ok(sorted(blocker_counts.items(), key=get_second_item, reverse=True))

    # =========================================================================
    # Vector Search Helpers
    # =========================================================================

    def _generate_learning_query(self) -> str:
        """
        Generate a semantic search query based on user's learning goals and life path.

        Combines:
        - Life path focus
        - Active learning goals
        - Current knowledge context
        """
        query_parts = []

        # Include life path focus
        if self.context.life_path_uid:
            # Extract meaningful terms from life path context
            query_parts.append("learning path knowledge")

        # Include learning goals context
        if self.context.learning_goals:
            query_parts.append("goal-aligned learning")

        # Include the path steps the user is studying
        query_parts.extend(
            step["title"] for step in self.context.current_path_steps if step.get("title")
        )

        # Default if no context
        if not query_parts:
            query_parts.append("ready to learn knowledge")

        return " ".join(query_parts)

    async def _vector_results_to_path_steps(
        self,
        vector_results: list[dict[str, Any]],
        max_steps: int,
        consider_goals: bool,
        consider_capacity: bool,
    ) -> Result[list[PathStep]]:
        """
        Convert vector search results to PathStep objects and rank them.

        Args:
            vector_results: Results from learning_aware_search()
            max_steps: Maximum steps to return
            consider_goals: Weight by goal alignment (``_rank_steps``)
            consider_capacity: Fit the steps to the day (``_rank_steps``)

        Returns:
            Result[list[PathStep]] with full context
        """
        path_steps = []

        for result in vector_results[: max_steps * 2]:
            node = result["node"]
            ku_uid = node["uid"]
            score = result.get("score", 0.0)

            applications_result = await self._get_application_opportunities_for_ku(ku_uid)
            if applications_result.is_error:
                return Result.fail(applications_result)
            applications = applications_result.value

            # Count unlocks
            unlocks_count = self._count_items_unlocked_by(ku_uid)

            # Find aligned goals
            aligned_goals = self._find_aligned_goals(ku_uid)

            prerequisites_met = not self.context.unmet_prerequisites(ku_uid)

            step = PathStep(
                ku_uid=ku_uid,
                title=node.get("title", f"Knowledge Unit {ku_uid}"),
                rationale=self._generate_learning_rationale(
                    ku_uid, aligned_goals, unlocks_count, applications
                ),
                prerequisites_met=prerequisites_met,
                aligns_with_goals=tuple(aligned_goals),
                unlocks_count=unlocks_count,
                estimated_time_minutes=self.context.estimated_minutes(
                    ku_uid, LearningTimeEstimate.NEXT_STEP_MINUTES
                ),
                priority_score=score,  # Use vector search score
                application_opportunities={k: tuple(v) for k, v in applications.items()},
            )

            path_steps.append(step)

        return Result.ok(self._rank_steps(path_steps, max_steps, consider_goals, consider_capacity))


__all__ = ["LearningIntelligenceMixin"]
