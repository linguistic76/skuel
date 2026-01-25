# Authenticated GraphQL Tests

## Overview

The GraphQL API tests require authentication to work correctly. This document explains how the authentication fixtures work.

## Architecture

### Authentication Requirement

The GraphQL endpoint (`/graphql`) requires authenticated users:

```python
# graphql_routes.py:135
user_uid = require_authenticated_user(request)  # Raises 401 if not authenticated
```

This is a production security requirement - all GraphQL queries must come from authenticated users.

### Test Fixtures

#### `authenticated_client` (conftest.py)

Provides an authenticated AsyncClient for API testing:

```python
async def test_my_graphql_query(authenticated_client):
    response = await authenticated_client.post(
        "/graphql",
        json={"query": "..."}
    )
    assert response.status_code == 200
```

**How it works:**

1. **Registration** - Creates test user if it doesn't exist
   - Username: `test_graphql_user`
   - Email: `test_graphql@example.com`
   - Password: `test_password_123`

2. **Login** - Authenticates via `/login` endpoint
   - Sends POST request with credentials
   - Receives session cookie (`skuel_session`)

3. **Session Cookie** - Returns AsyncClient with authenticated session
   - Cookie automatically included in all requests
   - Valid for duration of test

#### `test_user_uid` (conftest.py)

Provides the test user UID for use in GraphQL queries:

```python
def test_user_uid():
    """Test user UID matches the user created by authenticated_client"""
    return "test_graphql_user"
```

## Running Tests

### Prerequisites

1. **SKUEL application running** at `http://localhost:8000`
   ```bash
   poetry run python main.py
   ```

2. **All required services available:**
   - Neo4j database
   - OpenAI API key configured
   - Deepgram API key configured

### Run Tests

```bash
# Run all GraphQL tests
poetry run pytest tests/test_graphql_queries.py -v

# Run specific test
poetry run pytest tests/test_graphql_queries.py::test_learning_path_query -v

# Run with output
poetry run pytest tests/test_graphql_queries.py -v -s
```

## Test Structure

All 8 GraphQL API tests now use the `authenticated_client` fixture:

1. `test_learning_path_query` - Basic learning path query
2. `test_learning_path_with_context_query` - Learning path with user context
3. `test_prerequisite_chain_query` - Prerequisite chain traversal
4. `test_knowledge_dependencies_query` - Knowledge dependency graph
5. `test_learning_path_blockers_query` - Learning path blockers
6. `test_nested_query_depth` - Deeply nested query (3+ levels)
7. `test_flexible_field_selection_minimal` - Minimal field selection
8. `test_flexible_field_selection_rich` - Rich field selection

Plus 1 structure validation test (no authentication required):

9. `test_query_structure_validation` - GraphQL query syntax validation

## Troubleshooting

### 401 Unauthorized Errors

If tests fail with 401 errors:

1. **Check app is running** - `http://localhost:8000` must be accessible
2. **Check registration endpoint** - `/register` must be working
3. **Check login endpoint** - `/login` must be working
4. **Check SessionMiddleware** - Must be installed in app

### Registration Failures

If registration fails (user already exists):
- This is expected and handled
- Fixture will proceed to login step
- User credentials are consistent across test runs

### Cookie Issues

If session cookie isn't being set:
- Check `SessionMiddleware` configuration
- Check `SESSION_SECRET_KEY` environment variable
- Verify `/login` returns `set-cookie` header

## Design Philosophy

This follows SKUEL's **fail-fast architecture**:

- ✅ **No mocking** - Tests real authentication flow
- ✅ **Production behavior** - Same code path as production
- ✅ **Clear errors** - 401 errors indicate real configuration issues
- ✅ **Required dependencies** - All services must be available

This aligns with the principle: *"SKUEL runs at full capacity or not at all."*
