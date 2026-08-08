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
from core.config import get_settings

settings = get_settings()
db_config = settings.database
```

## Credential Setup

**Do not edit credential files manually.** Use the credential setup tool:

```bash
uv run python -m core.config
```

It reads `SKUEL_CREDENTIAL_BACKEND` to decide where to write:

- `SKUEL_CREDENTIAL_BACKEND=keyring` → OS keychain (libsecret / Keychain / Credential Locker)
- unset → Fernet-encrypted JSON at `~/.skuel/credentials.enc`

Either way, services read credentials via `get_credential(KEY, fallback_to_env=True)` — never raw `os.getenv()`. Required credentials for the active intelligence tier are validated at boot (commit `fed4287f`); the app refuses to start when one is missing rather than degrading silently.

For the full landscape (the three storage shapes, the migration scripts, the docker-compose carve-out for `NEO4J_AUTH` / `NEO4J_PASSWORD`), see `docs/roadmap/done/secrets-out-of-worktree.md`.

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
