# Development Setup Guide

This guide covers setting up SKUEL for local development.

## Prerequisites

- Python 3.14 (pinned in `.python-version`)
- uv (package manager)
- A Neo4j database — local Docker for a from-scratch setup, or a hosted AuraDB Free instance (see the note below)
- OpenAI API key (required at `INTELLIGENCE_TIER=full`)
- Deepgram API key (optional — voice journal transcription)

## Database Setup

### Neo4j

SKUEL requires Neo4j as its primary database. All dependencies are REQUIRED — no graceful degradation; tier-gated services fail boot when their credentials are missing (commit `fed4287f`).

1. Install and start Neo4j (default: `bolt://localhost:7687`).
2. Put non-secret connection bits in `app/.env`:
   ```
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USERNAME=neo4j
   ```
3. Load `NEO4J_PASSWORD` into the active credential backend (the keychain by default — `SKUEL_CREDENTIAL_BACKEND=keyring` in `app/.env`). See `app/README.md` § "Configure Environment" for the three supported shapes and the `python -m core.config` entry point.

> **Hosted alternative:** a Neo4j AuraDB Free instance works identically (`NEO4J_URI=neo4j+s://<dbid>.databases.neo4j.io`) — since 2026-08-15 the primary dev machine's daily graph is AuraDB, with local Docker kept as an opt-in sandbox. ⚠️ Aura usernames are the **instance ID**, not `neo4j` — copy `NEO4J_USERNAME` from the Aura credentials file. See `/docs/deployment/AURADB_MIGRATION_GUIDE.md` § 6.1.

### Development Users

**One path forward:** Same code in all environments, different data.

Development and production use the same authentication code path. The difference is in the seeded data:

- **Development:** Seeded test users in database
- **Production:** Real users in database

#### Seeding Test Users

Run the seed script to create test users in your development database:

```bash
uv run python scripts/seed_dev_users.py
```

This creates three test users:

| UID | Username | Email | Role | Purpose |
|-----|----------|-------|------|---------|
| `user.dev` | dev | dev@skuel.local | ADMIN | Primary development user |
| `user.alice` | alice | alice@skuel.local | MEMBER | Standard member testing |
| `user.bob` | bob | bob@skuel.local | TEACHER | Teacher/curriculum testing |

**Note:** The seed script is idempotent - it won't create duplicates if run multiple times.

## Authentication in Development

SKUEL enforces "one path forward" for authentication:

- **No demo user fallbacks** - User service must succeed
- **No silent failures** - Configuration errors surface immediately
- **Same code, different data** - Development uses seeded users, production uses real users

If you see authentication errors:
1. Ensure Neo4j is running
2. Run the seed script to create test users
3. Check that user service is properly initialized in `services_bootstrap.py`

## Environment Variables

`app/.env` (gitignored) holds non-secret config — see `app/.env.example` for the full inventory:

```
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
SKUEL_CREDENTIAL_BACKEND=keyring
SKUEL_ENVIRONMENT=local
INTELLIGENCE_TIER=full
APP_PORT=8000
LOG_LEVEL=INFO
```

Credentials (`NEO4J_PASSWORD`, `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, …) are read via `get_credential()` from the backend selected above — do **not** `export` them as shell env or paste them into `.env`. Load them once with `uv run python core/config/credential_setup.py` (interactive) or `uv run python scripts/migrate_secrets_to_keychain.py`. The full inventory of credential keys lives in `core/config/credential_setup.py::CredentialSetup.CREDENTIALS`.

## Running the Application

```bash
# Install dependencies
uv sync

# Seed development users (first time only)
uv run python scripts/seed_dev_users.py

# Start the application
uv run python main.py
```

The application will fail to start if required dependencies are not available. This is intentional - SKUEL does not support graceful degradation.

## Development Workflow

### Making Changes

SKUEL follows "one path forward" philosophy:
- **No backward compatibility** - Update all call sites when patterns change
- **No alternative paths** - One way to accomplish each task
- **No deprecation periods** - Old patterns are deleted, not deprecated

### Code Quality

Run formatting and linting before committing:

```bash
# Format code
./dev format

# Run all quality checks
./dev quality
```

## Testing

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest app/tests/unit/test_something.py

# Run with coverage
uv run pytest --cov=app
```

## Common Issues

### "User not found" errors

**Symptom:** Error page showing "User not found: user.dev"

**Solution:** Run the seed script to create development users:
```bash
uv run python scripts/seed_dev_users.py
```

### "Failed to load context" errors

**Symptom:** 500 error when accessing /profile

**Solution:** Ensure user service is properly initialized:
1. Check Neo4j is running
2. Check environment variables are set
3. Check services_bootstrap.py initializes user_service

### Database connection errors

**Symptom:** Application fails to start with database connection error

**Solution:** This is expected behavior (fail-fast). Check:
1. Neo4j is running on the configured URI
2. Credentials are correct
3. Network connectivity to Neo4j

## Architecture Notes

SKUEL uses a fail-fast dependency philosophy:
- All dependencies are REQUIRED at bootstrap
- No optional services with fallback logic
- Configuration errors surface immediately in development
- No environment-specific branching in code

This ensures development environments accurately reflect production behavior.

## See Also

- `/docs/patterns/AUTH_PATTERNS.md` - Authentication patterns
- `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md` - User architecture
- `/docs/decisions/ADR-022-graph-native-authentication.md` - Graph-native auth design
- `/app/CLAUDE.md` - Development philosophy and quick reference
