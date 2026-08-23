"""Event bus subscription wiring — 45+ event handler subscriptions."""

from typing import Any

from core.ports import EventBusOperations
from core.utils.logging import get_logger

logger = get_logger("skuel.bootstrap")


def _wire_event_subscribers(
    event_bus: EventBusOperations,
    user_service: Any,
    activity_services: dict[str, Any],
    learning_services: dict[str, Any],
    user_entry_exercise_linker: Any,
    notification_service: Any,
    advanced: dict[str, Any],
    analytics_service: Any,
    user_entry_backend: Any,
    insight_store: Any,
    group_backend: Any,
    ps_engagement: Any,
    search_event_recorder: Any,
    interaction_service: Any,
) -> None:
    """Wire all event subscribers for context invalidation, cross-domain, and intelligence.

    Pure side-effects: subscribes handlers to the event bus. No return value.
    All dependencies are required — compose_services passes them unconditionally.
    """
    import functools

    # ── Import all event types ──────────────────────────────────────────────
    from core.events import (
        CalendarEventCompleted,
        CalendarEventCreated,
        CalendarEventDeleted,
        CalendarEventRescheduled,
        CalendarEventUpdated,
        ChoiceCreated,
        ChoiceDeleted,
        ChoiceMade,
        ChoiceOutcomeRecorded,
        ChoiceUpdated,
        GoalAbandoned,
        GoalAchieved,
        GoalCreated,
        GoalMilestoneReached,
        GoalProgressUpdated,
        GoalUpdated,
        HabitCompleted,
        HabitCompletionBulk,
        HabitCreated,
        HabitMissed,
        HabitStreakBroken,
        HabitStreakMilestone,
        HabitUpdated,
        KnowledgeCreated,
        KnowledgeMastered,
        LearningPathCompleted,
        LearningPathProgressUpdated,
        LearningPathStarted,
        PathStepCompleted,
        PathStepCreated,
        PathStepDeleted,
        PathStepUpdated,
        PrincipleAlignmentAssessed,
        PrincipleCreated,
        PrincipleDeleted,
        PrincipleStrengthChanged,
        PrincipleUpdated,
        TaskCompleted,
        TaskCreated,
        TaskDeleted,
        TaskPriorityChanged,
        TaskReopened,
        TasksBulkCompleted,
        TaskUpdated,
    )
    from core.events.curriculum_events import PathStepEnrolled
    from core.events.handlers.exercise_handler import handle_exercise_submission
    from core.events.handlers.report_notification_handler import (
        handle_report_submitted,
        handle_revised_exercise_created,
        handle_revision_requested,
        handle_submission_approved,
    )
    from core.events.knowledge_substance_events import (
        KnowledgeAppliedInTask,
        KnowledgeBuiltIntoHabit,
        KnowledgeBulkAppliedInTask,
        KnowledgeBulkBuiltIntoHabit,
        KnowledgeBulkInformedChoice,
        KnowledgeInformedChoice,
        KnowledgePracticedInEvent,
        KnowledgeReflectedInEntry,
    )
    from core.events.learning_loop_events import (
        EntryReportGenerated,
        ReportSubmitted,
        RevisedExerciseCreated,
        UserEntryApproved,
        UserEntryRevisionRequested,
    )
    from core.events.principle_events import (
        PrincipleConflictRevealed,
        PrincipleReflectionRecorded,
    )
    from core.events.user_entry_events import (
        UserEntryCreated,
        UserEntryProcessingCompleted,
        UserEntryProcessingFailed,
        UserEntryProcessingStarted,
    )

    # ── Context invalidation handlers ───────────────────────────────────────
    # Two handlers: one for events that guarantee user_uid, one for events
    # where user_uid may be absent (curriculum/learning events).

    async def invalidate_context(event) -> None:
        """Invalidate user context cache when any domain event with user_uid fires."""
        logger.debug(f"Context invalidation: {event.__class__.__name__} for user {event.user_uid}")
        await user_service.invalidate_context(event.user_uid)

    async def invalidate_context_if_user(event) -> None:
        """Invalidate user context for events that may lack user_uid (curriculum events)."""
        user_uid = getattr(event, "user_uid", None)
        if user_uid:
            logger.debug(f"Context invalidation: {event.__class__.__name__} for user {user_uid}")
            await user_service.invalidate_context(user_uid)

    # ── Context invalidation subscriptions ──────────────────────────────────
    # All user-owned domain events guarantee user_uid on the event object.

    # Activity Domain events (user_uid guaranteed)
    activity_context_events = [
        # Tasks
        TaskCreated,
        TaskCompleted,
        TaskUpdated,
        TaskDeleted,
        TaskPriorityChanged,
        # Goals
        GoalCreated,
        GoalUpdated,
        GoalAchieved,
        GoalAbandoned,
        GoalMilestoneReached,
        GoalProgressUpdated,
        # Habits
        HabitCreated,
        HabitUpdated,
        HabitCompleted,
        HabitCompletionBulk,
        HabitMissed,
        HabitStreakBroken,
        HabitStreakMilestone,
        # Principles
        PrincipleCreated,
        PrincipleUpdated,
        PrincipleDeleted,
        PrincipleStrengthChanged,
        PrincipleAlignmentAssessed,
        # Choices
        ChoiceCreated,
        ChoiceUpdated,
        ChoiceDeleted,
        ChoiceMade,
        ChoiceOutcomeRecorded,
        # Calendar Events
        CalendarEventCreated,
        CalendarEventUpdated,
        CalendarEventCompleted,
        CalendarEventDeleted,
        CalendarEventRescheduled,
        # UserEntry processing lifecycle
        UserEntryProcessingStarted,
        UserEntryProcessingCompleted,
        UserEntryProcessingFailed,
    ]
    for event_type in activity_context_events:
        event_bus.subscribe(event_type, invalidate_context)
    logger.info(
        f"✅ UserService subscribed to {len(activity_context_events)} activity/domain context events"
    )

    # Subscribe to UserEntryCreated for exercise linking (ADR-040 / ADR-054)
    exercise_handler = functools.partial(
        handle_exercise_submission,
        exercise_linker=user_entry_exercise_linker,
    )
    event_bus.subscribe(UserEntryCreated, exercise_handler)
    logger.info(
        "✅ Exercise handler subscribed to UserEntryCreated "
        "(automatic FULFILLS_EXERCISE + SHARES_WITH creation)"
    )

    # Subscribe to PathStepEnrolled for auto default-group enrolment (ADR-040)
    from core.events.handlers.path_step_enrollment_handler import handle_path_step_enrolled

    enrollment_handler = functools.partial(
        handle_path_step_enrolled,
        user_entry_backend=user_entry_backend,
        group_backend=group_backend,
    )
    event_bus.subscribe(PathStepEnrolled, enrollment_handler)
    logger.info(
        "✅ Enrollment handler subscribed to PathStepEnrolled "
        "(auto student enrolment in admin default group)"
    )

    # Subscribe to report events for student notifications
    report_submitted_handler = functools.partial(
        handle_report_submitted,
        notification_service=notification_service,
    )
    submission_approved_handler = functools.partial(
        handle_submission_approved,
        notification_service=notification_service,
    )
    revision_requested_handler = functools.partial(
        handle_revision_requested,
        notification_service=notification_service,
    )
    revised_exercise_handler = functools.partial(
        handle_revised_exercise_created,
        notification_service=notification_service,
    )
    event_bus.subscribe(ReportSubmitted, report_submitted_handler)
    event_bus.subscribe(UserEntryApproved, submission_approved_handler)
    event_bus.subscribe(UserEntryRevisionRequested, revision_requested_handler)
    event_bus.subscribe(RevisedExerciseCreated, revised_exercise_handler)
    logger.info(
        "✅ Learning loop notification handlers subscribed to ReportSubmitted + "
        "UserEntryApproved + UserEntryRevisionRequested + RevisedExerciseCreated "
        "(student notifications)"
    )

    # Learning loop intelligence handlers — iteration tracking, feedback turnaround, mastery velocity
    from core.services.user_entry.learning_loop_handler import LearningLoopEventHandlerService

    learning_loop_handler = LearningLoopEventHandlerService(
        backend=user_entry_backend,
        insight_store=insight_store,
    )
    event_bus.subscribe(UserEntryCreated, learning_loop_handler.handle_submission_created)
    event_bus.subscribe(ReportSubmitted, learning_loop_handler.handle_report_submitted)
    event_bus.subscribe(UserEntryApproved, learning_loop_handler.handle_submission_approved)
    logger.info(
        "✅ LearningLoopEventHandlerService subscribed to UserEntryCreated, "
        "ReportSubmitted, UserEntryApproved (iteration tracking + feedback turnaround + mastery velocity)"
    )

    # Interaction result-status transitions (ADR-051 Phase 2) — the audit
    # record moves PENDING → SHARED_WITH_TEACHER → REPORT_GENERATED →
    # COMPLETED (or FAILED) as the report pipeline progresses.
    # SHARED_WITH_TEACHER is recorded directly by UserEntryService.create_entry
    # (only it knows the share outcome).
    from core.events.handlers import interaction_result_handler

    event_bus.subscribe(
        ReportSubmitted,
        functools.partial(
            interaction_result_handler.handle_report_submitted,
            interaction_service=interaction_service,
        ),
    )
    event_bus.subscribe(
        EntryReportGenerated,
        functools.partial(
            interaction_result_handler.handle_entry_report_generated,
            interaction_service=interaction_service,
        ),
    )
    event_bus.subscribe(
        UserEntryRevisionRequested,
        functools.partial(
            interaction_result_handler.handle_revision_requested,
            interaction_service=interaction_service,
        ),
    )
    event_bus.subscribe(
        UserEntryApproved,
        functools.partial(
            interaction_result_handler.handle_entry_approved,
            interaction_service=interaction_service,
        ),
    )
    event_bus.subscribe(
        UserEntryProcessingFailed,
        functools.partial(
            interaction_result_handler.handle_processing_failed,
            interaction_service=interaction_service,
        ),
    )
    logger.info(
        "✅ Interaction result handler subscribed to ReportSubmitted, "
        "EntryReportGenerated, UserEntryRevisionRequested, UserEntryApproved, "
        "UserEntryProcessingFailed (ADR-051 Phase 2 result_status transitions)"
    )

    # Learning events (user_uid may be absent on curriculum-level events)
    learning_context_events = [
        KnowledgeCreated,
        KnowledgeMastered,
        LearningPathStarted,
        LearningPathCompleted,
        LearningPathProgressUpdated,
        PathStepCreated,
        PathStepUpdated,
        PathStepDeleted,
        PathStepCompleted,
    ]
    for event_type in learning_context_events:
        event_bus.subscribe(event_type, invalidate_context_if_user)
    logger.info(
        f"✅ UserService subscribed to {len(learning_context_events)} learning context events"
    )

    # ── Cross-domain event subscriptions ────────────────────────────────────
    # "Events over dependencies" - Eliminate service-to-service coupling

    # Task completion → Goal progress update
    goals_service = activity_services["goals"]  # Use unified activity service
    event_bus.subscribe(TaskCompleted, goals_service.progress.handle_task_completed)
    logger.info("✅ GoalsProgressService subscribed to TaskCompleted (automatic progress updates)")

    # Habit completion → Goal progress update
    event_bus.subscribe(HabitCompleted, goals_service.progress.handle_habit_completed)
    logger.info("✅ GoalsProgressService subscribed to HabitCompleted (automatic progress updates)")

    # Goal achievement → Event handler (recommendations, duration calibration, alignment)
    event_bus.subscribe(GoalAchieved, goals_service.event_handler.handle_goal_achieved)
    # Goal abandonment → Event handler (classification, structured logging)
    event_bus.subscribe(GoalAbandoned, goals_service.event_handler.handle_goal_abandoned)
    # Goal progress → Event handler (stall detection, milestone proximity)
    event_bus.subscribe(
        GoalProgressUpdated, goals_service.event_handler.handle_goal_progress_updated
    )
    logger.info(
        "✅ GoalEventHandlerService subscribed to GoalAchieved, GoalAbandoned, GoalProgressUpdated"
    )

    # ── PS engagement auto-completion ───────────────────────────────────────
    # When an Activity instance reaches engagement-terminal status, check
    # whether its parent PS engagement is now fully done and auto-complete
    # if so. See: core/services/ps_engagement/_auto_completion_handler.py
    # and core/services/ps_engagement/_terminal_status_rules.py.
    from core.services.ps_engagement._auto_completion_handler import _AutoCompletionHandler

    auto_complete = _AutoCompletionHandler(ps_engagement)
    event_bus.subscribe(TaskCompleted, auto_complete.on_task_completed)
    event_bus.subscribe(GoalAchieved, auto_complete.on_goal_achieved)
    event_bus.subscribe(CalendarEventCompleted, auto_complete.on_calendar_event_completed)
    event_bus.subscribe(ChoiceMade, auto_complete.on_choice_made)
    logger.info(
        "✅ PsEngagementService auto-complete subscribed to TaskCompleted, "
        "GoalAchieved, CalendarEventCompleted, ChoiceMade"
    )

    # Knowledge mastery → Learning Path progress update
    lp_service = learning_services["learning_paths"]
    ps_service = learning_services["ps"]
    ku_service_for_mastery = learning_services["ps"]

    event_bus.subscribe(KnowledgeMastered, lp_service.progress.handle_knowledge_mastered)
    logger.info(
        "✅ LpProgressService subscribed to KnowledgeMastered (automatic LP progress updates)"
    )

    # Knowledge mastery → PathStep completion detection
    event_bus.subscribe(KnowledgeMastered, ku_service_for_mastery.mastery.handle_knowledge_mastered)
    logger.info(
        "✅ PsMasteryService subscribed to KnowledgeMastered (path step completion detection)"
    )

    # Knowledge mastery → PathStep progress update
    event_bus.subscribe(KnowledgeMastered, ps_service.progress.handle_knowledge_mastered)
    logger.info(
        "✅ PsProgressService subscribed to KnowledgeMastered (automatic PS progress updates)"
    )

    # PS completion → LP progress update (chain: PS→LP)
    event_bus.subscribe(PathStepCompleted, lp_service.progress.handle_step_completed)
    logger.info("✅ LpProgressService subscribed to PathStepCompleted (PS→LP progress chain)")

    # Event completion → Knowledge practice tracking
    ku_service = learning_services["ps"]
    event_bus.subscribe(CalendarEventCompleted, ku_service.practice.handle_event_completed)
    logger.info(
        "✅ PsPracticeService subscribed to CalendarEventCompleted (automatic practice tracking)"
    )

    # Habit streak milestone → Achievement badges
    habits_service = activity_services["habits"]
    event_bus.subscribe(
        HabitStreakMilestone, habits_service.event_handler.handle_habit_streak_milestone
    )
    logger.info("✅ HabitEventHandlerService subscribed to HabitStreakMilestone (badge awarding)")

    # Learning path completion & knowledge mastery → Learning recommendations
    learning_intelligence = learning_services["learning_intelligence"]
    event_bus.subscribe(
        LearningPathCompleted,
        learning_intelligence.recommendation_engine.handle_learning_path_completed,
    )
    event_bus.subscribe(
        KnowledgeMastered, learning_intelligence.recommendation_engine.handle_knowledge_mastered
    )
    logger.info(
        "✅ LearningRecommendationEngine subscribed to LearningPathCompleted & KnowledgeMastered "
        "(intelligent next-step recommendations)"
    )

    # Multi-domain analytics → Track activity across all domains
    cross_domain_analytics_service = advanced["cross_domain_analytics"]
    event_bus.subscribe(TaskCompleted, cross_domain_analytics_service.handle_task_completed)
    # ProductivityAnalytics.tasks_completed is recomputed, not tallied, so it has
    # to hear about a reopen too — otherwise the count could only ever rise.
    event_bus.subscribe(TaskReopened, cross_domain_analytics_service.handle_task_reopened)
    event_bus.subscribe(HabitCompleted, cross_domain_analytics_service.handle_habit_completed)
    event_bus.subscribe(
        CalendarEventCompleted, cross_domain_analytics_service.handle_event_completed
    )
    event_bus.subscribe(GoalCreated, cross_domain_analytics_service.handle_goal_created)
    event_bus.subscribe(KnowledgeMastered, cross_domain_analytics_service.handle_knowledge_mastered)
    event_bus.subscribe(LearningPathCompleted, cross_domain_analytics_service.handle_path_completed)
    # NOTE: JournalCreated subscription REMOVED (February 2026)
    # Journal merged into Reports — cross_domain_analytics needs update in
    # to subscribe to SubmissionCreated and filter for entity_type="journal"
    # NOTE: ExpenseCreated/ExpensePaid subscriptions REMOVED (ADR-052 Phase 5) —
    # native expense module demolished.
    logger.info(
        "✅ CrossDomainAnalyticsService subscribed to 7 event types "
        "(Tasks completed + reopened, Habits, Events, Goals, Knowledge, Paths)"
    )

    # Milestone achievements → Automatic report generation
    event_bus.subscribe(GoalAchieved, analytics_service.handle_goal_achieved)
    event_bus.subscribe(LearningPathCompleted, analytics_service.handle_learning_path_completed)
    event_bus.subscribe(HabitStreakMilestone, analytics_service.handle_habit_streak_milestone)
    logger.info(
        "✅ AnalyticsService subscribed to 3 milestone events "
        "(GoalAchieved, LearningPathCompleted, HabitStreakMilestone) for auto-report generation"
    )

    # ── Substance tracking event subscriptions ──────────────────────────────
    # "Applied knowledge, not pure theory" - Track real-world knowledge application

    # Subscribe to substance tracking events (single-entity)
    event_bus.subscribe(KnowledgeAppliedInTask, ku_service.handle_knowledge_applied_in_task)
    event_bus.subscribe(KnowledgePracticedInEvent, ku_service.handle_knowledge_practiced_in_event)
    event_bus.subscribe(KnowledgeBuiltIntoHabit, ku_service.handle_knowledge_built_into_habit)
    event_bus.subscribe(KnowledgeInformedChoice, ku_service.handle_knowledge_informed_choice)
    event_bus.subscribe(KnowledgeReflectedInEntry, ku_service.handle_knowledge_reflected_in_entry)

    # Subscribe to BATCH substance tracking events (O(1) vs O(n))
    event_bus.subscribe(
        KnowledgeBulkAppliedInTask, ku_service.handle_knowledge_bulk_applied_in_task
    )
    event_bus.subscribe(
        KnowledgeBulkBuiltIntoHabit, ku_service.handle_knowledge_bulk_built_into_habit
    )
    event_bus.subscribe(
        KnowledgeBulkInformedChoice, ku_service.handle_knowledge_bulk_informed_choice
    )

    logger.info("✅ PsService subscribed to substance tracking events:")
    logger.info("   - KnowledgeAppliedInTask (weight: 0.05)")
    logger.info("   - KnowledgePracticedInEvent (weight: 0.05)")
    logger.info("   - KnowledgeBuiltIntoHabit (weight: 0.10, lifestyle integration)")
    logger.info("   - KnowledgeInformedChoice (weight: 0.07, decision-making)")
    logger.info("   - KnowledgeReflectedInEntry (weight: 0.07, metacognition)")
    logger.info(
        "   - Bulk events: KnowledgeBulkAppliedInTask, KnowledgeBulkBuiltIntoHabit, KnowledgeBulkInformedChoice"
    )

    # ── Domain intelligence event subscriptions ─────────────────────────────
    # "Events enable cross-domain intelligence"

    # ---- Adaptive Learning Loop (ADR-048) ----

    # Task event handlers - duration calibration, priority analysis, batch patterns
    tasks_service = activity_services["tasks"]
    event_bus.subscribe(TaskCompleted, tasks_service.event_handler.handle_task_completed)
    event_bus.subscribe(
        TaskPriorityChanged, tasks_service.event_handler.handle_task_priority_changed
    )
    event_bus.subscribe(TasksBulkCompleted, tasks_service.event_handler.handle_tasks_bulk_completed)
    logger.info(
        "✅ TaskEventHandlerService subscribed to TaskCompleted, TaskPriorityChanged, TasksBulkCompleted"
    )

    # Events event handlers - attendance patterns, rescheduling detection, scheduling density
    events_service = activity_services["events"]
    event_bus.subscribe(CalendarEventCompleted, events_service.event_handler.handle_event_completed)
    event_bus.subscribe(
        CalendarEventRescheduled, events_service.event_handler.handle_event_rescheduled
    )
    event_bus.subscribe(CalendarEventCreated, events_service.event_handler.handle_event_created)
    logger.info(
        "✅ EventEventHandlerService subscribed to "
        "CalendarEventCompleted, CalendarEventRescheduled, CalendarEventCreated"
    )

    # Habit event handlers - timing learning, recovery insights, difficulty tracking
    habits_service = activity_services["habits"]
    event_bus.subscribe(HabitCompleted, habits_service.event_handler.handle_habit_completed)
    event_bus.subscribe(HabitStreakBroken, habits_service.event_handler.handle_habit_streak_broken)
    logger.info("✅ HabitEventHandlerService subscribed to HabitCompleted, HabitStreakBroken")

    # Choice event handlers - decision learning when outcomes are recorded
    choices_service = activity_services["choices"]
    event_bus.subscribe(
        ChoiceOutcomeRecorded, choices_service.event_handler.handle_choice_outcome_recorded
    )
    logger.info("✅ ChoiceEventHandlerService subscribed to ChoiceOutcomeRecorded")

    # Principle event handlers - cascade analysis, reflection insights, conflict detection
    principles_service = activity_services["principles"]
    event_bus.subscribe(
        PrincipleStrengthChanged,
        principles_service.event_handler.handle_principle_strength_changed,
    )
    logger.info("✅ PrincipleEventHandlerService subscribed to PrincipleStrengthChanged")

    # ── Tier 1 handlers: Quick-win event intelligence ───────────────────────

    # Habit event handler - difficulty tracking when habits are missed
    event_bus.subscribe(HabitMissed, habits_service.event_handler.handle_habit_missed)
    logger.info("✅ HabitEventHandlerService subscribed to HabitMissed")

    # Choice event handler - decision pattern tracking when choice is made
    event_bus.subscribe(ChoiceMade, choices_service.event_handler.handle_choice_made)
    logger.info("✅ ChoiceEventHandlerService subscribed to ChoiceMade")

    # ── Tier 2 handlers: Pattern-based event intelligence ───────────────────

    # Principle event handler - cross-domain insights from reflections
    event_bus.subscribe(
        PrincipleReflectionRecorded,
        principles_service.event_handler.handle_reflection_recorded,
    )
    logger.info("✅ PrincipleEventHandlerService subscribed to PrincipleReflectionRecorded")

    # Principle event handler - conflict detection and resolution guidance
    event_bus.subscribe(
        PrincipleConflictRevealed,
        principles_service.event_handler.handle_conflict_revealed,
    )
    logger.info("✅ PrincipleEventHandlerService subscribed to PrincipleConflictRevealed")

    # NOTE: MOC intelligence subscription removed (January 2026)
    # MOC is Entity-based - intelligence operations happen through Entity ORGANIZES relationships
    # MapOfContentUpdated event type is deprecated - MOC changes are Entity changes

    logger.info(
        "✅ Domain intelligence event subscriptions wired (8 handlers): "
        "Tier 1: HabitStreakBroken, ChoiceOutcomeRecorded, PrincipleStrengthChanged, "
        "HabitMissed, ChoiceMade, PathStepCompleted | "
        "Tier 2: PrincipleReflectionRecorded, PrincipleConflictRevealed"
    )

    # ── Search behavioral log (discovery analytics) ─────────────────────────
    from core.events.search_events import SearchExecuted

    event_bus.subscribe(SearchExecuted, search_event_recorder.handle_search_executed)
    logger.info("✅ SearchEventRecorder subscribed to SearchExecuted (:SearchEvent log)")

    logger.info("✅ Event-driven architecture wired (45+ event types subscribed)")
