"""Integration test for TasksService analytics methods.

January 2026: TasksAnalyticsService removed.
- Task model analysis methods moved to TasksIntelligenceService
- KU analytics methods implemented directly in TasksService
"""


def test_import_tasks_service():
    """Test 1: Import TasksService facade"""
    from core.services.tasks_service import TasksService

    assert TasksService is not None


def test_import_tasks_intelligence_service():
    """Test 2: Import TasksIntelligenceService (replaces TasksAnalyticsService)"""
    from core.services.tasks import TasksIntelligenceService

    assert TasksIntelligenceService is not None


def test_analytics_methods_exist():
    """Test 3: Verify analytics methods exist in facade.

    January 2026: Methods restructured after TasksAnalyticsService removal.
    - Task model analysis: TasksIntelligenceService
    - KU analytics: TasksService direct
    """
    from core.services.tasks_service import TasksService

    # Methods that remain on TasksService (now direct calls to AnalyticsEngine)
    ku_analytics_methods = [
        "analyze_learning_patterns",
        "calculate_knowledge_aware_priorities",
        "generate_task_insights",
        "track_knowledge_mastery_progression",
        "_trigger_knowledge_generation",
        "trigger_manual_knowledge_generation",
    ]

    for method in ku_analytics_methods:
        assert hasattr(TasksService, method), f"Missing method: {method}"


def test_intelligence_methods_exist():
    """Test 4: Verify Task model analysis methods moved to TasksIntelligenceService."""
    from core.services.tasks import TasksIntelligenceService

    # Methods moved from TasksAnalyticsService to TasksIntelligenceService
    task_model_methods = [
        "analyze_task_learning_metrics",
        "generate_task_knowledge_insights",
    ]

    for method in task_model_methods:
        assert hasattr(TasksIntelligenceService, method), f"Missing method: {method}"


def test_method_signatures():
    """Test 5: Check method signatures are preserved through explicit facade delegation.

    TasksService facade uses explicit async def delegation methods (February 2026)
    to preserve method signatures from the underlying sub-service implementations.
    """
    import inspect

    from core.services.tasks_service import TasksService

    # Check signatures are preserved on the facade
    method_checks = {
        "analyze_learning_patterns": ["user_uid", "timeframe_days"],
        "calculate_knowledge_aware_priorities": ["user_uid", "task_uids"],
        "generate_task_insights": ["user_uid", "timeframe_days"],
    }

    for method_name, expected_params in method_checks.items():
        method = getattr(TasksService, method_name)
        sig = inspect.signature(method)
        params = [p for p in sig.parameters if p != "self"]

        # Check all expected params are present
        for expected in expected_params:
            assert expected in params, f"{method_name} missing parameter: {expected}"
