"""
Environment Validator
=====================

Centralized configuration validation for SKUEL.
Single source of truth for all environment requirements.

Following SKUEL principle: Clear errors that help fix issues.
"""

import os
from typing import ClassVar, TypedDict

from core.config.credential_store import get_credential
from core.errors import ConfigurationError
from core.utils.logging import get_logger

logger = get_logger(__name__)


# TypedDicts for configuration structure (fixes MyPy index errors)
class Neo4jConfig(TypedDict):
    """Neo4j configuration structure."""

    uri: str
    user: str
    password: str


class ValidatedConfig(TypedDict):
    """Complete validated configuration structure."""

    openai_api_key: str
    neo4j: Neo4jConfig
    deepgram_api_key: str | None


class EnvironmentValidator:
    """
    Centralized validator for environment configuration.

    This is THE place for all environment validation.
    No scattered checks - all validation happens here.
    """

    # Required environment variables
    REQUIRED_VARS: ClassVar[dict[str, str]] = {
        "OPENAI_API_KEY": "OpenAI API key for embeddings and AI features"
    }

    # Optional but recommended variables
    RECOMMENDED_VARS: ClassVar[dict[str, str]] = {
        "NEO4J_URI": "Neo4j database URI (defaults to neo4j://localhost:7687)",
        "NEO4J_USER": "Neo4j username (defaults to neo4j)",
        "NEO4J_PASSWORD": "Neo4j password (defaults to password)",
        "DEEPGRAM_API_KEY": "Deepgram API key for audio transcription",
    }

    @classmethod
    def validate_required(cls) -> None:
        """
        Validate all required environment variables.

        Raises:
            ConfigurationError: If any required variable is missing
        """
        missing = []

        for var_name, description in cls.REQUIRED_VARS.items():
            # Check encrypted store first, then environment
            if not get_credential(var_name, fallback_to_env=True):
                missing.append(f"  • {var_name}: {description}")

        if missing:
            error_msg = (
                "Required credentials are not set:\n"
                + "\n".join(missing)
                + "\n\nTo fix this:\n"
                + "  1. Run the credential setup script:\n"
                + "     python -m core.config.credential_setup\n"
                + "  2. Or add to .env file temporarily:\n"
                + "     OPENAI_API_KEY='your-api-key'\n"
                + "  3. Credentials will be auto-migrated to encrypted store on first run\n\n"
                + "SKUEL stores all sensitive data in encrypted credential store."
            )
            logger.error(f"❌ {error_msg}")
            raise ConfigurationError(error_msg)

        logger.info("✅ All required environment variables validated")

    @classmethod
    def validate_openai(cls) -> str:
        """
        Validate and return OpenAI API key.

        Returns:
            str: The validated OpenAI API key

        Raises:
            ConfigurationError: If OPENAI_API_KEY is not set
        """
        api_key = get_credential("OPENAI_API_KEY", fallback_to_env=True)

        if not api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY is required. "
                "Set your OpenAI API key to enable SKUEL's full functionality. "
                "Export OPENAI_API_KEY='your-key' in your environment."
            )

        # Basic validation - check it's not a placeholder
        if api_key in ["your-key", "your-api-key", "test-key", ""]:
            raise ConfigurationError(
                f"OPENAI_API_KEY appears to be a placeholder: '{api_key}'. "
                "Please set a valid OpenAI API key."
            )

        if not api_key.startswith("sk-"):
            logger.warning("OPENAI_API_KEY doesn't start with 'sk-' - may not be valid")

        return api_key

    @classmethod
    def get_neo4j_config(cls) -> Neo4jConfig:
        """
        Get Neo4j configuration with defaults.

        Returns:
            Typed Neo4j configuration with uri, user, and password
        """
        return {
            "uri": os.getenv("NEO4J_URI", "neo4j://localhost:7687"),
            "user": os.getenv("NEO4J_USER", "neo4j"),
            "password": get_credential("NEO4J_PASSWORD", fallback_to_env=True) or "password",
        }

    @classmethod
    def get_deepgram_key(cls) -> str | None:
        """
        Get Deepgram API key if available.

        Returns:
            Optional[str]: Deepgram API key or None
        """
        key = get_credential("DEEPGRAM_API_KEY", fallback_to_env=True)
        if not key:
            logger.warning("DEEPGRAM_API_KEY not set - audio transcription unavailable")
        return key

    @classmethod
    def validate_all(cls) -> ValidatedConfig:
        """
        Validate all configuration and return typed config dict.

        This should be called at application startup.

        Returns:
            Typed configuration containing all validated settings

        Raises:
            ConfigurationError: If required configuration is missing
        """
        # Validate required variables
        cls.validate_required()

        # Build configuration dictionary with explicit type annotation
        config: ValidatedConfig = {
            "openai_api_key": cls.validate_openai(),
            "neo4j": cls.get_neo4j_config(),
            "deepgram_api_key": cls.get_deepgram_key(),
        }

        # Log configuration status (without exposing keys)
        logger.info("Configuration validated:")
        logger.info("  • OpenAI: Configured")
        logger.info(f"  • Neo4j: {config['neo4j']['uri']}")
        logger.info(
            f"  • Deepgram: {'Configured' if config['deepgram_api_key'] else 'Not configured'}"
        )

        return config

    @classmethod
    def check_optional(cls) -> list[str]:
        """
        Check optional/recommended variables and return warnings.

        Returns:
            List of warning messages for missing optional variables
        """
        warnings = []

        for var_name, description in cls.RECOMMENDED_VARS.items():
            if not os.getenv(var_name):
                warnings.append(f"Optional: {var_name} not set - {description}")

        for warning in warnings:
            logger.info(warning)

        return warnings


def validate_environment() -> ValidatedConfig:
    """
    Convenience function to validate environment at startup.

    Returns:
        Validated configuration dictionary,

    Raises:
        ConfigurationError: If required configuration is missing
    """
    return EnvironmentValidator.validate_all()


def get_openai_key() -> str:
    """
    Convenience function to get validated OpenAI API key.

    Returns:
        Validated OpenAI API key,

    Raises:
        ConfigurationError: If OPENAI_API_KEY is not set
    """
    return EnvironmentValidator.validate_openai()
