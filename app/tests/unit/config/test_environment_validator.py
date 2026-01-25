"""
Tests for Environment Validator.

Tests cover:
1. EnvironmentValidator.validate_required() - Required variable validation
2. EnvironmentValidator.validate_openai() - OpenAI API key validation
3. EnvironmentValidator.get_neo4j_config() - Neo4j config with defaults
4. EnvironmentValidator.get_deepgram_key() - Deepgram key retrieval
5. EnvironmentValidator.validate_all() - Complete validation
6. EnvironmentValidator.check_optional() - Optional variable warnings
7. Convenience functions - validate_environment(), get_openai_key()
"""

import os
from unittest.mock import patch

import pytest

from core.errors import ConfigurationError


@pytest.fixture
def mock_get_credential():
    """Mock get_credential to return test values."""
    with patch("core.config.environment_validator.get_credential") as mock:
        yield mock


class TestValidateRequired:
    """Tests for EnvironmentValidator.validate_required()."""

    def test_validate_required_success(self, mock_get_credential):
        """Test validation passes when all required vars are present."""
        mock_get_credential.return_value = "sk-valid-api-key"

        from core.config.environment_validator import EnvironmentValidator

        # Should not raise
        EnvironmentValidator.validate_required()

    def test_validate_required_missing_raises(self, mock_get_credential):
        """Test ConfigurationError raised when required var is missing."""
        mock_get_credential.return_value = None

        from core.config.environment_validator import EnvironmentValidator

        with pytest.raises(ConfigurationError, match="Required credentials are not set"):
            EnvironmentValidator.validate_required()

    def test_validate_required_empty_raises(self, mock_get_credential):
        """Test ConfigurationError raised when required var is empty string."""
        mock_get_credential.return_value = ""

        from core.config.environment_validator import EnvironmentValidator

        with pytest.raises(ConfigurationError):
            EnvironmentValidator.validate_required()


class TestValidateOpenai:
    """Tests for EnvironmentValidator.validate_openai()."""

    def test_validate_openai_success(self, mock_get_credential):
        """Test returns API key when valid."""
        mock_get_credential.return_value = "sk-valid-openai-key"

        from core.config.environment_validator import EnvironmentValidator

        result = EnvironmentValidator.validate_openai()
        assert result == "sk-valid-openai-key"

    def test_validate_openai_not_set_raises(self, mock_get_credential):
        """Test ConfigurationError raised when OPENAI_API_KEY not set."""
        mock_get_credential.return_value = None

        from core.config.environment_validator import EnvironmentValidator

        with pytest.raises(ConfigurationError, match="OPENAI_API_KEY is required"):
            EnvironmentValidator.validate_openai()

    def test_validate_openai_placeholder_raises(self, mock_get_credential):
        """Test ConfigurationError raised for placeholder values."""
        from core.config.environment_validator import EnvironmentValidator

        placeholders = ["your-key", "your-api-key", "test-key", ""]

        for placeholder in placeholders:
            mock_get_credential.return_value = placeholder
            with pytest.raises(ConfigurationError):
                EnvironmentValidator.validate_openai()

    def test_validate_openai_warns_invalid_format(self, mock_get_credential):
        """Test logs warning for non-sk- prefixed keys but doesn't raise."""
        mock_get_credential.return_value = "invalid-format-key"

        from core.config.environment_validator import EnvironmentValidator

        # Should return the key even though it warns
        result = EnvironmentValidator.validate_openai()
        assert result == "invalid-format-key"


class TestGetNeo4jConfig:
    """Tests for EnvironmentValidator.get_neo4j_config()."""

    def test_get_neo4j_config_defaults(self, mock_get_credential):
        """Test returns defaults when env vars not set."""
        mock_get_credential.return_value = None

        with patch.dict(os.environ, {}, clear=True):
            # Remove any NEO4J_* vars that might be set
            for key in list(os.environ.keys()):
                if key.startswith("NEO4J_"):
                    del os.environ[key]

            from core.config.environment_validator import EnvironmentValidator

            config = EnvironmentValidator.get_neo4j_config()
            assert config["uri"] == "neo4j://localhost:7687"
            assert config["user"] == "neo4j"
            assert config["password"] == "password"

    def test_get_neo4j_config_from_env(self, mock_get_credential):
        """Test reads from environment variables."""
        mock_get_credential.return_value = "secure_password"

        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "neo4j://prodhost:7687",
                "NEO4J_USER": "prod_user",
            },
        ):
            from core.config.environment_validator import EnvironmentValidator

            config = EnvironmentValidator.get_neo4j_config()
            assert config["uri"] == "neo4j://prodhost:7687"
            assert config["user"] == "prod_user"
            assert config["password"] == "secure_password"

    def test_get_neo4j_config_returns_typed_dict(self, mock_get_credential):
        """Test returns properly typed Neo4jConfig."""
        mock_get_credential.return_value = "test_pass"

        from core.config.environment_validator import EnvironmentValidator

        config = EnvironmentValidator.get_neo4j_config()
        assert "uri" in config
        assert "user" in config
        assert "password" in config


class TestGetDeepgramKey:
    """Tests for EnvironmentValidator.get_deepgram_key()."""

    def test_get_deepgram_key_present(self, mock_get_credential):
        """Test returns key when set."""
        mock_get_credential.return_value = "deepgram-api-key"

        from core.config.environment_validator import EnvironmentValidator

        result = EnvironmentValidator.get_deepgram_key()
        assert result == "deepgram-api-key"

    def test_get_deepgram_key_missing(self, mock_get_credential):
        """Test returns None and warns when not set."""
        mock_get_credential.return_value = None

        from core.config.environment_validator import EnvironmentValidator

        result = EnvironmentValidator.get_deepgram_key()
        assert result is None


class TestValidateAll:
    """Tests for EnvironmentValidator.validate_all()."""

    def test_validate_all_success(self, mock_get_credential):
        """Test returns ValidatedConfig when all validations pass."""

        def mock_credential(key, fallback_to_env=False):
            credentials = {
                "OPENAI_API_KEY": "sk-valid-openai-key",
                "NEO4J_PASSWORD": "neo4j_pass",
                "DEEPGRAM_API_KEY": "deepgram-key",
            }
            return credentials.get(key)

        mock_get_credential.side_effect = mock_credential

        # Ensure clean environment for this test
        with patch.dict(os.environ, {}, clear=False):
            # Remove Neo4j env vars that might override defaults
            for key in ["NEO4J_URI", "NEO4J_USER"]:
                os.environ.pop(key, None)

            from core.config.environment_validator import EnvironmentValidator

            result = EnvironmentValidator.validate_all()

            assert result["openai_api_key"] == "sk-valid-openai-key"
            # URI comes from environment or default
            assert "uri" in result["neo4j"]
            assert result["neo4j"]["user"] == "neo4j"
            assert result["neo4j"]["password"] == "neo4j_pass"
            assert result["deepgram_api_key"] == "deepgram-key"

    def test_validate_all_raises_on_missing_openai(self, mock_get_credential):
        """Test raises ConfigurationError when OpenAI key missing."""
        mock_get_credential.return_value = None

        from core.config.environment_validator import EnvironmentValidator

        with pytest.raises(ConfigurationError):
            EnvironmentValidator.validate_all()


class TestCheckOptional:
    """Tests for EnvironmentValidator.check_optional()."""

    def test_check_optional_all_present(self, mock_get_credential):
        """Test returns empty list when all optional vars set."""
        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "neo4j://localhost:7687",
                "NEO4J_USER": "neo4j",
                "NEO4J_PASSWORD": "password",
                "DEEPGRAM_API_KEY": "deepgram-key",
            },
        ):
            from core.config.environment_validator import EnvironmentValidator

            warnings = EnvironmentValidator.check_optional()
            assert warnings == []

    def test_check_optional_missing_returns_warnings(self, mock_get_credential):
        """Test returns warnings for missing optional vars."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear any potentially set vars
            for key in ["NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "DEEPGRAM_API_KEY"]:
                os.environ.pop(key, None)

            from core.config.environment_validator import EnvironmentValidator

            warnings = EnvironmentValidator.check_optional()
            assert len(warnings) > 0
            assert all("Optional:" in w for w in warnings)


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_validate_environment_returns_config(self, mock_get_credential):
        """Test validate_environment returns ValidatedConfig."""

        def mock_credential(key, fallback_to_env=False):
            credentials = {
                "OPENAI_API_KEY": "sk-valid-key",
                "NEO4J_PASSWORD": "pass",
                "DEEPGRAM_API_KEY": None,
            }
            return credentials.get(key)

        mock_get_credential.side_effect = mock_credential

        from core.config.environment_validator import validate_environment

        result = validate_environment()
        assert "openai_api_key" in result
        assert "neo4j" in result

    def test_get_openai_key_returns_key(self, mock_get_credential):
        """Test get_openai_key returns validated key."""
        mock_get_credential.return_value = "sk-valid-openai-key"

        from core.config.environment_validator import get_openai_key

        result = get_openai_key()
        assert result == "sk-valid-openai-key"

    def test_get_openai_key_raises_when_missing(self, mock_get_credential):
        """Test get_openai_key raises when key not set."""
        mock_get_credential.return_value = None

        from core.config.environment_validator import get_openai_key

        with pytest.raises(ConfigurationError):
            get_openai_key()


class TestRequiredVarsConstant:
    """Tests for REQUIRED_VARS class variable."""

    def test_required_vars_contains_openai(self):
        """Test REQUIRED_VARS includes OPENAI_API_KEY."""
        from core.config.environment_validator import EnvironmentValidator

        assert "OPENAI_API_KEY" in EnvironmentValidator.REQUIRED_VARS


class TestRecommendedVarsConstant:
    """Tests for RECOMMENDED_VARS class variable."""

    def test_recommended_vars_contains_neo4j(self):
        """Test RECOMMENDED_VARS includes Neo4j variables."""
        from core.config.environment_validator import EnvironmentValidator

        assert "NEO4J_URI" in EnvironmentValidator.RECOMMENDED_VARS
        assert "NEO4J_USER" in EnvironmentValidator.RECOMMENDED_VARS
        assert "NEO4J_PASSWORD" in EnvironmentValidator.RECOMMENDED_VARS

    def test_recommended_vars_contains_deepgram(self):
        """Test RECOMMENDED_VARS includes Deepgram."""
        from core.config.environment_validator import EnvironmentValidator

        assert "DEEPGRAM_API_KEY" in EnvironmentValidator.RECOMMENDED_VARS
