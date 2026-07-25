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

import pytest

from core.config.unified_config import (
    APIConfig,
    AskesisConfig,
    CacheConfig,
    DatabaseConfig,
    Environment,
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
from core.config.validation import validate_config


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
        assert Environment.LOCAL == "local"  # type: ignore[comparison-overlap]

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
        """Test from_env reads the APP_* environment variables."""
        with patch.dict(
            os.environ,
            {
                "APP_HOST": "192.168.1.1",
                "APP_PORT": "9000",
                "APP_DEBUG": "true",
                "APP_RELOAD": "true",
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
            for key in ["APP_HOST", "APP_PORT", "APP_DEBUG", "APP_RELOAD"]:
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
        # Schema monitoring is opt-in (off by default).
        assert config.schema_monitoring_enabled is False
        assert config.schema_monitoring_interval == 900

    def test_schema_monitoring_defaults_off_in_from_env(self):
        """from_env leaves schema monitoring off when the env vars are unset."""
        with (
            patch.dict(os.environ, {}, clear=False),
            patch("core.config.unified_config._get_neo4j_password", return_value="test_pass"),
        ):
            # Ensure no ambient values leak in from the shell.
            for key in ("NEO4J_SCHEMA_MONITORING", "NEO4J_SCHEMA_MONITORING_INTERVAL"):
                os.environ.pop(key, None)
            config = DatabaseConfig.from_env()
            assert config.schema_monitoring_enabled is False
            assert config.schema_monitoring_interval == 900

    def test_schema_monitoring_enabled_via_env(self):
        """from_env parses the schema-monitoring opt-in flag and interval."""
        with (
            patch.dict(
                os.environ,
                {
                    "NEO4J_SCHEMA_MONITORING": "true",
                    "NEO4J_SCHEMA_MONITORING_INTERVAL": "120",
                },
            ),
            patch("core.config.unified_config._get_neo4j_password", return_value="test_pass"),
        ):
            config = DatabaseConfig.from_env()
            assert config.schema_monitoring_enabled is True
            assert config.schema_monitoring_interval == 120

    def test_schema_monitoring_rejects_non_positive_interval(self):
        """from_env fails fast on a non-positive interval (would busy-spin the poller)."""
        with (
            patch.dict(os.environ, {"NEO4J_SCHEMA_MONITORING_INTERVAL": "-5"}),
            patch("core.config.unified_config._get_neo4j_password", return_value="test_pass"),
            pytest.raises(ValueError, match="must be a positive"),
        ):
            DatabaseConfig.from_env()

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
                },
            ),
            patch("core.config.unified_config._get_neo4j_password", return_value="test_pass"),
        ):
            config = DatabaseConfig.from_env()
            assert config.neo4j_uri == "neo4j://testhost:7688"
            assert config.neo4j_username == "test_user"
            assert config.neo4j_database == "test_db"
            assert config.max_connection_pool_size == 100


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

    def test_ingestion_path_absolute(self):
        """Test ingestion_path returns absolute path from absolute ingestion_root."""
        config = VaultConfig(ingestion_root="/opt/ingestion/data")
        assert config.ingestion_path == Path("/opt/ingestion/data")

    def test_ingestion_path_relative(self):
        """Test ingestion_path resolves relative path against cwd."""
        config = VaultConfig(ingestion_root="data/vault")
        assert config.ingestion_path.is_absolute()
        assert str(config.ingestion_path).endswith("data/vault")

    def test_from_env_reads_environment(self):
        """Test from_env reads VAULT_* environment variables."""
        with patch.dict(
            os.environ,
            {
                "VAULT_ROOT": "/custom/vault",
                "VAULT_ENABLED": "false",
                "INGESTION_PATH": "/custom/ingestion",
            },
        ):
            config = VaultConfig.from_env()
            assert config.vault_root == "/custom/vault"
            assert config.vault_enabled is False
            assert config.ingestion_root == "/custom/ingestion"


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
        with patch.dict(os.environ, {"APP_DEBUG": "true", "APP_RELOAD": "true", "LOG_LEVEL": ""}):
            config = UnifiedConfig.from_environment(Environment.LOCAL)
            assert config.environment == Environment.LOCAL
            assert config.application.log_level == "DEBUG"
            assert config.features.enable_experimental_features is True

    def test_from_environment_production(self):
        """Test production environment settings are applied."""
        with patch("core.config.unified_config._get_neo4j_password", return_value=""):
            config = UnifiedConfig.from_environment(Environment.PRODUCTION)
            assert config.environment == Environment.PRODUCTION
            # Production settings that survive _load_from_env. Memory cache is
            # THE path — production no longer overrides cache.provider.
            assert config.cache.provider == "memory"
            assert config.features.enable_experimental_features is False

    def test_from_environment_development(self):
        """Test development environment settings are applied."""
        with patch("core.config.unified_config._get_neo4j_password", return_value=""):
            with patch.dict(os.environ, {"APP_DEBUG": "true", "APP_RELOAD": "true"}):
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


class TestProductionUriGuard:
    """validate_config() production Neo4j URI guard.

    TLS comes solely from the URI scheme (the driver receives no encryption
    kwarg), so SKUEL_ENVIRONMENT=production must refuse plaintext schemes.
    Fail-fast at boot: get_settings() raises on any validation error.
    """

    def _config(self, env: Environment, uri: str) -> UnifiedConfig:
        with patch("core.config.unified_config._get_neo4j_password", return_value=""):
            config = UnifiedConfig(environment=env)
        config.database.neo4j_uri = uri
        config.database.neo4j_username = "neo4j"
        config.database.neo4j_password = "test-password"
        return config

    def _uri_errors(self, env: Environment, uri: str) -> list[str]:
        errors = validate_config(self._config(env, uri))
        return [e for e in errors if "Neo4j URI" in e]

    def test_production_plaintext_bolt_fails(self):
        """Production + bolt:// fails, naming the got-scheme."""
        errors = self._uri_errors(Environment.PRODUCTION, "bolt://localhost:7687")
        assert len(errors) == 1
        assert "got 'bolt://'" in errors[0]

    def test_production_plaintext_neo4j_fails(self):
        """Production + neo4j:// (plaintext routing scheme) fails."""
        errors = self._uri_errors(Environment.PRODUCTION, "neo4j://localhost:7687")
        assert len(errors) == 1
        assert "got 'neo4j://'" in errors[0]

    def test_production_neo4j_s_passes(self):
        """Production + neo4j+s:// (AuraDB) passes."""
        uri = "neo4j+s://abcd1234.databases.neo4j.io"
        assert self._uri_errors(Environment.PRODUCTION, uri) == []

    def test_production_self_signed_schemes_pass(self):
        """Production + +ssc schemes (self-signed cert) pass."""
        assert self._uri_errors(Environment.PRODUCTION, "neo4j+ssc://host:7687") == []
        assert self._uri_errors(Environment.PRODUCTION, "bolt+ssc://host:7687") == []
        assert self._uri_errors(Environment.PRODUCTION, "bolt+s://host:7687") == []

    def test_local_plaintext_bolt_passes(self):
        """Local + bolt:// stays valid — the guard is production-only."""
        assert self._uri_errors(Environment.LOCAL, "bolt://localhost:7687") == []

    def test_staging_plaintext_bolt_passes(self):
        """Staging + bolt:// stays valid (documented rehearsal fallback)."""
        assert self._uri_errors(Environment.STAGING, "bolt://localhost:7687") == []


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
