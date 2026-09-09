# Application Configuration

Python application runtime settings, credentials, and environment configuration.

## Contents

- `unified_config.py` - Main configuration dataclasses and factory functions
- `settings.py` - Settings accessor functions for the application
- `__main__.py` - `python -m core.config` → the credential setup tool
- `credential_setup.py` - Interactive credential setup tool
- `credential_store.py` - The credential catalog, the backends, and `get_credential()`
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

It writes through `get_active_backend()` — the same function `get_credential()` reads through, so there is exactly one place a credential can land:

- `SKUEL_CREDENTIAL_BACKEND=keyring` (the default) → OS keychain (libsecret / Keychain / Credential Locker)
- `SKUEL_CREDENTIAL_BACKEND=env` → the process environment, read-only. The setup tool refuses to run here rather than discarding what you type; set the value in whatever builds that environment.

Any other value raises `ConfigurationError` at the first credential read.

Services read credentials via `get_credential(KEY, fallback_to_env=True)` — never raw `os.getenv()`. An env-supplied value is written into a writable backend on first read, but only when the key is in `CREDENTIAL_CATALOG`: connection config such as `NEO4J_URI` reaches the funnel from real callers and must never become a second source of truth for where the database lives.

Required credentials for the active intelligence tier are validated at boot (commit `fed4287f`); the app refuses to start when one is missing rather than degrading silently.

`CREDENTIAL_CATALOG` in `credential_store.py` is THE list of credentials. `scripts/lint_skuel.py::SkuelLinter.CREDENTIAL_CATALOG` (SKUEL019) and `scripts/git-hooks/credential-keys.txt` (the secret scan) mirror its names, each pinned by a drift test — adding a credential there is what makes both cover it.

For how credentials got out of the worktree, and the docker-compose carve-out for `NEO4J_AUTH` / `NEO4J_PASSWORD`, see `docs/roadmap/done/secrets-out-of-worktree.md`.

## Architecture

This configuration module follows SKUEL's principles:
- **Single source of truth** - All settings flow through unified_config.py
- **Type-safe** - Pydantic-based configuration with validation
- **Environment-aware** - Automatic environment detection and adaptation
- **Secure** - Credentials stored separately with proper file permissions

## Configuration Hierarchy

1. **Credential backend** (the keychain, or the process environment under `env`)
2. **Environment variables** (fallback, and the migration source for the keychain)
3. **Default values**

---

**Location:** `/core/config/` - Application configuration (Python)
**Related:** `/data/config/` - Domain data configuration (YAML)
**Related:** `/infrastructure/` - Infrastructure configuration (Docker/Neo4j)
