# Application Configuration

Python application runtime settings, credentials, and environment configuration.

## Contents

- `unified_config.py` - Main configuration dataclasses and factory functions
- `settings.py` - Settings accessor functions for the application
- `credential_setup.py` - Interactive credential setup tool
- `credential_store.py` - Secure credential storage and retrieval
- `environment_validator.py` - Environment validation and API key management
- `validation.py` - Configuration validation logic

## Usage

```python
from core.config import get_settings, get_database_config

settings = get_settings()
db_config = get_database_config()
```

## Credential Setup

**Do not edit credential files manually.** Use the credential setup tool:

```bash
python -m core.config
```

## Architecture

This configuration module follows SKUEL's principles:
- **Single source of truth** - All settings flow through unified_config.py
- **Type-safe** - Pydantic-based configuration with validation
- **Environment-aware** - Automatic environment detection and adaptation
- **Secure** - Credentials stored separately with proper file permissions

## Configuration Hierarchy

1. **Environment variables** (highest priority)
2. **Credential store** (secure vault)
3. **Default values** (fallback)

---

**Location:** `/core/config/` - Application configuration (Python)
**Related:** `/data/config/` - Domain data configuration (YAML)
**Related:** `/infrastructure/` - Infrastructure configuration (Docker/Neo4j)
