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
    submissions_core_service: Any,
    notification_service: Any,
    advanced: dict[str, Any],
    analytics_service: Any,
    submissions_backend: Any = None,
    insight_store: Any = None,
) -> None:
    """Wire all event subscribers for context invalidation, cross-domain, and intelligence.

    Pure side-effects: subscribes handlers to the event bus. No return value.
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
        ExpenseCreated,
        ExpenseDeleted,
        ExpensePaid,
        ExpenseUpdated,
        GoalAbandoned,
        GoalAchieved,
        GoalCreated,
        GoalMilestoneReached,
        GoalProgressUpdated,
        HabitCompleted,
        HabitCompletionBulk,
        HabitCreated,
        HabitMissed,
        HabitStreakBroken,
        HabitStreakMilestone,
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
        TasksBulkCompleted,
        TaskUpdated,
    )
    from core.events.handlers.exercise_handler import handle_exercise_submission
    from core.events.handlers.report_notification_handler import (
        handle_report_submitted,
        handle_revised_exercise_created,
        handle_revision_requested,
        handle_submission_approved,
    )
    from core.events.learning_events import LessonCompleted
    from core.events.lesson_events import (
        KnowledgeAppliedInTask,
        KnowledgeBuiltIntoHabit,
        KnowledgeBulkAppliedInTask,
        KnowledgeBulkBuiltIntoHabit,
        KnowledgeBulkInformedChoice,
        KnowledgeInformedChoice,
        KnowledgePracticedInEvent,
    )
    from core.events.principle_events import (
        PrincipleConflictRevealed,
        PrincipleReflectionRecorded,
    )
    from core.events.submission_events import (
        ReportSubmitted,
        RevisedExerciseCreated,
        SubmissionApproved,
        SubmissionCreated,
        SubmissionProcessingCompleted,
        SubmissionProcessingFailed,
        SubmissionProcessingStarted,
        SubmissionRevisionRequested,
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

    # Activity Domain + Finance events (user_uid guaranteed)
    activity_context_events = [
        # Tasks
        TaskCreated,
        TaskCompleted,
        TaskUpdated,
        TaskDeleted,
        TaskPriorityChanged,
        # Goals
        GoalCreated,
        GoalAchieved,
        GoalAbandoned,
        GoalMilestoneReached,
        GoalProgressUpdated,
        # Habits
        HabitCreated,
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
        # Finance
        ExpenseCreated,
        ExpenseUpdated,
        ExpenseDeleted,
        ExpensePaid,
        # Submission processing lifecycle
        SubmissionProcessingStarted,
        SubmissionProcessingCompleted,
        SubmissionProcessingFailed,
    ]
    for event_type in activity_context_events:
        event_bus.subscribe(event_type, invalidate_context)
    logger.info(
        f"✅ UserService subscribed to {len(activity_context_events)} activity/domain context events"
    )

    # Subscribe to SubmissionCreated for exercise linking (ADR-040)
    exercise_handler = functools.partial(
        handle_exercise_submission,
        reports_core_service=submissions_core_service,
    )
    event_bus.subscribe(SubmissionCreated, exercise_handler)
    logger.info(
        "✅ Exercise handler subscribed to SubmissionCreated "
        "(automatic FULFILLS_EXERCISE + SHARES_WITH creation)"
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
    event_bus.subscribe(SubmissionApproved, submission_approved_handler)
    event_bus.subscribe(SubmissionRevisionRequested, revision_requested_handler)
    event_bus.subscribe(RevisedExerciseCreated, revised_exercise_handler)
    logger.info(
        "✅ Learning loop notification handlers subscribed to ReportSubmitted + "
        "SubmissionApproved + SubmissionRevisionRequested + RevisedExerciseCreated "
        "(student notifications)"
    )

    # Learning loop intelligence handlers — iteration tracking, feedback turnaround, mastery velocity
    if submissions_backend and insight_store:
        from core.services.submissions import LearningLoopEventHandlerService

        learning_loop_handler = LearningLoopEventHandlerService(
            backend=submissions_backend,
            insight_store=insight_store,
        )
        event_bus.subscribe(SubmissionCreated, learning_loop_handler.handle_submission_created)
        event_bus.subscribe(ReportSubmitted, learning_loop_handler.handle_report_submitted)
        event_bus.subscribe(SubmissionApproved, learning_loop_handler.handle_submission_approved)
        logger.info(
            "✅ LearningLoopEventHandlerService subscribed to SubmissionCreated, "
            "ReportSubmitted, SubmissionApproved (iteration tracking + feedback turnaround + mastery velocity)"
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

    # Knowledge mastery → Learning Path progress update
    lp_service = learning_services["learning_paths"]
    ps_service = learning_services["path_steps"]
    ku_service_for_mastery = learning_services["path_steps"]

    event_bus.subscribe(KnowledgeMastered, lp_service.progress.handle_knowledge_mastered)
    logger.info(
        "✅ LpProgressService subscribed to KnowledgeMastered (automatic LP progress updates)"
    )

    # Knowledge mastery → PathStep completion detection
    event_bus.subscribe(KnowledgeMastered, ku_service_for_mastery.mastery.handle_knowledge_mastered)
    logger.info(
        "✅ PsMasteryService subscribed to KnowledgeMastered (path step completion detection)"
    )

    # PathStep completion → PS progress update
    event_bus.subscribe(LessonCompleted, ps_service.progress.handle_lesson_completed)
    logger.info(
        "✅ PsProgressService subscribed to LessonCompleted (automatic PS progress updates)"
    )

    # LS completion → LP progress update (chain: LS→LP)
    event_bus.subscribe(PathStepCompleted, lp_service.progress.handle_step_completed)
    logger.info("✅ LpProgressService subscribed to PathStepCompleted (LS→LP progress chain)")

    # Event completion → Knowledge practice tracking
    ku_service = learning_services["path_steps"]
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
    event_bus.subscribe(HabitCompleted, cross_domain_analytics_service.handle_habit_completed)
    event_bus.subscribe(
        CalendarEventCompleted, cross_domain_analytics_service.handle_event_completed
    )
    event_bus.subscribe(ExpenseCreated, cross_domain_analytics_service.handle_expense_created)
    event_bus.subscribe(ExpensePaid, cross_domain_analytics_service.handle_expense_paid)
    event_bus.subscribe(GoalCreated, cross_domain_analytics_service.handle_goal_created)
    event_bus.subscribe(KnowledgeMastered, cross_domain_analytics_service.handle_knowledge_mastered)
    event_bus.subscribe(LearningPathCompleted, cross_domain_analytics_service.handle_path_completed)
    # NOTE: JournalCreated subscription REMOVED (February 2026)
    # Journal merged into Reports — cross_domain_analytics needs update in
    # to subscribe to SubmissionCreated and filter for entity_type="journal"
    logger.info(
        "✅ CrossDomainAnalyticsService subscribed to 8 event types "
        "(Tasks, Habits, Events, Expenses, Goals, Knowledge, Paths)"
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
        "✅ EventsEventHandlerService subscribed to "
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

    # KU intelligence - learning progress when path steps are completed
    event_bus.subscribe(PathStepCompleted, ku_service.intelligence.handle_path_step_completed)
    logger.info("✅ LessonIntelligenceService subscribed to PathStepCompleted")

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

    logger.info("✅ Event-driven architecture wired (45+ event types subscribed)")
