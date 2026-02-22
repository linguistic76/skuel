"""
Test unified query pattern for meta-services.

Verifies that the unified query API works correctly for Tasks and Events domains.

Test Coverage:
1. build_user_activity_query() - Core helper
2. TasksService.get_user_items_in_range() - Tasks domain
3. EventsService.get_user_items_in_range() - Events domain

Phase 1 Proof of Concept (October 29, 2025)
"""

from datetime import date

import pytest

from core.models.enums import EntityStatus
from core.models.query import build_user_activity_query


class TestUnifiedQueryPattern:
    """Test unified query pattern across domains."""

    def test_build_user_activity_query_basic(self):
        """Test basic query generation for Tasks."""
        query, params = build_user_activity_query(
            user_uid="user.mike",
            node_label="Task",
            date_field="due_date",
            start_date=date(2025, 10, 1),
            end_date=date(2025, 10, 31),
            exclude_statuses=["completed"],
        )

        # Verify query structure
        assert "MATCH (n:Task)" in query
        assert "WHERE n.user_uid = $user_uid" in query
        assert "n.due_date >= date($start_date)" in query
        assert "n.due_date <= date($end_date)" in query
        assert "NOT n.status IN $exclude_statuses" in query
        assert "RETURN n" in query
        assert "ORDER BY n.created_at DESC" in query
        assert "LIMIT $limit" in query

        # Verify parameters
        assert params["user_uid"] == "user.mike"
        assert params["start_date"] == "2025-10-01"
        assert params["end_date"] == "2025-10-31"
        assert params["exclude_statuses"] == ["completed"]
        assert params["limit"] == 100

    def test_build_user_activity_query_events(self):
        """Test query generation for Events."""
        query, params = build_user_activity_query(
            user_uid="user.mike",
            node_label="Event",
            date_field="event_date",
            start_date=date(2025, 10, 1),
            end_date=date(2025, 10, 31),
            exclude_statuses=["completed", "cancelled"],
        )

        # Verify Event-specific query
        assert "MATCH (n:Event)" in query
        assert "n.event_date >= date($start_date)" in query
        assert "n.event_date <= date($end_date)" in query
        assert params["exclude_statuses"] == ["completed", "cancelled"]

    def test_build_user_activity_query_no_date_filtering(self):
        """Test query without date filtering (all items)."""
        query, params = build_user_activity_query(
            user_uid="user.mike",
            node_label="Habit",
            date_field=None,  # No date filtering
            start_date=None,
            end_date=None,
            exclude_statuses=[],
        )

        # Should only filter by user_uid
        assert "MATCH (n:Habit)" in query
        assert "WHERE n.user_uid = $user_uid" in query
        assert "date(" not in query  # No date filtering
        assert "NOT n.status" not in query  # No status filtering

    def test_build_user_activity_query_include_completed(self):
        """Test query that includes completed items."""
        query, params = build_user_activity_query(
            user_uid="user.mike",
            node_label="Task",
            date_field="due_date",
            start_date=date(2025, 10, 1),
            end_date=date(2025, 10, 31),
            exclude_statuses=[],  # Include completed
        )

        # Should not have status filtering
        assert "NOT n.status" not in query
        assert "exclude_statuses" not in params

    def test_activity_status_values_for_tasks(self):
        """Verify EntityStatus enum values for Tasks."""
        # Tasks exclude COMPLETED when include_completed=False
        exclude_statuses = [EntityStatus.COMPLETED.value]
        assert exclude_statuses == ["completed"]

    def test_activity_status_values_for_events(self):
        """Verify EntityStatus enum values for Events."""
        # Events exclude COMPLETED and CANCELLED
        exclude_statuses = [EntityStatus.COMPLETED.value, EntityStatus.CANCELLED.value]
        assert exclude_statuses == ["completed", "cancelled"]

    def test_query_parameter_injection_safety(self):
        """Verify queries use parameterization (no SQL injection risk)."""
        query, params = build_user_activity_query(
            user_uid="user.mike'; DROP DATABASE; --",
            node_label="Task",
            date_field="due_date",
            start_date=date(2025, 10, 1),
            end_date=date(2025, 10, 31),
            exclude_statuses=["completed"],
        )

        # User input should be parameterized (not in query string)
        assert "DROP DATABASE" not in query
        assert "$user_uid" in query
        assert params["user_uid"] == "user.mike'; DROP DATABASE; --"

    def test_domain_consistency(self):
        """Verify all domains can use the same helper."""
        domains = [
            ("Task", "due_date"),
            ("Event", "event_date"),
            ("Habit", None),  # Habits don't have date filtering
            ("Goal", "target_date"),
            ("Expense", "expense_date"),
            ("Choice", "decision_date"),
            ("Principle", None),  # Principles don't have date filtering
        ]

        for node_label, date_field in domains:
            query, params = build_user_activity_query(
                user_uid="user.mike",
                node_label=node_label,
                date_field=date_field,
                start_date=date(2025, 10, 1) if date_field else None,
                end_date=date(2025, 10, 31) if date_field else None,
                exclude_statuses=[],
            )

            # All queries should work
            assert f"MATCH (n:{node_label})" in query
            assert "WHERE n.user_uid = $user_uid" in query

            if date_field:
                assert f"n.{date_field} >= date($start_date)" in query
                assert f"n.{date_field} <= date($end_date)" in query


@pytest.mark.asyncio
class TestUnifiedQueryIntegration:
    """Integration tests for unified query pattern."""

    async def test_tasks_service_has_unified_interface(self):
        """Verify TasksService exposes get_user_items_in_range() with preserved signature."""
        import inspect

        from core.services.tasks_service import TasksService

        # Verify method exists on facade
        assert hasattr(TasksService, "get_user_items_in_range")

        # Verify method signature is preserved through FacadeDelegationMixin
        # (requires class-level type annotations on facade)
        sig = inspect.signature(TasksService.get_user_items_in_range)
        params = list(sig.parameters.keys())

        assert "user_uid" in params
        assert "start_date" in params
        assert "end_date" in params
        assert "include_completed" in params

    async def test_events_service_has_unified_interface(self):
        """Verify EventsService exposes get_user_items_in_range() with preserved signature."""
        import inspect

        from core.services.events_service import EventsService

        # Verify method exists on facade
        assert hasattr(EventsService, "get_user_items_in_range")

        # Verify method signature is preserved through FacadeDelegationMixin
        # (requires class-level type annotations on facade)
        sig = inspect.signature(EventsService.get_user_items_in_range)
        params = list(sig.parameters.keys())

        assert "user_uid" in params
        assert "start_date" in params
        assert "end_date" in params
        assert "include_completed" in params


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
