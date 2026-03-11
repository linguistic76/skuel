# Development Setup Guide

This guide covers setting up SKUEL for local development.

## Prerequisites

- Python 3.11+
- uv (package manager)
- Neo4j database running locally
- OpenAI API key
- Deepgram API key

## Database Setup

### Neo4j

SKUEL requires Neo4j as its primary database. All dependencies are REQUIRED - no graceful degradation.

1. Install and start Neo4j (default: `bolt://localhost:7687`)
2. Set credentials in environment variables:
   ```bash
   export NEO4J_URI="bolt://localhost:7687"
   export NEO4J_USER="neo4j"
   export NEO4J_PASSWORD="your_password"
   ```

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

Required environment variables for development:

```bash
# Database
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="your_password"

# AI Services
export OPENAI_API_KEY="your_openai_key"
export DEEPGRAM_API_KEY="your_deepgram_key"

# Application
export ENV="development"
```

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
