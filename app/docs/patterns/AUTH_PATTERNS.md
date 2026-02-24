---
title: Authentication Patterns in SKUEL
updated: '2026-02-02'
category: patterns
related_skills: []
related_docs: []
---
# Authentication Patterns in SKUEL
*Last updated: 2026-01-24*

This document describes the authentication and authorization patterns used throughout SKUEL, including when to use each pattern and why.

## Overview

SKUEL uses **graph-native authentication** (sessions stored in Neo4j) with cookie-based session management. There are three main patterns for handling user identity in routes:

| Pattern | Function | Returns | Use Case |
|---------|----------|---------|----------|
| **Strict** | `require_authenticated_user(request)` | `UserUID` | API routes requiring auth |
| **Lenient** | `get_current_user_or_default(request)` | `UserUID` | UI routes (dev-friendly) |
| **Role-Based** | `@require_admin(service_getter)` | `current_user: User` | Protected admin/teacher routes |

## The UserUID Type Alias

```python
from adapters.inbound.auth import UserUID

# UserUID is a type alias for str with format "user.{name}"
# Examples: "user.mike", "user.alice"
user_uid: UserUID = require_authenticated_user(request)
```

The `UserUID` type alias provides:
- **Documentation**: Makes the expected format clear at call sites
- **Consistency**: Single source of truth for user identifier type
- **Future-proofing**: Easy to evolve to `NewType` if stricter typing needed

## Pattern 1: Strict Authentication (API Routes)

**Use for:** All API routes that require a real authenticated user.

```python
from adapters.inbound.auth import require_authenticated_user

@rt("/api/tasks")
async def list_tasks(request):
    # Raises HTTPException(401) if not authenticated
    user_uid = require_authenticated_user(request)

    # user_uid is guaranteed to be a valid UserUID string
    tasks = await tasks_service.list(user_uid=user_uid)
    return tasks
```

**Behavior:**
- Returns `UserUID` string (e.g., `"user.mike"`)
- Raises `HTTPException(401)` if user not authenticated
- No fallback to default user
- Logs warning on unauthenticated access attempts

**When to use:**
- All `/api/*` endpoints
- Any route that modifies user data
- Any route that returns user-specific data

## Pattern 2: Lenient Authentication (UI Routes)

**Use for:** UI routes where development convenience outweighs strict auth.

```python
from adapters.inbound.auth import get_current_user_or_default

@rt("/tasks")
async def tasks_page(request):
    # Returns "user.mike" if not authenticated (development mode)
    user_uid = get_current_user_or_default(request)

    tasks = await tasks_service.list(user_uid=user_uid)
    return render_tasks_page(tasks)
```

**Behavior:**
- Returns `UserUID` from session if authenticated
- Falls back to `DEFAULT_DEV_USER` (`"user.mike"`) if not authenticated
- Never returns `None` - always a valid `UserUID`
- Logs debug message when using default

**When to use:**
- UI pages during development
- Read-only views that don't require strict auth
- Demo/preview functionality

**Note:** In production, consider switching to `require_authenticated_user()` for UI routes that display sensitive data.

## Pattern 3: Role-Based Authentication (Admin/Teacher Routes)

**Use for:** Routes that require specific role permissions.

```python
from adapters.inbound.auth import require_admin, require_teacher

# SKUEL012: Use named functions, not lambdas
def get_user_service():
    return services.user_service


@rt("/api/admin/users")
@require_admin(get_user_service)
async def list_all_users(request, current_user):
    # current_user is the FULL User entity (not just uid)
    admin_uid = current_user.uid
    admin_role = current_user.role

    # Can use User entity methods
    if current_user.can_manage_users():
        return await user_service.list_all()


@rt("/api/ku", methods=["POST"])
@require_teacher(get_user_service)
async def create_knowledge_unit(request, current_user):
    # Teachers and Admins can create curriculum content
    return await ku_service.create(created_by=current_user.uid)
```

**Behavior:**
- Validates authentication (401 if not logged in)
- Fetches full `User` entity from database
- Checks role hierarchy (403 if insufficient role)
- Injects `current_user: User` into route kwargs

**Why `current_user: User` instead of `user_uid: str`?**
Role checking requires fetching the user from the database anyway, so the decorator provides the full entity to avoid duplicate fetches.

**Available decorators:**
- `@require_role(UserRole.ADMIN, getter)` - Explicit role requirement
- `@require_admin(getter)` - Shortcut for ADMIN
- `@require_teacher(getter)` - Shortcut for TEACHER
- `@require_member(getter)` - Shortcut for MEMBER (paid subscription)

## Pattern Comparison

| Aspect | `require_authenticated_user` | `get_current_user_or_default` | `@require_admin` |
|--------|------------------------------|-------------------------------|------------------|
| **Returns** | `UserUID` (string) | `UserUID` (string) | `current_user: User` |
| **On no auth** | Raises 401 | Returns default | Raises 401 |
| **On wrong role** | N/A | N/A | Raises 403 |
| **DB fetch** | No | No | Yes (required for role check) |
| **Best for** | API routes | UI development | Protected routes |

## Common Patterns

### Ownership Verification

After getting `user_uid`, verify ownership before operating on entities:

```python
@rt("/api/goals/{uid}")
async def update_goal(request):
    user_uid = require_authenticated_user(request)
    uid = request.path_params["uid"]

    # verify_ownership returns 404 (not 403) to prevent UID enumeration
    ownership = await goals_service.verify_ownership(uid, user_uid)
    if ownership.is_error:
        return ownership  # Returns 404 "Not Found"

    goal = ownership.value
    # Now safe to update
    return await goals_service.update(uid, updates)
```

### Using the `@with_ownership` Decorator

For simpler ownership verification:

```python
from adapters.inbound.auth import with_ownership

def get_goals_service():
    return goals_service


@rt("/api/goals/{uid}/progress")
@with_ownership(get_goals_service)
@boundary_handler()
async def update_goal_progress(request, user_uid, entity):
    # entity is pre-verified to belong to user_uid
    return await goals_service.update_progress(entity.uid, ...)
```

### Checking Admin in UI (Without Decorator)

For conditional UI rendering:

```python
from adapters.inbound.auth import get_is_admin

def create_navbar(request):
    is_admin = get_is_admin(request)  # Reads from session, no DB call

    if is_admin:
        return NavWithAdminLink()
    return NavStandard()
```

## Navbar Authentication Pattern (January 2026)

The navbar displays different links based on authentication state. To ensure consistent navbar behavior across all pages, **always pass the `request` object** through to layout functions.

### The Problem

Without passing the request, layouts default to unauthenticated state:
- Shows "Login/Sign Up" instead of user dropdown
- Admin users don't see "Admin Dashboard" link
- Profile Hub link may not work correctly

### The Solution: `create_navbar_for_request()`

Use `create_navbar_for_request(request)` for automatic auth detection:

```python
from ui.layouts.navbar import create_navbar_for_request

# ✅ RECOMMENDED: Auto-detects auth from session
navbar = create_navbar_for_request(request, active_page="tasks")

# ❌ LEGACY: Manual parameters (still supported for backwards compatibility)
navbar = create_navbar(
    current_user="user.mike",
    is_authenticated=True,
    is_admin=False,
    active_page="tasks",
)
```

### Layout Integration

All domain layouts and SharedUIComponents support the `request` parameter:

**Activity Domain Layouts:**
```python
from ui.habits.layout import create_habits_page

@rt("/habits")
async def habits_dashboard(request):
    # Pass request for automatic navbar auth
    return create_habits_page(content, request=request)
```

**SharedUIComponents:**
```python
from ui.patterns.entity_dashboard import SharedUIComponents

dashboard = SharedUIComponents.render_entity_dashboard(
    title="🎯 Habits",
    entities=habits,
    entity_renderer=render_habit_card,
    request=request,       # Auto-detects auth
    active_page="habits",  # Highlights active nav item
)
```

**DocsLayout (Nous pages):**
```python
from ui.docs import create_docs_page

return create_docs_page(
    title="Topic Title",
    content=content,
    sections=sections,
    base_path="/nous",
    request=request,  # Auto-detects auth for navbar
)
```

### What the Navbar Shows

| User State | Dashboard Links | User Area |
|------------|-----------------|-----------|
| Unauthenticated | None | Login / Sign Up |
| Authenticated (Regular) | Profile Hub | User dropdown |
| Authenticated (Admin) | Admin Dashboard + Profile Hub | User dropdown |

### Files Reference

| File | Purpose |
|------|---------|
| `/ui/layouts/navbar.py` | `create_navbar()`, `create_navbar_for_request()` |
| `/ui/layouts/activity_layout.py` | Activity domain layout with request support |
| `/ui/habits/layout.py` (etc.) | Domain-specific layouts delegating to activity_layout |
| `/ui/docs/layout.py` | Documentation layout with request support |
| `/ui/patterns/entity_dashboard.py` | Shared dashboard with request support |

## Session Flow

```
1. User logs in via /login
   ↓
2. GraphAuthService.sign_in() creates Session node in Neo4j
   ↓
3. set_current_user() stores user_uid + session_token in cookie
   ↓
4. On each request:
   - Fast path: get_current_user() reads user_uid from cookie
   - Secure path: get_current_user_validated() validates in Neo4j
   ↓
5. User logs out via /logout
   ↓
6. clear_current_user() removes cookie, Session node invalidated
```

## Security Principles

1. **Fail-Fast**: Invalid auth = immediate 401/403, no silent fallbacks
2. **IDOR Protection**: `verify_ownership()` returns "not found" not "access denied"
3. **Role Hierarchy**: ADMIN > TEACHER > MEMBER > REGISTERED
4. **Graph-Native**: Sessions stored in Neo4j, no external auth dependencies

## Files Reference

| File | Purpose |
|------|---------|
| `/core/auth/session.py` | Session helpers, `UserUID` type, decorators |
| `/core/auth/roles.py` | Role-based decorators, permission checking |
| `/core/auth/graph_auth.py` | `GraphAuthService` for sign_in/sign_up |
| `/core/auth/__init__.py` | Public API exports |

## Graph-Native Session Model

SKUEL uses **graph-native authentication** where all auth data lives in Neo4j:

```
(User)-[:HAS_SESSION]->(Session)
     |-[:HAS_RESET_TOKEN]->(PasswordResetToken)
     |-[:HAS_AUTH_EVENT]->(AuthEvent)
```

### Session Structure

```python
@dataclass(frozen=True)
class Session:
    uid: str                    # "session.abc123..."
    user_uid: str               # "user.mike"
    token: str                  # Hashed session token
    created_at: datetime
    expires_at: datetime
    ip_address: str | None
    user_agent: str | None
    is_active: bool
```

### Sign In Flow

```python
from core.auth import GraphAuthService

# Sign in creates session node in Neo4j
result = await graph_auth.sign_in(
    email="user@example.com",
    password="securepass123",
    ip_address=request.client.host,
    user_agent=request.headers.get("user-agent")
)

if result.is_ok:
    session_token = result.value["session_token"]
    user_uid = result.value["user_uid"]
    # Set HTTP-only cookie with session token
```

### Session Validation

```python
# Fast path: Read from cookie (no DB call)
user_uid = get_current_user(request)  # Returns None if not logged in

# Strict path: Validate in Neo4j (DB call)
user_uid = require_authenticated_user(request)  # Raises 401 if invalid

# Full validation with session refresh
result = await graph_auth.validate_session(session_token)
```

---

## Admin-Initiated Password Reset

SKUEL uses admin-initiated password reset (no email service required):

### Flow

```
1. Admin generates reset token via Admin Dashboard
   ↓
2. Admin shares token with user (out-of-band: email, chat, etc.)
   ↓
3. User enters token + new password at /reset-password
   ↓
4. Token verified, password updated, token invalidated
```

### Admin Side

```python
# Admin generates token
token_result = await graph_auth.admin_generate_reset_token(
    user_uid="user.johndoe",
    admin_uid="user.admin",
    ip_address=admin_ip,
    user_agent=admin_ua
)

if token_result.is_ok:
    token = token_result.value  # Plain token to share with user
    # Token stored hashed in Neo4j, expires in 24 hours
```

### User Side

```python
# User resets password with token
result = await graph_auth.reset_password_with_token(
    token_value=token_from_admin,
    new_password="newsecurepass123",
    ip_address=user_ip,
    user_agent=user_ua
)
```

### Admin Dashboard Routes

- `GET /admin/users/{uid}/reset-password` - Show reset token form
- `POST /admin/users/{uid}/reset-password` - Generate token

---

## Rate Limiting

SKUEL implements rate limiting via graph queries:

### Login Rate Limiting

- **Threshold:** 5 failed attempts
- **Lockout:** 15 minutes
- **Scope:** Per email address

```python
# Automatically enforced by GraphAuthService.sign_in()
result = await graph_auth.sign_in(email, password, ip, ua)

if result.is_error and "rate limited" in result.error.message:
    # User must wait 15 minutes
    return Result.fail(Errors.business(
        rule="rate_limited",
        message="Too many failed attempts. Please wait 15 minutes."
    ))
```

### Implementation

Rate limiting is tracked via `AuthEvent` nodes:

```cypher
MATCH (u:User {email: $email})-[:HAS_AUTH_EVENT]->(e:AuthEvent)
WHERE e.event_type = 'LOGIN_FAILED'
  AND e.timestamp > datetime() - duration('PT15M')
RETURN count(e) as failures
```

---

## Security Features

| Feature | Implementation |
|---------|----------------|
| **Password Hashing** | Bcrypt with automatic salt |
| **Session Tokens** | Cryptographically random, stored hashed |
| **HTTP-Only Cookies** | Prevents XSS access to tokens |
| **Secure Flag** | Cookies only sent over HTTPS |
| **Session Binding** | Optional IP/UA binding |
| **Token Expiry** | 30 days default, configurable |
| **Reset Token Expiry** | 24 hours |
| **Audit Logging** | All auth events stored as graph nodes |

---

## Route Factory Auth Matrix
*Last updated: 2026-01-24*

**Core Principle:** "Authentication patterns are explicit per factory type"

Quick reference for auth behavior across all route factories in `/adapters/inbound/route_factories/`:

| Factory | Auth Required | Content Scope | Role Support | Use Case |
|---------|--------------|---------------|--------------|----------|
| **CRUDRouteFactory** (user-owned) | Always for create; configurable for read | `scope=ContentScope.USER_OWNED` | Optional | Tasks, Goals, Habits, Events, Choices, Principles |
| **CRUDRouteFactory** (shared) | Create only | `scope=ContentScope.SHARED` | Optional | KU, LP, MOC (public read) |
| **StatusRouteFactory** | Always | Always USER_OWNED | No | activate, pause, complete, archive |
| **CommonQueryRouteFactory** (mine) | Always | Implied via user_uid | No | by-status, by-category, user queries |
| **CommonQueryRouteFactory** (admin) | Always | No | ADMIN required | Query any user's data |
| **IntelligenceRouteFactory** | Always | No (read-only) | No | analytics, recommendations, patterns |
| **AnalyticsRouteFactory** | Configurable | No | Optional | Domain-specific analytics |

### Key Patterns

**1. Content Scope (`scope` parameter):**
```python
from core.models.enums import ContentScope

# Activity domains - user-owned content
factory = CRUDRouteFactory(
    service=tasks_service,
    scope=ContentScope.USER_OWNED  # Default - ownership verification via get_for_user()
)

# Curriculum domains - shared content
factory = CRUDRouteFactory(
    service=ku_service,
    scope=ContentScope.SHARED  # No ownership checks, auth optional for reads
)
```

**2. Admin Override (CommonQueryRouteFactory):**
- No `user_uid` param → returns current user's data
- With `user_uid` param → requires ADMIN role to query other users

**3. Role vs Scope:**
- When `require_role` is set, `scope` is ignored
- Role-based access disables ownership checks
- Use for admin dashboards, teacher content creation

**See:** Individual factory docstrings in `/adapters/inbound/route_factories/` for implementation details.

---

## See Also

- [ADR-018: User Roles Four-Tier System](/docs/decisions/ADR-018-user-roles-four-tier-system.md)
- [ADR-022: Graph-Native Authentication](/docs/decisions/ADR-022-graph-native-authentication.md)
- `/docs/patterns/OWNERSHIP_VERIFICATION.md`
