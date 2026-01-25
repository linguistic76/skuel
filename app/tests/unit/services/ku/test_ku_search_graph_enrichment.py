"""
Unit tests for KU Search Graph Enrichment Patterns (Phase 3).

Tests that KuSearchService properly configures _graph_enrichment_patterns
to surface cross-domain activity applications in search results.
"""

from core.services.ku.ku_search_service import KuSearchService


class TestGraphEnrichmentPatternsConfiguration:
    """Test that _graph_enrichment_patterns is properly configured."""

    def test_graph_enrichment_patterns_configured(self):
        """Verify KuSearchService defines graph enrichment patterns."""
        assert hasattr(KuSearchService, "_graph_enrichment_patterns")
        assert len(KuSearchService._graph_enrichment_patterns) > 0

        # Verify each pattern has correct structure (context_key, rel_type, label)
        for pattern in KuSearchService._graph_enrichment_patterns:
            assert isinstance(pattern, tuple)
            assert len(pattern) == 3

            context_key, rel_type, label = pattern
            assert isinstance(context_key, str), (
                f"context_key should be str, got {type(context_key)}"
            )
            assert isinstance(rel_type, str), f"rel_type should be str, got {type(rel_type)}"
            assert isinstance(label, str), f"label should be str, got {type(label)}"

    def test_activity_domain_patterns_included(self):
        """Verify Activity Domain relationships are configured."""
        patterns = KuSearchService._graph_enrichment_patterns
        context_keys = [p[0] for p in patterns]

        # Activity Domain applications (6 domains)
        assert "applied_in_tasks" in context_keys
        assert "required_by_goals" in context_keys
        assert "practiced_in_events" in context_keys
        assert "reinforced_by_habits" in context_keys
        assert "informs_choices" in context_keys
        assert "grounds_principles" in context_keys

    def test_curriculum_patterns_included(self):
        """Verify Curriculum relationships are configured."""
        patterns = KuSearchService._graph_enrichment_patterns
        context_keys = [p[0] for p in patterns]

        # Curriculum (LS directly, LP handled separately)
        assert "taught_in_steps" in context_keys

    def test_ku_navigation_patterns_included(self):
        """Verify KU↔KU navigation relationships are configured."""
        patterns = KuSearchService._graph_enrichment_patterns
        context_keys = [p[0] for p in patterns]

        # KU navigation
        assert "prerequisites" in context_keys
        assert "enables" in context_keys

    def test_minimum_pattern_count(self):
        """Verify at least 9 patterns are configured (8 Activity/Curriculum + KU nav)."""
        # 6 Activity Domains + 1 Curriculum (LS) + 2 KU navigation = 9 minimum
        assert len(KuSearchService._graph_enrichment_patterns) >= 9

    def test_pattern_relationship_types_are_valid(self):
        """Verify all relationship types are non-empty strings."""
        patterns = KuSearchService._graph_enrichment_patterns

        for context_key, rel_type, _label in patterns:
            assert rel_type, f"Empty relationship type for {context_key}"
            assert rel_type.isupper(), f"Relationship type should be uppercase: {rel_type}"
            assert "_" in rel_type or rel_type == "REQUIRES" or rel_type == "ENABLES", (
                f"Relationship type should be snake_case uppercase: {rel_type}"
            )

    def test_pattern_labels_are_valid(self):
        """Verify all target labels are non-empty strings."""
        patterns = KuSearchService._graph_enrichment_patterns

        valid_labels = {
            "Task",
            "Goal",
            "Event",
            "Habit",
            "Choice",
            "Principle",
            "Ku",
            "Ls",
            "Lp",
        }

        for context_key, _rel_type, label in patterns:
            assert label, f"Empty label for {context_key}"
            assert label in valid_labels, f"Invalid label '{label}' for {context_key}"

    def test_no_duplicate_context_keys(self):
        """Verify no duplicate context keys (would cause conflicts)."""
        patterns = KuSearchService._graph_enrichment_patterns
        context_keys = [p[0] for p in patterns]

        assert len(context_keys) == len(set(context_keys)), "Duplicate context keys found"
