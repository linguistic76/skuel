# GraphQL Authentication

**Session-based authentication for SKUEL GraphQL API**

---

## Overview

SKUEL's GraphQL API now uses **session-based authentication** with a development-friendly approach:

- ✅ Extracts authenticated user from session cookie
- ✅ Falls back to default dev user when no session exists
- ✅ Optional `user_uid` parameters for admin queries (future)
- ✅ Permission checks placeholder (ready for enhancement)

---

## How It Works

### Request Flow

```
1. Client sends GraphQL query with session cookie
   ↓
2. GraphQL route extracts user from session
   ↓
3. Context created with authenticated user_uid
   ↓
4. Resolvers use context.user_uid for queries
   ↓
5. Results returned to client
```

### Implementation

**Step 1: Route extracts user from session**

```python
# adapters/inbound/graphql_routes.py

from adapters.inbound.auth.session import get_current_user_or_default

@rt("/graphql", methods=["POST"])
async def graphql_post(request: Any) -> Response:
    # Extract authenticated user from session (or use default for development)
    user_uid = get_current_user_or_default(request)
    logger.info(f"GraphQL request from user: {user_uid}")

    # Create authenticated context
    context = create_graphql_context(services, user_uid=user_uid)

    # Execute query with authenticated context
    result = await schema.execute(...)
```

**Step 2: Resolvers use authenticated user**

```python
# routes/graphql/schema.py

@strawberry.field
async def tasks(
    self,
    info: Info[GraphQLContext, Any],
    include_completed: bool = False,
    limit: int | None = None,
    user_uid: str | None = None  # Optional: for admin queries
) -> list[Task]:
    context: GraphQLContext = info.context

    # AUTHENTICATION: Use authenticated user from context
    target_user_uid = user_uid or context.user_uid

    if not target_user_uid:
        return []  # No authenticated user

    # Query tasks for authenticated user
    result = await context.services.tasks.list_user_tasks(
        user_uid=target_user_uid,
        ...
    )
```

---

## Authentication Modes

### Development Mode (Default)

**Behavior:**
- If session exists → Uses `session['user_uid']`
- If no session → Falls back to `DEFAULT_DEV_USER` ("user.mike")
- GraphQL queries always work (development-friendly)

**Usage:**
```graphql
# No user_uid needed - uses authenticated user from session
query {
  tasks {
    uid
    title
  }
}

# Returns tasks for session user or "user.mike" if no session
```

### Production Mode (Future)

**Behavior:**
- Session required for all authenticated queries
- No fallback to default user
- Returns error if no session

**Implementation:**
```python
# Future: Strict authentication mode
from adapters.inbound.auth.session import get_current_user  # No fallback

user_uid = get_current_user(request)
if not user_uid:
    return JSONResponse(
        {"errors": [{"message": "Authentication required"}]},
        status_code=401
    )
```

---

## Authenticated Queries

### User-Specific Queries

These queries now use the authenticated user from context:

#### `tasks(includeCompleted, limit, userUid?)`

**Default behavior (uses authenticated user):**
```graphql
query {
  tasks(includeCompleted: false, limit: 10) {
    uid
    title
    status
  }
}
```

**Admin query (specify user_uid):**
```graphql
query {
  tasks(userUid: "user.other", limit: 10) {
    uid
    title
  }
}
```

**Parameters:**
- `includeCompleted` - Include completed tasks (default: false)
- `limit` - Max tasks to return (default: 20, max: 100)
- `userUid` - Optional: query another user's tasks (future: admin only)

#### `learningPaths(userUid?, limit)`

**Default behavior (uses authenticated user):**
```graphql
query {
  learningPaths(limit: 5) {
    uid
    name
    goal
  }
}
```

**All paths (no user filter):**
```graphql
# To get ALL paths (not user-specific), explicitly pass userUid as null
# Future enhancement: add allLearningPaths query
```

**Parameters:**
- `userUid` - Optional: defaults to authenticated user
- `limit` - Max paths to return (default: 20, max: 100)

#### `userDashboard(userUid?)`

**Default behavior (uses authenticated user):**
```graphql
query {
  userDashboard {
    tasksCount
    pathsCount
    habitsCount
  }
}
```

**Admin query (specify user):**
```graphql
query {
  userDashboard(userUid: "user.other") {
    tasksCount
    pathsCount
    habitsCount
  }
}
```

**Parameters:**
- `userUid` - Optional: defaults to authenticated user

---

## Permission Checks

### Current Implementation

**Placeholder with TODO:**
```python
# PERMISSION CHECK: Users can only query their own dashboard
# (unless they're admin - future enhancement)
if user_uid and user_uid != context.user_uid:
    # User is trying to access another user's dashboard
    # For now, allow it (future: check admin permissions)
    pass  # TODO: Add admin permission check
```

### Future Enhancement

**Add admin permission checks:**
```python
# routes/graphql/context.py

@dataclass
class GraphQLContext:
    services: Services
    knowledge_loader: DataLoader[str, Any]
    task_loader: DataLoader[str, Any]
    learning_path_loader: DataLoader[str, Any]
    user_uid: str | None = None
    is_admin: bool = False  # ✅ Add admin flag

# routes/graphql/schema.py

@strawberry.field
async def user_dashboard(
    self,
    info: Info[GraphQLContext, Any],
    user_uid: str | None = None
) -> DashboardData:
    context: GraphQLContext = info.context

    target_user_uid = user_uid or context.user_uid

    # PERMISSION CHECK: Users can only query their own dashboard
    if user_uid and user_uid != context.user_uid:
        if not context.is_admin:
            raise Exception("Unauthorized: Cannot access other user's dashboard")
```

---

## Session Management

### Setting Up Session

**Login route (example):**
```python
from adapters.inbound.auth.session import set_current_user

@rt("/login", methods=["POST"])
async def login(request, username: str, password: str):
    # Validate credentials...
    if valid:
        set_current_user(request, user_uid="user.mike")
        return RedirectResponse("/")
    else:
        return "Invalid credentials"
```

### Clearing Session

**Logout route (example):**
```python
from adapters.inbound.auth.session import clear_current_user

@rt("/logout")
async def logout(request):
    clear_current_user(request)
    return RedirectResponse("/login")
```

### Session Configuration

**In bootstrap:**
```python
from starlette.middleware.sessions import SessionMiddleware
from adapters.inbound.auth.session import get_session_middleware_config

config = get_session_middleware_config()
app.add_middleware(SessionMiddleware, **config)
```

**Session settings:**
- Cookie name: `skuel_session`
- Max age: 30 days
- Secure: Production only (HTTPS)
- SameSite: `lax` (CSRF protection)

---

## Development Experience

### GraphiQL with Authentication

**GraphiQL playground automatically uses session:**
1. Open browser to http://localhost:8000/graphql
2. Session cookie is sent automatically
3. Queries use authenticated user

**Testing different users:**
```python
# In browser console (while on GraphiQL page):
// Manually set session to test different users
// (This is a hack for development only)

fetch('/login', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({username: 'test_user', password: 'test'})
});
```

### Default User Behavior

**Development-friendly defaults:**
- No session → Uses `DEFAULT_DEV_USER` ("user.mike")
- All queries work without authentication
- No need to log in during development
- Production mode can enforce strict authentication

---

## Security Considerations

### Current Security

✅ **Session cookies** - Signed and tamper-proof
✅ **HTTPS in production** - Secure cookies enabled
✅ **SameSite protection** - CSRF mitigation
✅ **Development fallback** - Explicit and logged

⚠️ **Not yet implemented:**
- Admin permission checks
- Rate limiting per user
- Query complexity limits per user
- Audit logging for sensitive queries

### Best Practices

**For production deployment:**

1. **Set session secret key:**
```bash
export SESSION_SECRET_KEY="your-secure-random-key-here"
```

2. **Enable strict authentication:**
```python
# Change from:
user_uid = get_current_user_or_default(request)

# To:
user_uid = get_current_user(request)
if not user_uid:
    return JSONResponse(
        {"errors": [{"message": "Authentication required"}]},
        status_code=401
    )
```

3. **Implement admin checks:**
```python
# Add admin permission checks before allowing cross-user queries
if user_uid != context.user_uid and not context.is_admin:
    raise Exception("Unauthorized")
```

4. **Add rate limiting:**
```python
# Use Strawberry extensions for rate limiting
from strawberry.extensions import RateLimitExtension

schema = strawberry.Schema(
    query=Query,
    extensions=[RateLimitExtension(max_queries_per_minute=60)]
)
```

---

## Testing Authentication

### Manual Testing

**Test authenticated queries:**
```bash
# 1. Start the server
poetry run python main.py

# 2. Log in via browser
# Navigate to http://localhost:8000/login
# Enter credentials

# 3. Test GraphQL with session
# Navigate to http://localhost:8000/graphql
# Run query:
query {
  tasks {
    uid
    title
  }
}

# Should return tasks for authenticated user
```

### Programmatic Testing

**Test with Python:**
```python
import httpx
import asyncio

async def test_authenticated_query():
    async with httpx.AsyncClient() as client:
        # Login first
        login_response = await client.post(
            "http://localhost:8000/login",
            json={"username": "test_user", "password": "test"}
        )

        # Get session cookie
        cookies = login_response.cookies

        # Make GraphQL query with session
        response = await client.post(
            "http://localhost:8000/graphql",
            json={
                "query": """
                    query {
                        tasks {
                            uid
                            title
                        }
                    }
                """
            },
            cookies=cookies  # Include session cookie
        )

        print(response.json())

asyncio.run(test_authenticated_query())
```

---

## Migration from Unauthenticated Queries

### Before (Unauthenticated)

```graphql
query {
  tasks(userUid: "user.mike", limit: 10) {
    uid
    title
  }
}
```

**Problem:** Client must know and provide user UID

### After (Authenticated)

```graphql
query {
  tasks(limit: 10) {
    uid
    title
  }
}
```

**Benefit:** User UID extracted from session automatically

### Backward Compatibility

**Old queries still work:**
```graphql
# Explicit userUid still supported (for admin queries)
query {
  tasks(userUid: "user.other", limit: 10) {
    uid
    title
  }
}
```

---

## Summary

### What's Implemented ✅

- ✅ Session-based authentication in GraphQL routes
- ✅ Authenticated user extraction from session
- ✅ Development-friendly fallback to default user
- ✅ Updated resolvers to use `context.user_uid`
- ✅ Optional `user_uid` parameters for admin queries
- ✅ Permission check placeholders (ready for enhancement)

### What's Next 🔄

- 🔄 Implement admin permission checks
- 🔄 Add strict authentication mode for production
- 🔄 Add audit logging for sensitive queries
- 🔄 Implement rate limiting per user
- 🔄 Add query complexity limits per user

### Authentication Status

**Current:** Development-friendly with optional authentication
**Production-ready:** With environment variable `SESSION_SECRET_KEY` set
**Recommended:** Implement strict auth mode + admin checks before production
