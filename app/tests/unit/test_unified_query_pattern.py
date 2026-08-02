"""
Test unified query pattern for meta-services.

Verifies that the unified query API works correctly for Tasks and Events domains.

Test Coverage:
1. build_user_activity_query() - Core helper
2. TasksService.get_user_items_in_range() - Tasks domain
3. EventsService.get_user_items_in_range() - Events domain

Proof of Concept (October 29, 2025)
"""

from datetime import date

import pytest

from adapters.persistence.neo4j.query import build_user_activity_query
from core.models.enums import EntityStatus


class TestUnifiedQueryPattern:
    """Test unified query pattern across domains."""

    def test_build_user_activity_query_basic(self):
        """Test basic query generation for Tasks."""
        query, params = build_user_activity_query(
            user_uid="user_mike",
            node_label="Task",
            date_field="due_date",
            start_date=date(2025, 10, 1),
            end_date=date(2025, 10, 31),
            exclude_statuses=["completed"],
        )

        # Verify query structure
        assert "MATCH (n:Task)" in query
        assert "WHERE n.user_uid = $user_uid" in query
        # date(left(toString(...), 10)) coercion — tolerant of date-only strings,
        # datetime strings (which bare date() throws on, #766), and temporal types.
        assert "date(left(toString(n.due_date), 10)) >= date($start_date)" in query
        assert "date(left(toString(n.due_date), 10)) <= date($end_date)" in query
        assert "NOT n.status IN $exclude_statuses" in query
        assert "RETURN n" in query
        assert "ORDER BY n.created_at DESC" in query
        assert "LIMIT $limit" in query

        # Verify parameters
        assert params["user_uid"] == "user_mike"
        assert params["start_date"] == "2025-10-01"
        assert params["end_date"] == "2025-10-31"
        assert params["exclude_statuses"] == ["completed"]
        assert params["limit"] == 100

    def test_build_user_activity_query_events(self):
        """Test query generation for Events."""
        query, params = build_user_activity_query(
            user_uid="user_mike",
            node_label="Event",
            date_field="event_date",
            start_date=date(2025, 10, 1),
            end_date=date(2025, 10, 31),
            exclude_statuses=["completed", "cancelled"],
        )

        # Verify Event-specific query
        assert "MATCH (n:Event)" in query
        assert "date(left(toString(n.event_date), 10)) >= date($start_date)" in query
        assert "date(left(toString(n.event_date), 10)) <= date($end_date)" in query
        assert params["exclude_statuses"] == ["completed", "cancelled"]

    def test_build_user_activity_query_no_date_filtering(self):
        """Test query without date filtering (all items)."""
        query, _params = build_user_activity_query(
            user_uid="user_mike",
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
            user_uid="user_mike",
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

    def test_build_user_activity_query_multi_field_or(self):
        """Multiple date fields OR together — each through the #766 idiom (act-from C2)."""
        query, params = build_user_activity_query(
            user_uid="user_mike",
            node_label="Task",
            date_field=["due_date", "scheduled_date"],
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            exclude_statuses=["completed"],
        )

        # EVERY field goes through the date(left(toString(...), 10)) idiom
        assert "date(left(toString(n.due_date), 10)) >= date($start_date)" in query
        assert "date(left(toString(n.due_date), 10)) <= date($end_date)" in query
        assert "date(left(toString(n.scheduled_date), 10)) >= date($start_date)" in query
        assert "date(left(toString(n.scheduled_date), 10)) <= date($end_date)" in query

        # OR semantics between the per-field range groups, parenthesized so the
        # OR cannot leak into the surrounding AND chain (user_uid / status filters)
        assert (
            "((date(left(toString(n.due_date), 10)) >= date($start_date)"
            " AND date(left(toString(n.due_date), 10)) <= date($end_date))"
            " OR (date(left(toString(n.scheduled_date), 10)) >= date($start_date)"
            " AND date(left(toString(n.scheduled_date), 10)) <= date($end_date)))" in query
        )
        assert "WHERE n.user_uid = $user_uid AND ((" in query
        assert ")) AND NOT n.status IN $exclude_statuses" in query

        # Date VALUES stay driver parameters (CYP003)
        assert "2026-08" not in query
        assert params["start_date"] == "2026-08-01"
        assert params["end_date"] == "2026-08-31"

    def test_build_user_activity_query_single_field_list_matches_string(self):
        """A one-element list is the same query as the plain-string shape."""
        query_str, params_str = build_user_activity_query(
            user_uid="user_mike",
            node_label="Task",
            date_field="due_date",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            exclude_statuses=["completed"],
        )
        query_list, params_list = build_user_activity_query(
            user_uid="user_mike",
            node_label="Task",
            date_field=["due_date"],
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            exclude_statuses=["completed"],
        )
        assert query_str == query_list
        assert params_str == params_list

    def test_build_user_activity_query_validates_every_field(self):
        """EVERY field in a multi-field list is identifier-validated (injection guard)."""
        with pytest.raises(ValueError, match="date field"):
            build_user_activity_query(
                user_uid="user_mike",
                node_label="Task",
                date_field=["due_date", "scheduled_date) OR true // "],
                start_date=date(2026, 8, 1),
                end_date=date(2026, 8, 31),
                exclude_statuses=[],
            )

    def test_build_user_activity_query_empty_field_list_means_no_date_filter(self):
        """An empty list behaves like date_field=None — no date clause at all."""
        query, params = build_user_activity_query(
            user_uid="user_mike",
            node_label="Task",
            date_field=[],
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
            exclude_statuses=[],
        )
        assert "date(" not in query
        assert "start_date" not in params
        assert "end_date" not in params

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
            ("Choice", "decision_date"),
            ("Principle", None),  # Principles don't have date filtering
        ]

        for node_label, date_field in domains:
            query, _params = build_user_activity_query(
                user_uid="user_mike",
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
                assert f"date(left(toString(n.{date_field}), 10)) >= date($start_date)" in query
                assert f"date(left(toString(n.{date_field}), 10)) <= date($end_date)" in query


@pytest.mark.asyncio
class TestUnifiedQueryIntegration:
    """Integration tests for unified query pattern."""

    async def test_tasks_service_has_unified_interface(self):
        """Verify TasksService exposes get_user_items_in_range() with preserved signature."""
        import inspect

        from core.services.tasks_service import TasksService

        # Verify method exists on facade
        assert hasattr(TasksService, "get_user_items_in_range")

        # Verify method signature is preserved through explicit facade delegation
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

        # Verify method signature is preserved through explicit facade delegation
        sig = inspect.signature(EventsService.get_user_items_in_range)
        params = list(sig.parameters.keys())

        assert "user_uid" in params
        assert "start_date" in params
        assert "end_date" in params
        assert "include_completed" in params


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
