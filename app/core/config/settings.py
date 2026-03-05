"""
SKUEL Configuration Settings
============================

Thin wrapper around unified_config.py providing convenient access patterns.
Follows ports + adapters architecture principles.

Usage:
    from core.config.settings import get_settings, get_database_config

    settings = get_settings()
    db_config = get_database_config()
    neo4j_uri = db_config.neo4j_uri
"""

__version__ = "1.0"


import os
from functools import lru_cache

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
    UnifiedConfig,
    VaultConfig,
    create_config,
)
from core.config.validation import validate_config


@lru_cache(maxsize=1)
def get_settings() -> UnifiedConfig:
    """Get the global settings instance with validation"""
    environment = Environment(os.getenv("SKUEL_ENVIRONMENT", "local"))
    config = create_config(environment)

    # Validate configuration on first access
    validation_errors = validate_config(config)
    if validation_errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(validation_errors)
        raise ValueError(error_msg)

    return config


# Port Configuration Accessors
@lru_cache(maxsize=1)
def get_api_config() -> APIConfig:
    """Get API port configuration"""
    return get_settings().api


@lru_cache(maxsize=1)
def get_graphql_config() -> GraphQLConfig:
    """Get GraphQL port configuration"""
    return get_settings().graphql


# Adapter Configuration Accessors
@lru_cache(maxsize=1)
def get_database_config() -> DatabaseConfig:
    """Get database adapter configuration"""
    return get_settings().database


@lru_cache(maxsize=1)
def get_cache_config() -> CacheConfig:
    """Get cache adapter configuration"""
    return get_settings().cache


@lru_cache(maxsize=1)
def get_message_queue_config() -> MessageQueueConfig:
    """Get message queue adapter configuration"""
    return get_settings().message_queue


# Core Domain Configuration Accessors
@lru_cache(maxsize=1)
def get_search_config() -> SearchConfig:
    """Get search domain configuration"""
    return get_settings().search


@lru_cache(maxsize=1)
def get_askesis_config() -> AskesisConfig:
    """Get askesis domain configuration"""
    return get_settings().askesis


@lru_cache(maxsize=1)
def get_knowledge_config() -> KnowledgeConfig:
    """Get knowledge domain configuration"""
    return get_settings().knowledge


@lru_cache(maxsize=1)
def get_genai_config() -> GenAIConfig:
    """Get GenAI configuration"""
    return get_settings().genai


@lru_cache(maxsize=1)
def get_vault_config() -> VaultConfig:
    """Get vault and sync configuration"""
    return get_settings().vault


@lru_cache(maxsize=1)
def get_application_config() -> ApplicationConfig:
    """Get application configuration"""
    return get_settings().application


# Environment detection helpers
def is_production() -> bool:
    """Check if running in production"""
    return get_settings().environment == Environment.PRODUCTION


def is_development() -> bool:
    """Check if running in development"""
    return get_settings().environment == Environment.DEVELOPMENT


def is_staging() -> bool:
    """Check if running in staging"""
    return get_settings().environment == Environment.STAGING


def is_local() -> bool:
    """Check if running locally"""
    return get_settings().environment == Environment.LOCAL


def is_testing() -> bool:
    """Check if running in test mode"""
    return get_settings().environment == Environment.TEST


# Quick access helpers for common settings
def neo4j_uri() -> str:
    """Get Neo4j connection URI"""
    return get_database_config().neo4j_uri


def neo4j_username() -> str:
    """Get Neo4j username"""
    return get_database_config().neo4j_username


def neo4j_password() -> str:
    """Get Neo4j password"""
    return get_database_config().neo4j_password


def api_port() -> int:
    """Get API server port"""
    return get_api_config().port


def api_host() -> str:
    """Get API server host"""
    return get_api_config().host


def redis_url() -> str:
    """Get Redis URL from cache configuration"""
    return get_cache_config().redis_url


def search_results_limit() -> int:
    """Get default search results limit"""
    return get_search_config().default_limit


def conversation_max_history() -> int:
    """Get conversation max history size"""
    return get_askesis_config().max_facet_history


def embedding_dimension() -> int:
    """Get embedding dimension from GenAI configuration"""
    return get_genai_config().embedding_dimension


def app_name() -> str:
    """Get application name"""
    return get_application_config().name


def app_version() -> str:
    """Get application version"""
    return get_application_config().version


def log_level() -> str:
    """Get logging level"""
    return get_application_config().log_level


def debug_mode() -> bool:
    """Check if debug mode is enabled"""
    return get_application_config().debug


# Feature flags helpers
def is_feature_enabled(feature_name: str) -> bool:
    """Check if a feature is enabled"""
    return get_application_config().features.get(feature_name, False)


def get_feature_config(feature_name: str) -> dict | None:
    """Get configuration for a specific feature"""
    return get_application_config().features.get(feature_name)


# Reload configuration (useful for testing or runtime reloads)
def reload_config():
    """Clear cached configuration to force reload"""
    get_settings.cache_clear()
    get_api_config.cache_clear()
    get_graphql_config.cache_clear()
    get_database_config.cache_clear()
    get_cache_config.cache_clear()
    get_message_queue_config.cache_clear()
    get_search_config.cache_clear()
    get_askesis_config.cache_clear()
    get_knowledge_config.cache_clear()
    get_genai_config.cache_clear()
    get_application_config.cache_clear()


if __name__ == "__main__":
    # Demo the settings
    settings = get_settings()
    print("🧠 SKUEL Configuration")
    print(f"Environment: {settings.environment}")
    print(f"Application: {app_name()} v{app_version()}")
    print(f"Neo4j URI: {neo4j_uri()}")
    print(f"API: {api_host()}:{api_port()}")
    print(f"Debug Mode: {debug_mode()}")
    print(f"Log Level: {log_level()}")

    if is_development():
        print("✅ Running in development mode")
    elif is_production():
        print("⚠️  Running in production mode")
