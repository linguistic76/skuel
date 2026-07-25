"""
SKUEL Configuration Module
==========================

Centralized configuration management for the ports + adapters architecture.

Quick Usage:
    from core.config import get_settings

    settings = get_settings()
    db = settings.database
"""

__version__ = "1.0"


# Import intelligence tier
# Import main configuration access points
# Dependency injection moved to services_bootstrap.py - no legacy functions needed
# Import environment validation
from core.config.environment_validator import (
    EnvironmentValidator,
    get_openai_key,
    validate_environment,
)
from core.config.intelligence_tier import IntelligenceTier
from core.config.settings import (
    get_settings,
    reload_config,
)

# Import core configuration types
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
    "IntelligenceTier",
    "KnowledgeConfig",
    "MessageQueueConfig",
    "SearchConfig",
    # Configuration types
    "UnifiedConfig",
    "create_config",
    "create_development_config",
    "create_production_config",
    "create_test_config",
    "get_openai_key",
    # Settings access
    "get_settings",
    "print_validation_report",
    "reload_config",
    # Validation
    "validate_config",
    "validate_environment",
]
