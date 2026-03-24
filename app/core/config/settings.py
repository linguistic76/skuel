"""
SKUEL Configuration Settings
============================

Single entry point: get_settings() returns a cached UnifiedConfig instance.
Access sub-configs via attribute access: get_settings().database, get_settings().api, etc.

Usage:
    from core.config.settings import get_settings

    settings = get_settings()
    db_config = settings.database
    neo4j_uri = db_config.neo4j_uri
"""

__version__ = "1.0"


import os
from functools import lru_cache

from core.config.unified_config import Environment, UnifiedConfig, create_config
from core.config.validation import validate_config


@lru_cache(maxsize=1)
def get_settings() -> UnifiedConfig:
    """Get the global settings instance with validation."""
    environment = Environment(os.getenv("SKUEL_ENVIRONMENT", "local"))
    config = create_config(environment)

    # Validate configuration on first access
    validation_errors = validate_config(config)
    if validation_errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(validation_errors)
        raise ValueError(error_msg)

    return config


def reload_config() -> None:
    """Clear cached configuration to force reload."""
    get_settings.cache_clear()
