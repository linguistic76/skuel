"""
Tests for SKUEL Configuration Settings.

Tests cover:
1. get_settings() - Main settings accessor with caching
2. Config accessor functions (get_api_config, get_database_config, etc.)
3. Environment detection helpers (is_production, is_development, etc.)
4. Quick access helpers (neo4j_uri, api_port, etc.)
5. reload_config() - Cache clearing
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear all cached configs before and after each test."""
    from core.config import settings

    settings.reload_config()
    yield
    settings.reload_config()


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
        GenAIConfig,
        GraphQLConfig,
        KnowledgeConfig,
        MessageQueueConfig,
        SearchConfig,
        VaultConfig,
    )

    mock_config = MagicMock()
    mock_config.environment = Environment.LOCAL
    mock_config.api = APIConfig(host="127.0.0.1", port=8080)
    mock_config.graphql = GraphQLConfig(enabled=True)
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
    mock_config.genai = GenAIConfig(embedding_dimension=1536)
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

    # Set defaults for mocked objects
    if hasattr(mock_config.search, "default_limit"):
        mock_config.search.default_limit = 20
    else:
        mock_config.search = MagicMock(default_limit=20)

    if hasattr(mock_config.askesis, "max_facet_history"):
        mock_config.askesis.max_facet_history = 10
    else:
        mock_config.askesis = MagicMock(max_facet_history=10)

    if hasattr(mock_config.application, "name"):
        pass
    else:
        mock_config.application = MagicMock(
            name="SKUEL",
            version="1.0.0",
            log_level="INFO",
            debug=False,
            features={},
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


class TestConfigAccessors:
    """Tests for configuration accessor functions."""

    def test_get_api_config(self, mock_unified_config):
        """Test get_api_config returns APIConfig."""
        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import get_api_config

                api_config = get_api_config()
                assert api_config.host == "127.0.0.1"
                assert api_config.port == 8080

    def test_get_database_config(self, mock_unified_config):
        """Test get_database_config returns DatabaseConfig."""
        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import get_database_config

                db_config = get_database_config()
                assert db_config.neo4j_uri == "neo4j://localhost:7687"
                assert db_config.neo4j_username == "neo4j"

    def test_get_cache_config(self, mock_unified_config):
        """Test get_cache_config returns CacheConfig."""
        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import get_cache_config

                cache_config = get_cache_config()
                assert cache_config.redis_host == "localhost"
                assert cache_config.redis_port == 6379

    def test_get_graphql_config(self, mock_unified_config):
        """Test get_graphql_config returns GraphQLConfig."""
        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import get_graphql_config

                gql_config = get_graphql_config()
                assert gql_config.enabled is True


class TestEnvironmentDetection:
    """Tests for environment detection helpers."""

    def test_is_local_true(self, mock_unified_config):
        """Test is_local returns True when environment is LOCAL."""
        from core.config.unified_config import Environment

        mock_unified_config.environment = Environment.LOCAL

        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import is_local

                assert is_local() is True

    def test_is_development_true(self, mock_unified_config):
        """Test is_development returns True when environment is DEVELOPMENT."""
        from core.config.unified_config import Environment

        mock_unified_config.environment = Environment.DEVELOPMENT

        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import is_development

                assert is_development() is True

    def test_is_production_true(self, mock_unified_config):
        """Test is_production returns True when environment is PRODUCTION."""
        from core.config.unified_config import Environment

        mock_unified_config.environment = Environment.PRODUCTION

        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import is_production

                assert is_production() is True

    def test_is_testing_true(self, mock_unified_config):
        """Test is_testing returns True when environment is TEST."""
        from core.config.unified_config import Environment

        mock_unified_config.environment = Environment.TEST

        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import is_testing

                assert is_testing() is True

    def test_is_staging_true(self, mock_unified_config):
        """Test is_staging returns True when environment is STAGING."""
        from core.config.unified_config import Environment

        mock_unified_config.environment = Environment.STAGING

        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import is_staging

                assert is_staging() is True

    def test_environment_detection_false_when_different(self, mock_unified_config):
        """Test that environment checks return False for non-matching environments."""
        from core.config.unified_config import Environment

        mock_unified_config.environment = Environment.LOCAL

        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import is_production, is_staging, is_testing

                assert is_production() is False
                assert is_staging() is False
                assert is_testing() is False


class TestQuickAccessHelpers:
    """Tests for quick access helper functions."""

    def test_neo4j_uri_helper(self, mock_unified_config):
        """Test neo4j_uri returns correct URI."""
        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import neo4j_uri

                assert neo4j_uri() == "neo4j://localhost:7687"

    def test_neo4j_username_helper(self, mock_unified_config):
        """Test neo4j_username returns correct username."""
        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import neo4j_username

                assert neo4j_username() == "neo4j"

    def test_neo4j_password_helper(self, mock_unified_config):
        """Test neo4j_password returns correct password."""
        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import neo4j_password

                assert neo4j_password() == "test_password"

    def test_api_port_helper(self, mock_unified_config):
        """Test api_port returns correct port."""
        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import api_port

                assert api_port() == 8080

    def test_api_host_helper(self, mock_unified_config):
        """Test api_host returns correct host."""
        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import api_host

                assert api_host() == "127.0.0.1"

    def test_redis_url_construction_no_password(self, mock_unified_config):
        """Test redis_url constructs correct URL without password."""
        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import redis_url

                url = redis_url()
                assert url == "redis://localhost:6379/0"

    def test_redis_url_construction_with_password(self, mock_unified_config):
        """Test redis_url constructs correct URL with password."""
        mock_unified_config.cache.redis_password = "secret"

        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import redis_url

                url = redis_url()
                assert url == "redis://:secret@localhost:6379/0"

    def test_embedding_dimension_default(self, mock_unified_config):
        """Test embedding_dimension returns OpenAI default."""
        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import embedding_dimension

                # Default for text-embedding-3-small
                assert embedding_dimension() == 1536


class TestReloadConfig:
    """Tests for reload_config()."""

    def test_reload_clears_all_caches(self, mock_unified_config):
        """Test that reload_config clears all cached configs."""
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


class TestFeatureFlags:
    """Tests for feature flag helpers."""

    def test_is_feature_enabled_true(self, mock_unified_config):
        """Test is_feature_enabled returns True for enabled feature."""
        mock_unified_config.application.features = {"dark_mode": True}

        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import is_feature_enabled

                assert is_feature_enabled("dark_mode") is True

    def test_is_feature_enabled_false(self, mock_unified_config):
        """Test is_feature_enabled returns False for disabled feature."""
        mock_unified_config.application.features = {"dark_mode": False}

        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import is_feature_enabled

                assert is_feature_enabled("dark_mode") is False

    def test_is_feature_enabled_missing(self, mock_unified_config):
        """Test is_feature_enabled returns False for missing feature."""
        mock_unified_config.application.features = {}

        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import is_feature_enabled

                assert is_feature_enabled("nonexistent_feature") is False

    def test_get_feature_config(self, mock_unified_config):
        """Test get_feature_config returns feature configuration."""
        mock_unified_config.application.features = {
            "ai_suggestions": {"max_suggestions": 5, "enabled": True}
        }

        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import get_feature_config

                config = get_feature_config("ai_suggestions")
                assert config["max_suggestions"] == 5
                assert config["enabled"] is True

    def test_get_feature_config_missing(self, mock_unified_config):
        """Test get_feature_config returns None for missing feature."""
        mock_unified_config.application.features = {}

        with patch("core.config.settings.create_config", return_value=mock_unified_config):
            with patch("core.config.settings.validate_config", return_value=[]):
                from core.config.settings import get_feature_config

                config = get_feature_config("nonexistent")
                assert config is None
