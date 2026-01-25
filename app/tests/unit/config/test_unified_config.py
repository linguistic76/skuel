"""
Tests for Unified Configuration System.

Tests cover:
1. Environment enum
2. Config dataclasses (APIConfig, DatabaseConfig, CacheConfig, etc.)
3. from_env() classmethods
4. UnifiedConfig.from_environment() with environment-specific settings
5. UnifiedConfig.validate()
6. UnifiedConfig.to_dict()
7. create_config() factory function
8. VaultConfig properties
"""

import os
from pathlib import Path
from unittest.mock import patch

from core.config.unified_config import (
    APIConfig,
    AskesisConfig,
    CacheConfig,
    DatabaseConfig,
    Environment,
    GraphQLConfig,
    KnowledgeConfig,
    MessageQueueConfig,
    SchemaVersion,
    SearchConfig,
    UnifiedConfig,
    VaultConfig,
    create_config,
    create_development_config,
    create_production_config,
    create_test_config,
)


class TestEnvironmentEnum:
    """Tests for Environment enum."""

    def test_all_environments_defined(self):
        """Test that all expected environments exist."""
        assert Environment.LOCAL.value == "local"
        assert Environment.DEVELOPMENT.value == "development"
        assert Environment.STAGING.value == "staging"
        assert Environment.PRODUCTION.value == "production"
        assert Environment.TEST.value == "test"

    def test_environment_is_string_enum(self):
        """Test that Environment inherits from str."""
        assert isinstance(Environment.LOCAL, str)
        assert Environment.LOCAL == "local"

    def test_environment_count(self):
        """Test there are exactly 5 environments."""
        assert len(Environment) == 5


class TestSchemaVersion:
    """Tests for SchemaVersion enum."""

    def test_schema_versions_defined(self):
        """Test schema versions exist."""
        assert SchemaVersion.V3_0.value == "3.0"
        assert SchemaVersion.V3_1.value == "3.1"


class TestAPIConfig:
    """Tests for APIConfig dataclass."""

    def test_default_values(self):
        """Test APIConfig has correct defaults."""
        config = APIConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.debug is False
        assert config.reload is False
        assert config.api_prefix == "/api"

    def test_rate_limit_defaults(self):
        """Test rate limiting defaults."""
        config = APIConfig()
        assert config.rate_limit_enabled is True
        assert config.rate_limit_requests == 100
        assert config.rate_limit_period == 60

    def test_from_env_reads_environment(self):
        """Test from_env reads environment variables."""
        with patch.dict(
            os.environ,
            {
                "API_HOST": "192.168.1.1",
                "API_PORT": "9000",
                "API_DEBUG": "true",
                "API_RELOAD": "true",
            },
        ):
            config = APIConfig.from_env()
            assert config.host == "192.168.1.1"
            assert config.port == 9000
            assert config.debug is True
            assert config.reload is True

    def test_from_env_uses_defaults(self):
        """Test from_env uses defaults when env vars not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove potentially set env vars
            for key in ["API_HOST", "API_PORT", "API_DEBUG", "API_RELOAD"]:
                os.environ.pop(key, None)

            config = APIConfig.from_env()
            assert config.host == "0.0.0.0"
            assert config.port == 8000


class TestDatabaseConfig:
    """Tests for DatabaseConfig dataclass."""

    def test_default_values(self):
        """Test DatabaseConfig has correct defaults."""
        config = DatabaseConfig()
        assert config.neo4j_database == "neo4j"
        assert config.max_connection_pool_size == 50
        assert config.connection_timeout == 30.0
        assert config.encrypted is False

    def test_from_env_reads_environment(self):
        """Test from_env reads NEO4J_* environment variables."""
        with (
            patch.dict(
                os.environ,
                {
                    "NEO4J_URI": "neo4j://testhost:7688",
                    "NEO4J_USERNAME": "test_user",
                    "NEO4J_DATABASE": "test_db",
                    "NEO4J_MAX_CONNECTION_POOL_SIZE": "100",
                    "NEO4J_ENCRYPTED": "true",
                },
            ),
            patch("core.config.unified_config._get_neo4j_password", return_value="test_pass"),
        ):
            config = DatabaseConfig.from_env()
            assert config.neo4j_uri == "neo4j://testhost:7688"
            assert config.neo4j_username == "test_user"
            assert config.neo4j_database == "test_db"
            assert config.max_connection_pool_size == 100
            assert config.encrypted is True


class TestCacheConfig:
    """Tests for CacheConfig dataclass."""

    def test_default_values(self):
        """Test CacheConfig has correct defaults."""
        config = CacheConfig()
        assert config.enabled is True
        assert config.provider == "memory"
        assert config.redis_host == "localhost"
        assert config.redis_port == 6379
        assert config.default_ttl == 3600

    def test_feature_specific_ttls(self):
        """Test feature-specific TTL defaults."""
        config = CacheConfig()
        assert config.search_cache_ttl == 1800  # 30 minutes
        assert config.user_context_ttl == 86400  # 24 hours
        assert config.facet_cache_ttl == 3600  # 1 hour


class TestSearchConfig:
    """Tests for SearchConfig dataclass."""

    def test_default_values(self):
        """Test SearchConfig has correct defaults."""
        config = SearchConfig()
        assert config.default_limit == 25
        assert config.max_limit == 100
        assert config.min_query_length == 2
        assert config.max_query_length == 500
        assert config.enable_cross_domain is True


class TestVaultConfig:
    """Tests for VaultConfig dataclass."""

    def test_vault_path_property(self):
        """Test vault_path returns Path object."""
        config = VaultConfig(vault_root="/test/vault")
        assert isinstance(config.vault_path, Path)
        assert str(config.vault_path) == "/test/vault"

    def test_import_export_paths(self):
        """Test import_path and export_path are computed correctly."""
        config = VaultConfig(vault_root="/test/vault")
        assert config.import_path == Path("/test/vault/neo4j/import")
        assert config.export_path == Path("/test/vault/neo4j/export")

    def test_from_env_reads_environment(self):
        """Test from_env reads VAULT_* environment variables."""
        with patch.dict(
            os.environ,
            {
                "VAULT_ROOT": "/custom/vault",
                "VAULT_ENABLED": "false",
                "AUTO_SYNC_VAULT": "false",
                "WATCH_VAULT": "true",
                "SYNC_INTERVAL_MINUTES": "60",
            },
        ):
            config = VaultConfig.from_env()
            assert config.vault_root == "/custom/vault"
            assert config.vault_enabled is False
            assert config.auto_sync is False
            assert config.watch_vault is True
            assert config.sync_interval_minutes == 60


class TestUnifiedConfig:
    """Tests for UnifiedConfig dataclass."""

    def test_default_environment_is_local(self):
        """Test default environment is LOCAL."""
        config = UnifiedConfig()
        assert config.environment == Environment.LOCAL

    def test_contains_all_sub_configs(self):
        """Test UnifiedConfig contains all sub-configurations."""
        config = UnifiedConfig()
        assert isinstance(config.api, APIConfig)
        assert isinstance(config.graphql, GraphQLConfig)
        assert isinstance(config.database, DatabaseConfig)
        assert isinstance(config.cache, CacheConfig)
        assert isinstance(config.message_queue, MessageQueueConfig)
        assert isinstance(config.search, SearchConfig)
        assert isinstance(config.askesis, AskesisConfig)
        assert isinstance(config.knowledge, KnowledgeConfig)
        assert isinstance(config.vault, VaultConfig)


class TestUnifiedConfigFromEnvironment:
    """Tests for UnifiedConfig.from_environment()."""

    def test_from_environment_local(self):
        """Test local environment settings are applied."""
        # Note: _load_from_env() applies after environment settings
        # Test that environment is correctly set and log_level is applied
        # Clear LOG_LEVEL to prevent .env from overriding local settings
        with patch.dict(os.environ, {"API_DEBUG": "true", "API_RELOAD": "true", "LOG_LEVEL": ""}):
            config = UnifiedConfig.from_environment(Environment.LOCAL)
            assert config.environment == Environment.LOCAL
            assert config.application.log_level == "DEBUG"
            assert config.features.enable_experimental_features is True

    def test_from_environment_production(self):
        """Test production environment settings are applied."""
        with patch("core.config.unified_config._get_neo4j_password", return_value=""):
            config = UnifiedConfig.from_environment(Environment.PRODUCTION)
            assert config.environment == Environment.PRODUCTION
            # Production settings that survive _load_from_env
            assert config.cache.provider == "redis"
            assert config.application.enable_auth is True
            assert config.features.enable_experimental_features is False

    def test_from_environment_development(self):
        """Test development environment settings are applied."""
        with patch("core.config.unified_config._get_neo4j_password", return_value=""):
            with patch.dict(os.environ, {"API_DEBUG": "true", "API_RELOAD": "true"}):
                config = UnifiedConfig.from_environment(Environment.DEVELOPMENT)
                assert config.environment == Environment.DEVELOPMENT
                assert config.application.debug is True
                assert config.features.enable_experimental_features is True
                assert config.features.enable_beta_features is True

    def test_from_environment_test(self):
        """Test test environment settings are applied."""
        with patch("core.config.unified_config._get_neo4j_password", return_value=""):
            config = UnifiedConfig.from_environment(Environment.TEST)
            assert config.environment == Environment.TEST
            assert config.cache.enabled is False
            assert config.dependencies.use_mock_services is True
            assert config.dependencies.repository_provider == "memory"

    def test_from_environment_staging(self):
        """Test staging environment settings are applied."""
        with patch("core.config.unified_config._get_neo4j_password", return_value=""):
            config = UnifiedConfig.from_environment(Environment.STAGING)
            assert config.environment == Environment.STAGING
            assert config.features.enable_beta_features is True


class TestUnifiedConfigValidation:
    """Tests for UnifiedConfig.validate()."""

    def test_validate_passes_valid_config(self):
        """Test validation passes for valid config."""
        config = UnifiedConfig()
        config.database.neo4j_uri = "neo4j://localhost:7687"
        config.api.port = 8000
        config.search.default_limit = 25
        config.search.max_limit = 100
        errors = config.validate()
        assert errors == []

    def test_validate_fails_missing_database_uri(self):
        """Test validation fails when database URI is missing."""
        config = UnifiedConfig()
        config.database.neo4j_uri = ""
        errors = config.validate()
        assert "Database URI is required" in errors

    def test_validate_fails_invalid_port(self):
        """Test validation fails for invalid port."""
        config = UnifiedConfig()
        config.api.port = 0
        errors = config.validate()
        assert any("Invalid API port" in e for e in errors)

        config.api.port = 70000
        errors = config.validate()
        assert any("Invalid API port" in e for e in errors)

    def test_validate_fails_search_limit_mismatch(self):
        """Test validation fails when max_limit < default_limit."""
        config = UnifiedConfig()
        config.search.default_limit = 100
        config.search.max_limit = 50
        errors = config.validate()
        assert any("max_limit must be >= default_limit" in e for e in errors)


class TestUnifiedConfigToDict:
    """Tests for UnifiedConfig.to_dict()."""

    def test_to_dict_returns_dict(self):
        """Test to_dict returns a dictionary."""
        config = UnifiedConfig()
        result = config.to_dict()
        assert isinstance(result, dict)

    def test_to_dict_contains_expected_keys(self):
        """Test to_dict contains expected keys."""
        config = UnifiedConfig()
        result = config.to_dict()
        assert "environment" in result
        assert "schema_version" in result
        assert "api" in result
        assert "database" in result
        assert "cache" in result
        assert "features" in result

    def test_to_dict_environment_is_string(self):
        """Test environment is serialized as string value."""
        config = UnifiedConfig()
        result = config.to_dict()
        assert result["environment"] == "local"


class TestCreateConfigFactory:
    """Tests for create_config() factory function."""

    def test_create_config_returns_unified_config(self):
        """Test create_config returns UnifiedConfig instance."""
        with patch("core.config.unified_config._get_neo4j_password", return_value=""):
            config = create_config(Environment.LOCAL)
            assert isinstance(config, UnifiedConfig)

    def test_create_config_defaults_to_local(self):
        """Test create_config defaults to LOCAL environment."""
        with patch.dict(os.environ, {"SKUEL_ENVIRONMENT": "local"}):
            with patch("core.config.unified_config._get_neo4j_password", return_value=""):
                config = create_config()
                assert config.environment == Environment.LOCAL

    def test_create_config_reads_environment_variable(self):
        """Test create_config reads SKUEL_ENVIRONMENT."""
        with patch.dict(os.environ, {"SKUEL_ENVIRONMENT": "production"}):
            with patch("core.config.unified_config._get_neo4j_password", return_value=""):
                config = create_config()
                assert config.environment == Environment.PRODUCTION


class TestConvenienceFactories:
    """Tests for convenience factory functions."""

    def test_create_test_config(self):
        """Test create_test_config creates TEST environment config."""
        with patch("core.config.unified_config._get_neo4j_password", return_value=""):
            config = create_test_config()
            assert config.environment == Environment.TEST

    def test_create_development_config(self):
        """Test create_development_config creates DEVELOPMENT environment config."""
        with patch("core.config.unified_config._get_neo4j_password", return_value=""):
            config = create_development_config()
            assert config.environment == Environment.DEVELOPMENT

    def test_create_production_config(self):
        """Test create_production_config creates PRODUCTION environment config."""
        with patch("core.config.unified_config._get_neo4j_password", return_value=""):
            config = create_production_config()
            assert config.environment == Environment.PRODUCTION
