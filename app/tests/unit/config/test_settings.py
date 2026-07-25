"""
Tests for SKUEL Configuration Settings.

Tests cover:
1. get_settings() - Main settings accessor with caching and validation
2. reload_config() - Cache clearing
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear all cached configs before and after each test."""
    from core.config.settings import reload_config

    reload_config()
    yield
    reload_config()


@pytest.fixture
def mock_unified_config():
    """Create mock UnifiedConfig with default values."""
    from core.config.unified_config import (
        APIConfig,
        ApplicationConfig,
        AskesisConfig,
        CacheConfig,
        DatabaseConfig,
        Environment,
        KnowledgeConfig,
        MessageQueueConfig,
        SearchConfig,
        VaultConfig,
    )

    mock_config = MagicMock()
    mock_config.environment = Environment.LOCAL
    mock_config.api = APIConfig(host="127.0.0.1", port=8080)
    mock_config.database = DatabaseConfig(
        neo4j_uri="neo4j://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="test_password",
    )
    mock_config.cache = CacheConfig(
        redis_host="localhost",
        redis_port=6379,
        redis_db=0,
        redis_password=None,
    )
    mock_config.message_queue = MessageQueueConfig()
    mock_config.search = SearchConfig() if hasattr(SearchConfig, "__init__") else MagicMock()
    mock_config.askesis = AskesisConfig() if hasattr(AskesisConfig, "__init__") else MagicMock()
    mock_config.knowledge = (
        KnowledgeConfig() if hasattr(KnowledgeConfig, "__init__") else MagicMock()
    )
    mock_config.vault = VaultConfig() if hasattr(VaultConfig, "__init__") else MagicMock()
    mock_config.application = (
        ApplicationConfig() if hasattr(ApplicationConfig, "__init__") else MagicMock()
    )

    return mock_config


class TestGetSettings:
    """Tests for get_settings()."""

    def test_returns_unified_config(self, mock_unified_config):
        """Test that get_settings returns UnifiedConfig instance."""
        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import get_settings

                settings = get_settings()
                assert settings is not None
                assert settings == mock_unified_config

    def test_settings_are_cached(self, mock_unified_config):
        """Test that settings are cached (lru_cache)."""
        with (
            patch(
                "core.config.settings.create_config", return_value=mock_unified_config
            ) as mock_create,
            patch("core.config.settings.validate_config", return_value=[]),
        ):
            from core.config.settings import get_settings

            # Call twice
            settings1 = get_settings()
            settings2 = get_settings()

            # Should only create once due to caching
            assert mock_create.call_count == 1
            assert settings1 is settings2

    def test_validation_failure_raises(self, mock_unified_config):
        """Test that validation errors raise ValueError."""
        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=["Error 1", "Error 2"]):
                from core.config.settings import get_settings

                with pytest.raises(ValueError, match="Configuration validation failed"):
                    get_settings()


class TestReloadConfig:
    """Tests for reload_config()."""

    def test_reload_clears_cache(self, mock_unified_config):
        """Test that reload_config clears the cached config."""
        with (
            patch(
                "core.config.settings.create_config", return_value=mock_unified_config
            ) as mock_create,
            patch("core.config.settings.validate_config", return_value=[]),
        ):
            from core.config.settings import get_settings, reload_config

            # First call - creates config
            get_settings()
            assert mock_create.call_count == 1

            # Reload clears cache
            reload_config()

            # Second call - should create again
            get_settings()
            assert mock_create.call_count == 2
