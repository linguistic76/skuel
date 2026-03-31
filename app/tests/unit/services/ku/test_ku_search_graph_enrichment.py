"""
Unit tests for PathStep Search Graph Enrichment Patterns.

Tests that PsSearchService properly configures graph_enrichment_patterns
via DomainConfig to surface cross-domain activity applications in search results.
"""

from core.services.ps.ps_search_service import PsSearchService


class TestGraphEnrichmentPatternsConfiguration:
    """Test that graph enrichment patterns are properly configured via DomainConfig."""

    def test_graph_enrichment_patterns_configured(self):
        """Verify PsSearchService config defines graph enrichment patterns."""
        config = PsSearchService._config
        assert config.graph_enrichment_patterns is not None
        assert len(config.graph_enrichment_patterns) > 0

    def test_minimum_pattern_count(self):
        """Verify at least 9 patterns are configured."""
        config = PsSearchService._config
        assert len(config.graph_enrichment_patterns) >= 9

    def test_config_has_correct_search_fields(self):
        """Verify PsSearchService has correct search fields."""
        config = PsSearchService._config
        assert "title" in config.search_fields
        assert "intent" in config.search_fields
        assert "description" in config.search_fields

    def test_config_service_name(self):
        """Verify service name starts with 'ps'."""
        config = PsSearchService._config
        assert config.service_name == "ps.search"
