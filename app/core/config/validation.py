"""
Configuration Validation
========================

Validates configuration values and provides error reporting.
Ensures all required settings are present and valid.
"""

__version__ = "1.0"


import re
from urllib.parse import urlparse

from core.config.unified_config import (
    APIConfig,
    AskesisConfig,
    CacheConfig,
    DatabaseConfig,
    Environment,
    KnowledgeConfig,
    SearchConfig,
    UnifiedConfig,
)
from core.utils.logging import get_logger

logger = get_logger("skuel.config.validation")


class ConfigValidator:
    """Validates configuration objects"""

    @staticmethod
    def validate_url(url: str, name: str) -> str | None:
        """Validate a URL format"""
        try:
            result = urlparse(url)
            if not all([result.scheme, result.netloc]):
                return f"{name}: Invalid URL format: {url}"
        except Exception as e:
            return f"{name}: URL parsing error: {e!s}"
        return None

    @staticmethod
    def validate_port(port: int, name: str) -> str | None:
        """Validate a port number"""
        if not 1 <= port <= 65535:
            return f"{name}: Port must be between 1 and 65535, got {port}"
        return None

    @staticmethod
    def validate_positive_int(value: int, name: str) -> str | None:
        """Validate a positive integer"""
        if value <= 0:
            return f"{name}: Must be positive, got {value}"
        return None

    @staticmethod
    def validate_percentage(value: float, name: str) -> str | None:
        """Validate a percentage value (0.0 to 1.0)"""
        if not 0.0 <= value <= 1.0:
            return f"{name}: Must be between 0.0 and 1.0, got {value}"
        return None

    @staticmethod
    def validate_non_empty_string(value: str, name: str) -> str | None:
        """Validate a non-empty string"""
        if not value or not value.strip():
            return f"{name}: Cannot be empty"
        return None

    @staticmethod
    def validate_email(email: str, name: str) -> str | None:
        """Validate email format"""
        pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        if not re.match(pattern, email):
            return f"{name}: Invalid email format: {email}"
        return None


def validate_api_config(config: APIConfig) -> list[str]:
    """Validate API configuration"""
    errors = []

    # Validate port
    error = ConfigValidator.validate_port(config.port, "API port")
    if error:
        errors.append(error)

    # Validate host
    if not config.host:
        errors.append("API host cannot be empty")

    # Validate CORS origins
    for origin in config.cors_origins:
        if origin != "*":
            error = ConfigValidator.validate_url(origin, "CORS origin")
            if error:
                errors.append(error)

    # Validate rate limits
    error = ConfigValidator.validate_positive_int(config.rate_limit_requests, "Rate limit requests")
    if error:
        errors.append(error)

    error = ConfigValidator.validate_positive_int(config.rate_limit_period, "Rate limit period")
    if error:
        errors.append(error)

    # API config doesn't have timeout or max_request_size fields in our implementation

    return errors


def validate_database_config(config: DatabaseConfig) -> list[str]:
    """Validate database configuration"""
    errors = []

    # Validate Neo4j URI
    if not config.neo4j_uri:
        errors.append("Neo4j URI is required")
    elif not config.neo4j_uri.startswith(("neo4j://", "neo4j+s://", "bolt://", "bolt+s://")):
        errors.append(f"Invalid Neo4j URI scheme: {config.neo4j_uri}")

    # Validate credentials
    if not config.neo4j_username:
        errors.append("Neo4j username is required")

    if not config.neo4j_password:
        errors.append("Neo4j password is required")

    # Database config uses max_connection_pool_size
    error = ConfigValidator.validate_positive_int(
        config.max_connection_pool_size, "Max connection pool size"
    )
    if error:
        errors.append(error)

    return errors


def validate_cache_config(config: CacheConfig) -> list[str]:
    """Validate cache configuration"""
    errors = []

    if config.enabled and config.provider == "redis" and not config.redis_host:
        # Only validate if cache is enabled
        errors.append("Redis host is required when Redis cache is enabled")

    return errors


def validate_search_config(config: SearchConfig) -> list[str]:
    """Validate search configuration"""
    errors = []

    # Validate results limit (using default_limit field)
    error = ConfigValidator.validate_positive_int(config.default_limit, "Search default limit")
    if error:
        errors.append(error)

    # Validate max limit
    error = ConfigValidator.validate_positive_int(config.max_limit, "Search max limit")
    if error:
        errors.append(error)

    return errors


def validate_askesis_config(config: AskesisConfig) -> list[str]:
    """Validate askesis configuration"""
    errors = []

    # Validate max facet history
    error = ConfigValidator.validate_positive_int(config.max_facet_history, "Max facet history")
    if error:
        errors.append(error)

    # Validate max conversation history
    error = ConfigValidator.validate_positive_int(
        config.max_conversation_history, "Max conversation history"
    )
    if error:
        errors.append(error)

    return errors


def validate_knowledge_config(_config: KnowledgeConfig) -> list[str]:
    """
    Validate knowledge configuration.

    Args:
        _config: Knowledge configuration (currently unused - reserved for future validation)

    Returns:
        List of validation errors (empty until validation rules are implemented)

    TODO: Add validation when embedding_model and embedding_dimension fields are added to KnowledgeConfig
    """
    # For now, knowledge config has no fields that need validation
    # (domains, mastery_levels, and boolean flags are valid by default)
    return []


def validate_config(config: UnifiedConfig) -> list[str]:
    """
    Validate the entire configuration

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Validate environment
    if config.environment not in Environment:
        errors.append(f"Invalid environment: {config.environment}")

    # Basic database validation
    if not config.database.neo4j_uri:
        errors.append("Neo4j URI is required")

    if not config.database.neo4j_username:
        errors.append("Neo4j username is required")

    if not config.database.neo4j_password:
        errors.append("Neo4j password is required")

    # Basic API validation
    if config.api.port < 1 or config.api.port > 65535:
        errors.append(f"Invalid API port: {config.api.port}")

    # Validate application config
    if not config.application.name:
        errors.append("Application name is required")

    if not config.application.version:
        errors.append("Application version is required")

    # Validate log level
    valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if config.application.log_level not in valid_log_levels:
        errors.append(f"Invalid log level: {config.application.log_level}")

    # Validate knowledge configuration
    errors.extend(validate_knowledge_config(config.knowledge))

    return errors



def log_validation_report(errors: list[str]) -> None:
    """Log a formatted validation report"""
    if not errors:
        logger.info("Configuration validation successful")
    else:
        logger.error("Configuration validation failed", errors=errors)


def print_validation_report(errors: list[str]) -> None:
    """Print a formatted validation report (for CLI/interactive use)"""
    if not errors:
        print("✅ Configuration validation successful")
    else:
        print("❌ Configuration validation failed:")
        for error in errors:
            print(f"  • {error}")


if __name__ == "__main__":
    # Demo configuration validation
    from core.config.settings import get_settings as _get_settings

    print("🧠 SKUEL Configuration Validation")
    print("=" * 40)

    # Validate configuration
    try:
        config: UnifiedConfig = _get_settings()  # type: ignore[has-type]
        config_errors = validate_config(config)
        print("\nConfiguration:")
        print_validation_report(config_errors)

        if not config_errors:
            print("\n✨ All validations passed!")
    except Exception as e:
        print(f"\n❌ Error validating configuration: {e}")
