---
title: Authentication Patterns in SKUEL
updated: '2026-09-05'
category: patterns
related_skills: [security]
related_docs: []
---
# Authentication Patterns in SKUEL
*Last updated: 2026-07-24*

This document describes the authentication and authorization patterns used throughout SKUEL, including when to use each pattern and why.

## Overview

SKUEL uses **graph-native authentication** (sessions stored in Neo4j) with cookie-based session management. The access model follows `ContentScope` directly: shared content is publicly readable, user-owned content requires authentication.

| Pattern | Function | Returns | Use Case |
|---------|----------|---------|----------|
| **Strict** | `require_authenticated_user(request)` | `UserUID` | API routes, USER_OWNED UI pages |
| **Optional** | `get_current_user(request)` | `UserUID \| None` | SHARED content pages (enrich if authenticated) |
| **Lenient** | `get_current_user_or_default(request)` | `UserUID` | Dev-only fallback (raises 401 in prod) |
| **Role-Based** | `@require_admin(service_getter)` | `current_user: User` | Protected admin/teacher routes |

## Page Access Model

`ContentScope` is the single source of truth for page access. Do not make ad-hoc auth decisions at the route level — derive the pattern from the content type.

```
PUBLIC (no auth required)
  ContentScope.SHARED read views:
    /ku, /ku/{uid}, /path-steps, /path-steps/{uid}/details,
    /learning-paths, /lp/{uid}, /library, /library/resources
  Auth pages: /login, /register, /forgot-password, /reset-password

AUTHENTICATED (require_authenticated_user)
  ContentScope.USER_OWNED:
    /profile, /tasks, /goals, /habits, /events, /choices, /principles,
    /submissions, /calendar, /activity-reports, /library/exercises
  All API mutation routes (POST, PUT, DELETE)

ROLE-GATED
  TEACHER+: create/edit curriculum (API routes)
  ADMIN:    user management, finance, admin dashboard
```

### Optional Auth Pattern (SHARED pages with user enhancements)

Shared content pages can enrich the view with user-specific state (bookmarks, learning progress) when the user is authenticated, without requiring it:

```python
# CORRECT: optional auth for SHARED content
user_uid: str | None = get_current_user(request)
if user_uid:
    state_result = await service.get_learning_state(user_uid, uid)
    # populate learning state variables
# render page; show "Log in to track progress" link when user_uid is None

# WRONG: blocking SHARED content behind auth
user_uid = require_authenticated_user(request)  # ← do not use for SHARED pages
```

The `/ku` index established this pattern (line 470 in `ku_ui.py`); all other SHARED content pages follow it.

## The UserUID Type

```python
from adapters.inbound.auth import UserUID

# UserUID = NewType("UserUID", str) — MyPy rejects plain str where UserUID is required
# Examples: "user_mike", "user_alice"
user_uid: UserUID = require_authenticated_user(request)
```

`UserUID` is implemented as a `NewType` (a nominal subtype of `str`). Zero runtime cost — `UserUID("user_mike")` returns `"user_mike"` — but MyPy treats it as a distinct type from plain `str`, catching accidental mixing of `UserUID`, `TaskUID`, `SessionUID`, etc.

- **Type safety**: Passing a raw `str` or wrong UID type where `UserUID` is required is a MyPy error
- **Documentation**: Makes expected format clear at call sites
- **Single source of truth**: Defined in `core/models/type_hints.py`, re-exported from `adapters.inbound.auth`

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
from adapters.inbound.auth import make_service_getter, require_admin, require_teacher

get_user_service = make_service_getter(services.user)


@rt("/api/admin/users")
@require_admin(get_user_service)
async def list_all_users(request, current_user):
    # current_user is the FULL User entity (not just uid)
    #
    # ⚠️ If you ANNOTATE the param, it MUST default to None:
    # `current_user: Any = None`. FastHTML resolves the wrapped signature
    # and 400s ("Missing required field: current_user") on an annotated
    # param with no default BEFORE the decorator can inject it.
    # Unannotated params resolve to None, so the bare form also works.
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

**Why `current_user: User` instead of `user_uid: UserUID`?**
Role checking requires fetching the user from the database anyway, so the decorator provides the full entity to avoid duplicate fetches.

**Do not mix patterns:** When using a role decorator, use `current_user.uid` for the user identifier — do NOT also call `require_authenticated_user(request)`. The decorator already authenticates; the extra call is redundant.

```python
# ✅ CORRECT — use current_user.uid from decorator
@require_teacher(get_user_service)
async def create_item(request, current_user):
    teacher_uid = current_user.uid

# ❌ WRONG — redundant auth call
@require_teacher(get_user_service)
async def create_item(request, current_user):
    teacher_uid = require_authenticated_user(request)  # Already done by decorator
```

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

After getting `user_uid`, verify ownership before operating on entities. Use the `verify_entity_ownership` helper for API routes:

```python
from adapters.inbound.route_factories import verify_entity_ownership

@rt("/api/goals/{uid}")
@boundary_handler()
async def update_goal(request, uid: str):
    user_uid = require_authenticated_user(request)

    # Returns error Result on failure, None on success (404, not 403 — prevents UID enumeration)
    ownership_error = await verify_entity_ownership(
        goals_service, uid, user_uid, "goal"
    )
    if ownership_error:
        return ownership_error

    # Build the typed intent from the validated request (ADR-066) — never a raw dict.
    intent = GoalUpdateRequest.model_validate(await request.json()).to_intent()
    return await goals_service.update(uid, intent)
```

For UI routes returning `Response`, use `require_owned_entity`:

```python
from adapters.inbound.route_factories import require_owned_entity

entity, error = await require_owned_entity(service, uid, user_uid, "Goal")
if error:
    return error  # Returns Response(404)
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

### Checking Admin for Conditional Rendering (Without Decorator)

In **route code** (`adapters/inbound/`), read the session directly:

```python
from adapters.inbound.auth import get_is_admin

@rt("/some-page")
async def some_page(request):
    is_admin = get_is_admin(request)  # Reads from session, no DB call
    ...
```

In **UI components** (`ui/`), never import `adapters.inbound.auth` — lint rule
SKUEL027 fails closed on any runtime ui → adapters import. Read the
middleware-set auth context instead:

```python
from core.utils.auth_context import current_auth_state

def render_section():
    auth = current_auth_state()  # AuthState(user_uid, is_admin, is_teacher)
    if auth.is_admin:
        return SectionWithAdminLink()
    return SectionStandard()
```

`AuthContextMiddleware` (`adapters/inbound/auth/context_middleware.py`)
mirrors the session's auth flags into `core/utils/auth_context.py` once per
request — same shape as the CSRF token context. The session stays the single
source of truth; outside a request (unit renders, WebSocket paths), the
context degrades to unauthenticated defaults.

## Navbar Authentication Pattern (January 2026)

The navbar displays different links based on authentication state. To ensure consistent navbar behavior across all pages, **always pass the `request` object** through to layout functions.

### The Problem

Without passing the request, layouts default to unauthenticated state:
- Shows "Login/Sign Up" instead of user dropdown
- Admin users don't see SKUEL logo or admin-specific navbar
- Profile Hub link may not work correctly

### The Solution: `create_navbar_for_request()`

Use `create_navbar_for_request(request)` for automatic auth detection. Auth
state comes from the middleware-set auth context (`core/utils/auth_context.py`,
written per request by `AuthContextMiddleware` from the session) — the navbar
never imports `adapters.inbound.auth`:

```python
from ui.layouts.navbar import create_navbar_for_request

# ✅ RECOMMENDED: Auto-detects auth from the request-scoped auth context
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

Pages build on `BasePage` (see CLAUDE.md § UI Component Pattern); passing
`request` makes it delegate to `create_navbar_for_request()` internally:

```python
from ui.layouts.base_page import BasePage

@rt("/library")
async def library_page(request: Request) -> Any:
    return BasePage(
        content=content,
        title="Library",
        request=request,  # Auto-detects auth for navbar + bottom nav
        active_page="library",
    )
```

### What the Navbar Shows

| User State | Left Section | Center | Right Section |
|------------|--------------|--------|---------------|
| Unauthenticated | Icon links | None | Login / Sign Up |
| Authenticated (Regular) | Avatar + Icon links | Teaching (if teacher) | Search + Notifications |
| Authenticated (Admin) | SKUEL logo (→ `/`) | None | Avatar (→ `/`) + Sign out |

### Files Reference

| File | Purpose |
|------|---------|
| `/ui/layouts/navbar.py` | `create_navbar()`, `create_navbar_for_request()`, bottom-nav variants |
| `/ui/layouts/base_page.py` | `BasePage()` / `AuthPage()` — pass `request` for auto-detected navbar auth |
| `/ui/layouts/nav_config.py` | Type-safe `NavItem` definitions consumed by the navbar |

## Session Flow

```
1. User logs in via /login
   ↓
2. GraphAuthService.sign_in() creates Session node in Neo4j
   ↓
3. set_current_user() stores user_uid + session_token in cookie
   ↓
4. On each request:
   - AuthContextMiddleware validates session_token against the :Session node
     (revoked/expired → cookie session cleared → forced re-login)
   - Route helpers (get_current_user() etc.) then read the cookie — the graph
     round-trip already happened once, upstream
   ↓
5. User logs out via /logout
   ↓
6. clear_current_user() removes cookie, Session node invalidated
```

Server-side revocation — `invalidate_all_user_sessions(user_uid)` on password change,
password reset, admin role change, and deactivation — takes effect on the target's very
next request because of step 4. See `/adapters/inbound/auth/context_middleware.py` for
the enforcement semantics (exempt paths, 503-without-clearing on validation errors).

## Security Principles

1. **ContentScope Drives Access**: SHARED content is public; USER_OWNED content requires auth — no ad-hoc per-route decisions
2. **Fail-Fast**: Invalid auth = immediate 401/403, no silent fallbacks
3. **IDOR Protection**: `verify_ownership()` returns "not found" not "access denied"
4. **Role Hierarchy**: ADMIN > TEACHER > MEMBER > REGISTERED
5. **Graph-Native**: Sessions stored in Neo4j, no external auth dependencies

## Files Reference

| File | Purpose |
|------|---------|
| `/adapters/inbound/auth/session.py` | Session helpers, `UserUID` type, decorators, WebSocket auth |
| `/adapters/inbound/auth/context_middleware.py` | Per-request graph-session enforcement + auth ContextVar mirror |
| `/adapters/inbound/auth_ui.py` | Auth UI routes (register, login, password reset) |
| `/adapters/inbound/rate_limit.py` | `rate_limited` (per-user) + `rate_limited_ip` (per-IP) sliding-window decorators |
| `/adapters/inbound/auth/roles.py` | Role-based decorators, permission checking |
| `/core/auth/graph_auth.py` | `GraphAuthService` for sign_in/sign_up |
| `/core/auth/__init__.py` | Public API exports |
| `/core/models/auth/auth_request.py` | Pydantic request models for auth forms |

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
    uid: str                    # "session_{hex}"
    session_token: str          # Raw token (cookie only, never stored in Neo4j)
    user_uid: UserUID               # "user_mike"
    created_at: datetime        # UTC-aware
    expires_at: datetime        # UTC-aware
    last_active_at: datetime    # UTC-aware (sliding expiration)
    ip_address: str
    user_agent: str
    is_valid: bool
    user_is_active: bool        # Cached at session creation
    token_hash: str             # SHA-256 hash stored in Neo4j
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

Graph validation happens ONCE per request in `AuthContextMiddleware` (revoked/expired
sessions are cleared before any route runs). Route code just reads the cookie:

```python
# Optional auth: read from cookie (no DB call — middleware already validated)
user_uid = get_current_user(request)  # Returns None if not logged in

# Required auth: same read, raises instead of returning None
user_uid = require_authenticated_user(request)  # Raises 401 if not logged in

# Explicit re-validation with full User fetch (rare — e.g. WebSocket handshakes)
result = await graph_auth.validate_session(session_token)
```

---

## Password Reset

SKUEL supports two password reset paths:

### Self-Service (Email)

```
1. User enters email at /forgot-password
   ↓
2. GraphAuthService.reset_password_email() sends email via Resend
   ↓
3. User clicks link → /reset-password?token=...
   ↓
4. Token verified, password updated, token invalidated
```

**Security:** `reset_password_email()` always returns `ok(True)` regardless of whether the email exists — prevents enumeration attacks.

**Configuration:** Requires `RESEND_API_KEY` and optionally `RESEND_FROM_EMAIL`, `APP_URL` env vars. Without `RESEND_API_KEY`, email reset is disabled and admin-initiated flow is the only option.

### Admin-Initiated

```python
# Admin generates token
token_result = await graph_auth.admin_generate_reset_token(
    user_uid=UserUID("user_johndoe"),
    admin_uid=UserUID("user_admin"),
    ip_address=admin_ip,
    user_agent=admin_ua
)

if token_result.is_ok:
    token = token_result.value  # Plain token to share with user
    # Token stored hashed in Neo4j, expires in 15 minutes
```

### User Side (Both Paths)

```python
# User resets password with token (from email link or admin)
result = await graph_auth.reset_password_with_token(
    token_value=token,
    new_password="newsecurepass123",
    ip_address=user_ip,
    user_agent=user_ua
)
```

### Routes

- `GET /forgot-password` - Email form for self-service reset
- `POST /forgot-password` - Send reset email
- `GET /reset-password?token=...` - Token + new password form
- `POST /reset-password/submit` - Process password reset
- `GET /admin/users/{uid}/reset-password` - Admin token form
- `POST /admin/users/{uid}/reset-password` - Admin generate token

## Auth Form Validation

Auth forms (registration, login, password reset) use Pydantic request models for validation, following the same boundary-validation pattern as API routes.

**Models** (`core/models/auth/auth_request.py`):

| Model | Fields | Validators |
|-------|--------|------------|
| `RegistrationRequest` | username, email, display_name, password, confirm_password, accept_terms | Password match, terms acceptance |
| `LoginRequest` | username (email or username), password | Required fields |
| `ResetPasswordRequest` | token, password, confirm_password | Password match |
| `ForgotPasswordRequest` | email | Required field |

**Usage in route handlers:**

```python
from core.models.auth import RegistrationRequest

form_data = await request.form()
try:
    reg = RegistrationRequest(
        username=safe_form_string(form_data.get("username")),
        email=safe_form_string(form_data.get("email")),
        ...
    )
except ValidationError as e:
    return render_error(first_validation_error(e))
```

Cross-field validation (password matching, terms acceptance) uses `@model_validator(mode="after")` — business rules live in the model, not the route handler.

### User node schema (the ruling, July 2026 — Arc F/G12)

The graph `:User` node carries exactly the `User` dataclass field names (`core/models/user/user.py`):

- **Username lives in `title`** — there is NO `username` property. `get_user_by_username` matches `{title: $username}`; login resolves username → `title` → node → `.email` → authenticate by email. (A legacy `username` property was migrated to `title` on 2026-06-12.)
- **Role lives in `role`** (NOT `user_role`), stored as the lowercase enum *value* (`"admin"`, `"member"`). Raw Cypher must compare against `.value`; model loads are alias-aware via `UserRole.from_string`.
- **`is_premium` is an independent flag, not derived from role.** Subscription checks go through `User.is_subscriber()` → `role.is_subscriber()`; a MEMBER with `is_premium=false` is by design.

---

## Rate Limiting

SKUEL enforces rate limiting at **two independent layers**:

**HTTP layer (in-process):** `rate_limited_ip` in `adapters/inbound/rate_limit.py` — a sliding-window, per-IP decorator applied directly to the four auth POST handlers before the request reaches any service. Keys are namespaced (`ip:<bucket>:<ip>`) in the module-level `_BUCKETS` store. Limits: login 10/60s, register/forgot-password/reset-password 5/300s. Returns HTTP 429 with `Retry-After`. Unknown IPs pass through.

**Graph layer:** SKUEL implements **two-axis** login rate limiting via graph queries over `AuthEvent` nodes — no separate cache or external counter.

### Per-Account Lockout

- **Threshold:** `MAX_FAILED_ATTEMPTS = 5`
- **Window:** `LOCKOUT_MINUTES = 15`
- **Scope:** Per email address

Protects a single account from credential guessing.

### Per-IP Throttle (added 2026-05)

- **Threshold:** `MAX_FAILED_ATTEMPTS_PER_IP = 20`
- **Window:** 15 minutes (same as per-account)
- **Scope:** Per client IP from `AuthEvent.ip_address`
- **`"unknown"` sentinel skips the check** for CLI / non-HTTP callers

Intentionally **looser** than per-account: a single office NAT routinely covers many users, so a 5-strike limit would lock out a shared egress IP after a few honest typos. 20/15min ≈ one wrong attempt every 45 s — well above human error rates, well below brute-force speed.

**Order matters:** the per-IP throttle is checked **before email lookup** in `GraphAuthService.sign_in`. A throttled IP gets the same response whether the email exists or not, so a credential-stuffer can't enumerate valid accounts off the rate-limit response shape.

```python
# Automatically enforced by GraphAuthService.sign_in() — IP check first, then per-account
result = await graph_auth.sign_in(email, password, ip, ua)

if result.is_error and "rate" in (result.expect_error().message or "").lower():
    # User must wait 15 minutes
    return result
```

### Implementation

```cypher
// Per-account
MATCH (u:User {email: $email})-[:HAS_AUTH_EVENT]->(e:AuthEvent)
WHERE e.event_type = 'LOGIN_FAILED'
  AND e.timestamp > datetime() - duration('PT15M')
RETURN count(e) as failures

// Per-IP (no User binding — scans AuthEvent directly)
MATCH (e:AuthEvent)
WHERE e.event_type = 'LOGIN_FAILED'
  AND e.ip_address = $ip
  AND e.timestamp > datetime() - duration('PT15M')
RETURN count(e) as failures
```

The per-IP query reuses the existing `AuthEvent.ip_address` field — no schema change.

---

## Security Features

| Feature | Implementation |
|---------|----------------|
| **Password Hashing** | Bcrypt 12 rounds + constant-time `checkpw`. `validate_password` enforces `MAX_PASSWORD_BYTES = 72` (bcrypt's hard limit) **by UTF-8 byte count, not character count** — a 36-emoji password is 144 bytes. Front-runs bcrypt so the user gets a clean field-level error instead of a generic broad-except surface. |
| **Session Tokens** | 256-bit `secrets.token_urlsafe`; only the SHA-256 **hash** is stored in Neo4j |
| **HTTP-Only Cookies** | Prevents XSS access to tokens |
| **Secure Flag** | Cookies only sent over HTTPS |
| **Session Binding** | Optional IP/UA binding |
| **Token Expiry** | 30 days default, configurable |
| **Reset Token Expiry** | 24 hours |
| **Audit Logging** | All auth events stored as graph nodes (`AuthEvent` — also the substrate for the per-IP throttle above) |

---

## Route Factory Auth Matrix
*Last updated: 2026-07-24*

**Core Principle:** "Authentication patterns are explicit per factory type"

Quick reference for auth behavior across all route factories in `/adapters/inbound/route_factories/`:

| Factory | Auth Required | Content Scope | Role Support | Use Case |
|---------|--------------|---------------|--------------|----------|
| **CRUDRouteFactory** (user-owned) | Always for create; configurable for read | `scope=ContentScope.USER_OWNED` | Optional | Tasks, Goals, Habits, Events, Choices, Principles |
| **CRUDRouteFactory** (shared) | Create only | `scope=ContentScope.SHARED` | Optional | KU, LP, MOC (public read) |
| **create_activity_field_api_routes** | Always | Always USER_OWNED | No | inline status/priority card updates |
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

- [ADR-018: User Roles Four-Tier System](../decisions/ADR-018-user-roles-four-tier-system.md)
- [ADR-022: Graph-Native Authentication](../decisions/ADR-022-graph-native-authentication.md)
- `/docs/patterns/OWNERSHIP_VERIFICATION.md`
