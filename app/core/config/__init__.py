"""
SKUEL Configuration Module
==========================

Centralized configuration management for the ports + adapters architecture.

Quick Usage:
    from core.config import get_settings, get_database_config

    settings = get_settings()
    db = get_database_config()
"""

__version__ = "1.0"


# Import intelligence tier
from core.config.intelligence_tier import IntelligenceTier

# Import main configuration access points
# Dependency injection moved to services_bootstrap.py - no legacy functions needed
# Import environment validation
from core.config.environment_validator import (
    EnvironmentValidator,
    get_openai_key,
    validate_environment,
)
from core.config.settings import (
    api_host,
    api_port,
    app_name,
    app_version,
    conversation_max_history,
    debug_mode,
    embedding_dimension,
    get_api_config,
    get_application_config,
    get_askesis_config,
    get_cache_config,
    get_database_config,
    get_feature_config,
    get_graphql_config,
    get_knowledge_config,
    get_message_queue_config,
    get_search_config,
    get_settings,
    is_development,
    is_feature_enabled,
    is_local,
    is_production,
    is_staging,
    is_testing,
    log_level,
    neo4j_password,
    neo4j_uri,
    neo4j_username,
    redis_url,
    reload_config,
    search_results_limit,
)

# Import core configuration types
from core.config.unified_config import (
    APIConfig,
    ApplicationConfig,
    AskesisConfig,
    CacheConfig,
    DatabaseConfig,
    Environment,
    GraphQLConfig,
    KnowledgeConfig,
    MessageQueueConfig,
    SearchConfig,
    UnifiedConfig,
    create_config,
    create_development_config,
    create_production_config,
    create_test_config,
)

# Import validation utilities
from core.config.validation import (
    ConfigValidator,
    print_validation_report,
    validate_config,
    validate_environment_variables,
)

__all__ = [
    "APIConfig",
    "ApplicationConfig",
    "AskesisConfig",
    "CacheConfig",
    "ConfigValidator",
    "DatabaseConfig",
    "Environment",
    # Environment validation
    "EnvironmentValidator",
    "GraphQLConfig",
    "IntelligenceTier",
    "KnowledgeConfig",
    "MessageQueueConfig",
    "SearchConfig",
    # Configuration types
    "UnifiedConfig",
    "api_host",
    "api_port",
    "app_name",
    "app_version",
    "conversation_max_history",
    "create_config",
    "create_development_config",
    "create_production_config",
    "create_test_config",
    "debug_mode",
    "embedding_dimension",
    "get_api_config",
    "get_application_config",
    "get_askesis_config",
    "get_cache_config",
    "get_database_config",
    "get_feature_config",
    "get_graphql_config",
    "get_knowledge_config",
    "get_message_queue_config",
    "get_openai_key",
    "get_search_config",
    # Settings access
    "get_settings",
    "is_development",
    "is_feature_enabled",
    "is_local",
    # Environment detection
    "is_production",
    "is_staging",
    "is_testing",
    "log_level",
    "neo4j_password",
    # Quick accessors
    "neo4j_uri",
    "neo4j_username",
    "print_validation_report",
    "redis_url",
    "reload_config",
    "search_results_limit",
    # Dependency injection moved to services_bootstrap.py
    # Validation
    "validate_config",
    "validate_environment",
    "validate_environment_variables",
]
