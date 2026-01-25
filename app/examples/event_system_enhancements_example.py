"""
Event System Enhancements Example
==================================

Demonstrates the enhanced event system with:
1. Event logging and audit trails
2. Event replay for debugging
3. Cross-domain analytics
4. Learning velocity tracking
5. Financial goal tracking
6. Journal mood analysis

All features built entirely on event subscriptions - no service coupling!

Version: 1.0.0
Date: 2025-10-16
"""

import asyncio
from datetime import datetime, timedelta

from core.events import (
    ExpenseCreated,
    GoalCreated,
    JournalCreated,
    KnowledgeMastered,
    LearningPathCompleted,
)
from core.services.cross_domain_analytics_service import CrossDomainAnalyticsService
from core.services.event_logger_service import EventLoggerService

# ============================================================================
# BOOTSTRAP WIRING EXAMPLE
# ============================================================================


async def wire_enhanced_event_system(event_bus, driver):
    """
    Wire enhanced event system in bootstrap.

    This shows how to integrate event logging and analytics WITHOUT
    modifying any existing services!
    """
    # Create enhanced services
    event_logger = EventLoggerService(driver)
    analytics = CrossDomainAnalyticsService(driver)

    # ========================================================================
    # EVENT LOGGING - Subscribe to ALL events for audit trail
    # ========================================================================

    # Log ALL events (using wildcard subscription if available)
    # For now, subscribe to each event type explicitly
    from core.events import ALL_EVENTS

    for event_class in ALL_EVENTS:
        event_bus.subscribe(event_class, event_logger.log_event)

    print("✅ Event logging enabled (all events logged to database)")

    # ========================================================================
    # CROSS-DOMAIN ANALYTICS - Subscribe to specific events
    # ========================================================================

    # Financial analytics
    event_bus.subscribe(ExpenseCreated, analytics.handle_expense_created)
    event_bus.subscribe(GoalCreated, analytics.handle_goal_created)

    # Learning velocity analytics
    event_bus.subscribe(KnowledgeMastered, analytics.handle_knowledge_mastered)
    event_bus.subscribe(LearningPathCompleted, analytics.handle_path_completed)

    # Journal mood analytics
    event_bus.subscribe(JournalCreated, analytics.handle_journal_created)

    print("✅ Cross-domain analytics enabled")

    return event_logger, analytics


# ============================================================================
# USAGE EXAMPLES
# ============================================================================


async def example_event_logging(event_logger):
    """Example: Event logging and querying."""

    print("\n📋 Event Logging Example")
    print("=" * 50)

    # Events are automatically logged when published
    # No explicit logging calls needed!

    # Query recent events for a user
    events_result = await event_logger.get_events_by_user(user_uid="user-123", days_back=7)

    if events_result.is_ok:
        events = events_result.value
        print(f"\n✓ Found {len(events)} events for user-123 in last 7 days:")

        for event in events[:5]:  # Show first 5
            print(f"  - {event.event_type} at {event.occurred_at}")

    # Query events for a specific entity (e.g., task)
    task_events_result = await event_logger.get_events_by_aggregate(
        aggregate_id="task-456", aggregate_type="Task"
    )

    if task_events_result.is_ok:
        task_events = task_events_result.value
        print(f"\n✓ Found {len(task_events)} events for task-456:")

        for event in task_events:
            print(f"  - {event.event_type} at {event.occurred_at}")

    # Get event statistics
    stats_result = await event_logger.get_event_statistics(user_uid="user-123", days_back=30)

    if stats_result.is_ok:
        stats = stats_result.value
        print("\n✓ Event Statistics (last 30 days):")
        print(f"  - Total events: {stats['total_events']}")
        print(f"  - Most common: {stats['most_common_event']}")
        print("  - Event counts:")
        for event_type, count in list(stats["event_counts"].items())[:5]:
            print(f"    • {event_type}: {count}")


async def example_event_replay(event_logger):
    """Example: Event replay for debugging."""

    print("\n🔄 Event Replay Example")
    print("=" * 50)

    # Define a debug handler
    async def debug_handler(event):
        print(f"  Replaying: {event.event_type} - {event.__dict__}")

    # Replay all task events for debugging
    replay_result = await event_logger.replay_events(
        filters={
            "event_type": "task.completed",
            "user_uid": "user-123",
            "start_date": datetime.now() - timedelta(days=7),
        },
        handler=debug_handler,
        dry_run=True,  # Don't mark as replayed (testing only)
    )

    if replay_result.is_ok:
        count = replay_result.value
        print(f"\n✓ Replayed {count} task completion events")


async def example_learning_velocity(analytics):
    """Example: Learning velocity tracking."""

    print("\n📚 Learning Velocity Example")
    print("=" * 50)

    # Get learning velocity metrics (built from KnowledgeMastered events)
    velocity_result = await analytics.get_learning_velocity(user_uid="user-123", days_back=30)

    if velocity_result.is_ok:
        velocity = velocity_result.value
        print("\n✓ Learning Velocity (last 30 days):")
        print(f"  - KUs mastered per week: {velocity.kus_mastered_per_week:.1f}")
        print(f"  - Paths completed: {velocity.paths_completed}")
        print(f"  - Total learning hours: {velocity.total_learning_hours:.1f}")
        print(f"  - Velocity trend: {velocity.velocity_trend}")
        print(f"  - Change from previous: {velocity.compared_to_previous_period:+.1f}%")


async def example_spending_patterns(analytics):
    """Example: Spending pattern analysis."""

    print("\n💰 Spending Patterns Example")
    print("=" * 50)

    # Get spending patterns (built from ExpenseCreated events)
    spending_result = await analytics.get_spending_patterns(user_uid="user-123", days_back=30)

    if spending_result.is_ok:
        spending = spending_result.value
        print("\n✓ Spending Patterns (last 30 days):")
        print(f"  - Top spending domain: {spending.top_spending_domain}")
        print(f"  - Average expense: ${spending.avg_expense_amount:.2f}")
        print(f"  - Expense frequency: {spending.expense_frequency_per_week:.1f} per week")
        print("\n  Spending by domain:")
        for domain, amount in list(spending.spending_by_domain.items())[:5]:
            print(f"    • {domain}: ${amount:.2f}")


async def example_mood_analysis(analytics):
    """Example: Journal mood analysis."""

    print("\n😊 Journal Mood Analysis Example")
    print("=" * 50)

    # Get mood analysis (built from JournalCreated events)
    mood_result = await analytics.get_mood_analysis(user_uid="user-123", days_back=30)

    if mood_result.is_ok:
        mood = mood_result.value
        print("\n✓ Mood Analysis (last 30 days):")
        print(f"  - Average mood: {mood.average_mood:.2f} (0.0-1.0 scale)")
        print(f"  - Mood trend: {mood.mood_trend}")
        print(f"  - Entries per week: {mood.entries_per_week:.1f}")
        print(f"  - Longest streak: {mood.longest_streak} days")
        print(f"  - Common themes: {', '.join(mood.most_common_themes)}")


async def example_financial_goal_tracking(analytics):
    """Example: Financial goal tracking."""

    print("\n🎯 Financial Goal Tracking Example")
    print("=" * 50)

    # Get financial metrics for a goal (links expenses to goals)
    metrics_result = await analytics.get_financial_goal_metrics(goal_uid="goal-789")

    if metrics_result.is_ok:
        metrics = metrics_result.value
        print("\n✓ Financial Goal Metrics:")
        print(f"  - Total expenses: ${metrics.total_expenses:.2f}")
        print(f"  - Expense count: {metrics.expense_count}")

        if metrics.budget_allocated:
            print(f"  - Budget allocated: ${metrics.budget_allocated:.2f}")
            print(f"  - Budget remaining: ${metrics.budget_remaining:.2f}")

        print("\n  Top expense categories:")
        for category, amount in list(metrics.top_expense_categories.items())[:3]:
            print(f"    • {category}: ${amount:.2f}")


async def example_event_export(event_logger):
    """Example: Export event stream for external analysis."""

    print("\n📤 Event Export Example")
    print("=" * 50)

    # Export events in JSON format
    export_result = await event_logger.export_event_stream(
        filters={
            "user_uid": "user-123",
            "days_back": 7,
            "event_types": ["task.completed", "knowledge.mastered"],
        },
        format="json",
    )

    if export_result.is_ok:
        json_data = export_result.value
        print("\n✓ Exported events (JSON):")
        print(f"  {json_data[:200]}...")  # Show first 200 chars

    # Export in NDJSON format for streaming
    ndjson_result = await event_logger.export_event_stream(
        filters={"user_uid": "user-123", "days_back": 7}, format="ndjson"
    )

    if ndjson_result.is_ok:
        print("\n✓ Exported events (NDJSON) - ready for streaming processing")


# ============================================================================
# SIMULATING EVENTS FOR TESTING
# ============================================================================


async def simulate_events_for_testing(event_bus):
    """Simulate some events for testing analytics."""

    print("\n🎬 Simulating Events for Testing")
    print("=" * 50)

    # Simulate knowledge mastery events
    for i in range(5):
        event = KnowledgeMastered(
            ku_uid=f"ku-{i}",
            user_uid="user-123",
            occurred_at=datetime.now() - timedelta(days=i),
            mastery_score=0.85 + (i * 0.02),
            time_to_mastery_hours=10 + i,
        )
        await event_bus.publish_async(event)

    print("✓ Published 5 KnowledgeMastered events")

    # Simulate expense events
    for i in range(3):
        event = ExpenseCreated(
            expense_uid=f"expense-{i}",
            user_uid="user-123",
            amount=50.0 + (i * 25.0),
            category=["food", "transport", "education"][i],
            description=f"Test expense {i}",
            occurred_at=datetime.now() - timedelta(days=i * 2),
        )
        await event_bus.publish_async(event)

    print("✓ Published 3 ExpenseCreated events")

    # Simulate journal events
    for i in range(4):
        event = JournalCreated(
            journal_uid=f"journal-{i}",
            user_uid="user-123",
            title=f"Daily reflection {i}",
            occurred_at=datetime.now() - timedelta(days=i),
        )
        await event_bus.publish_async(event)

    print("✓ Published 4 JournalCreated events")

    # Simulate learning path completion
    event = LearningPathCompleted(
        path_uid="path-123",
        user_uid="user-123",
        occurred_at=datetime.now(),
        actual_duration_hours=20,
        estimated_duration_hours=25,
        completed_ahead_of_schedule=True,
        kus_mastered=10,
        average_mastery_score=0.88,
    )
    await event_bus.publish_async(event)

    print("✓ Published 1 LearningPathCompleted event")


# ============================================================================
# MAIN EXAMPLE RUNNER
# ============================================================================


async def main():
    """Run all examples."""

    print("\n" + "=" * 70)
    print("EVENT SYSTEM ENHANCEMENTS - COMPLETE EXAMPLE")
    print("=" * 70)

    # Mock dependencies (in real usage, these come from bootstrap)
    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j.universal_backend import get_driver

    driver = get_driver()
    event_bus = InMemoryEventBus()

    # Wire enhanced event system
    event_logger, analytics = await wire_enhanced_event_system(event_bus, driver)

    # Simulate some events for testing
    await simulate_events_for_testing(event_bus)

    # Wait a bit for async event handling
    await asyncio.sleep(0.5)

    # Run examples
    await example_event_logging(event_logger)
    await example_event_replay(event_logger)
    await example_learning_velocity(analytics)
    await example_spending_patterns(analytics)
    await example_mood_analysis(analytics)
    await example_financial_goal_tracking(analytics)
    await example_event_export(event_logger)

    print("\n" + "=" * 70)
    print("✅ All examples completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())


# ============================================================================
# KEY TAKEAWAYS
# ============================================================================

"""
Key Takeaways - Event System Enhancements
==========================================

1. **Event Logging is Automatic**
   - Subscribe EventLogger to all events
   - Full audit trail with zero service changes
   - Query events by user, entity, type, date range

2. **Event Replay for Debugging**
   - Reproduce bugs by replaying event sequences
   - Rebuild state after data loss
   - Migrate data by replaying with new handlers

3. **Cross-Domain Analytics Built on Events**
   - Learning velocity from KnowledgeMastered events
   - Spending patterns from ExpenseCreated events
   - Mood analysis from JournalCreated events
   - Financial goals from Expense + Goal events

4. **Zero Service Coupling**
   - Analytics service never calls other services
   - All data comes from event subscriptions
   - Can enable/disable by subscribing/unsubscribing

5. **Event Export for External Analysis**
   - Export to JSON, CSV, NDJSON
   - Stream to analytics platforms
   - Integrate with BI tools

6. **Extensibility**
   - Add new analytics by subscribing to events
   - No changes to existing services
   - Event-driven architecture enables easy feature addition

Example Use Cases
-----------------

1. **Debugging Task Completion Issues**
   ```python
   # Replay all task events for a specific user
   await event_logger.replay_events(
       filters={'user_uid': 'user-123', 'event_type': 'task.completed'},
       handler=debug_handler
   )
   ```

2. **Tracking Learning Progress**
   ```python
   # Get learning velocity (built from events)
   velocity = await analytics.get_learning_velocity('user-123', days_back=30)
   print(f"Learning {velocity.kus_mastered_per_week} KUs per week")
   ```

3. **Financial Goal Monitoring**
   ```python
   # See expenses linked to a goal
   metrics = await analytics.get_financial_goal_metrics('goal-789')
   print(f"Spent ${metrics.total_expenses} of ${metrics.budget_allocated}")
   ```

4. **Mood Tracking via Journals**
   ```python
   # Analyze mood from journal entries
   mood = await analytics.get_mood_analysis('user-123', days_back=30)
   print(f"Average mood: {mood.average_mood}, trend: {mood.mood_trend}")
   ```

Bootstrap Integration
--------------------

Add to services_bootstrap.py:

```python
# Phase 3.5: Wire Enhanced Event System
event_logger = EventLoggerService(driver)
analytics = CrossDomainAnalyticsService(driver)

# Subscribe to all events for logging
for event_class in ALL_EVENTS:
    event_bus.subscribe(event_class, event_logger.log_event)

# Subscribe to specific events for analytics
event_bus.subscribe(ExpenseCreated, analytics.handle_expense_created)
event_bus.subscribe(KnowledgeMastered, analytics.handle_knowledge_mastered)
event_bus.subscribe(JournalCreated, analytics.handle_journal_created)
# ... etc

logger.info("✅ Enhanced event system wired (logging + analytics)")
```

That's it! No service modifications needed - everything works through events!
"""
