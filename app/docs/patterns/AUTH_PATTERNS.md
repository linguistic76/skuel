---
title: Authentication Patterns in SKUEL
updated: '2026-09-23'
category: patterns
related_skills: [security]
related_docs: []
---
# Authentication Patterns in SKUEL

This document describes the authentication and authorization patterns used throughout SKUEL, including when to use each pattern and why.

## Related Skills

For implementation guidance, see:
- [@security](../../.claude/skills/security/SKILL.md)

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
    /explore/ku/{uid}, /path-steps, /path-steps/{uid}/details,
    /learning-paths, /lp/{uid}, /library, /library/resources
  Auth pages: /login, /register, /forgot-password, /reset-password

AUTHENTICATED (require_authenticated_user)
  ContentScope.USER_OWNED:
    /today, /settings, /tasks, /goals, /habits, /events, /choices, /principles,
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

The Ku reading page (`/explore/ku/{uid}`, `learning_loop_routes.py`) and `/path-steps` (`path_steps_ui.py`) are the live instances; every other SHARED content page follows them.

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

@rt("/api/tasks/list")
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
async def list_all_users(request: Request, current_user: Any = None):
    # current_user is the FULL User entity (not just uid)
    admin_uid = current_user.uid
    admin_role = current_user.role

    # Can use User entity methods
    if current_user.can_manage_users():
        return await user_service.list_all()


@rt("/api/exercises/for-curriculum", methods=["GET"])
@require_teacher(get_user_service)
async def get_exercises_for_curriculum(request: Request, current_user: Any = None):
    # Teachers and Admins read the exercises that require a curriculum uid
    curriculum_uid = request.query_params.get("curriculum_uid")
    return await exercises_service.get_exercises_for_curriculum(curriculum_uid)
```

**The one spelling is `current_user: Any = None`, next to a parameter named `request`.**
FastHTML fills a handler's parameters from the request by reading the registered callable's
signature. The role decorator publishes the handler's signature *minus* `current_user` on its
wrapper (`signature_for_binding` in `adapters/inbound/auth/roles.py`), so FastHTML never binds
that name: a value a caller sends under it — query string, header, form field — is neither read
nor coerced, and the decorator's assignment is its only writer. `Any` rather than `User` on
purpose — it is a documented boundary (`# boundary: injected-user`, [ANY_USAGE_POLICY.md](ANY_USAGE_POLICY.md)):
FastHTML binds a dataclass-annotated parameter from the request body, so `current_user: User` on
a handler that *lacks* the decorator would receive a `User` built from the caller's own form
fields (a caller-chosen `uid`), while `Any = None` on the same mistake leaves `None` and the
first attribute read fails. The default because a request never carries the value. Any other
spelling (bare, no default, another annotation) or a missing parameter fails at decoration time
with a `TypeError` naming the spelling — at registration, so the first test that registers the
route fails. The handler's **first** parameter is `request`, even when its body never reads it:
the wrapper receives the request from FastHTML under that name and passes it on as the handler's
first positional argument, so another name (`_request`) or position would leave the wrapper's own
`request` unfilled on every call — the same check refuses that at decoration.

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
async def create_item(request: Request, current_user: Any = None):
    teacher_uid = current_user.uid

# ❌ WRONG — redundant auth call
@require_teacher(get_user_service)
async def create_item(request: Request, current_user: Any = None):
    teacher_uid = require_authenticated_user(request)  # Already done by decorator
```

**Available decorators:**
- `@require_role(UserRole.ADMIN, getter)` - Explicit role requirement
- `@require_admin(getter)` - Shortcut for ADMIN
- `@require_teacher(getter)` - Shortcut for TEACHER

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

### Checking Admin for Conditional Rendering (Without Decorator)

The session readers (`get_current_user`, `get_is_admin`, `get_is_teacher` — no DB call)
are the **route** layer's API, and the session stays the single source of truth
(`core/utils/auth_context.py`'s own contract). In **route code** (`adapters/inbound/`),
read them directly — `get_current_user(request)` is how the explore pages tell an
anonymous reader from a signed-in one (`learning_loop_routes.py`):

```python
from adapters.inbound.auth import get_current_user

@rt("/explore/ps/{uid}/content")
async def explore_ps_content_fragment(request: Request, uid: str) -> Any:
    user_uid = get_current_user(request)  # session read, no DB call; None when anonymous
    ...
```

`get_is_admin(request)` / `get_is_teacher(request)` are the same shape for the role flags.

In **UI components** (`ui/`), never import `adapters.inbound.auth` — lint rule
SKUEL027 fails closed on any runtime ui → adapters import. Read the
middleware-set auth context instead (the mirror exists for the render side, which
takes no `request`):

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

## Navbar Authentication Pattern

The navbar is one bar for every role; which doors it shows (sign-out, the inbox, the
role-gated Teaching and Admin doors) depends on the authentication state. To keep that
consistent across pages, **always pass the `request` object** through to layout functions.

### The Problem

Without the request, a layout renders the unauthenticated state — "Login/Sign Up"
instead of the user's avatar, and no role doors for an admin or teacher.

### The Solution: `create_navbar_for_request()`

Use `create_navbar_for_request(request)` for automatic auth detection. Auth
state comes from the middleware-set auth context (`core/utils/auth_context.py`,
written per request by `AuthContextMiddleware` from the session) — the navbar
never imports `adapters.inbound.auth`:

```python
from ui.layouts.navbar import create_navbar_for_request

# ✅ RECOMMENDED: Auto-detects auth from the request-scoped auth context
navbar = create_navbar_for_request(request, active_page="tasks")

# create_navbar() is the primitive underneath — BasePage and the request helper call
# it; a handler calls it directly only where no request-scoped context exists
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

One navbar for every role (`ui/layouts/navbar.py`); what changes by auth state is which doors render:

| User State | Left | Centre (sm+) | Right | Bottom nav (<sm) |
|------------|------|--------------|-------|------------------|
| Unauthenticated | SKUEL (→ `/`) | Library, PathSteps | Login / Sign Up | Library, PathSteps |
| Authenticated (any role) | SKUEL (→ `/explore`) | Tasks+, Library, PathSteps, Submissions | Askesis, Shared-inbox, Bell, Avatar (→ `/settings`), Sign out (sm+) | the same four tabs |
| + Teacher | | + Teaching (lg+) | | (Teaching is a `/settings` row below lg) |
| + Admin | | + Teaching, Admin (lg+) | | (both are `/settings` rows below lg) |

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

Server-side revocation takes effect on the target's very next request because of step 4.
Every revoking operation commits its credential/privilege write AND the session sweep in
ONE Cypher transaction on `SessionBackend`: `change_password_and_revoke_sessions`
(compare-and-set on the hash the old password was verified against),
`reset_password_and_revoke_sessions` (claims the reset token under its write-lock — of
concurrent redemptions exactly one wins), `update_role_and_revoke_sessions`, and
`deactivate_user_and_revoke_sessions`. A failed sweep fails the whole write, so the caller
is never told "done" while old sessions still validate. See `/adapters/inbound/auth/context_middleware.py` for
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
    session_token: str = field(repr=False)  # Raw token: cookie only, never in Neo4j or repr()
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
- `GET /reset-password?token=` - Token + new password form
- `POST /reset-password/submit` - Process password reset
- `POST /api/admin/users/reset-password?uid=` - Admin generates a reset token for a user (no email is sent; the admin hands the token over) — `admin_api.py`, `@require_admin`; the plain `@rt` also answers GET

## Auth Form Validation

Auth forms (registration, login, password reset) use Pydantic request models for validation, following the same boundary-validation pattern as API routes.

**Models** (`core/models/auth/auth_request.py`):

| Model | Fields (**bold** = `SecretStr`) | Validators |
|-------|--------|------------|
| `RegistrationRequest` | username, email, display_name, **password**, **confirm_password**, accept_terms, invite_code | Password match, terms acceptance |
| `LoginRequest` | username (email or username), **password** | Required fields |
| `ResetPasswordRequest` | **token**, **password**, **confirm_password** | Password match |
| `ForgotPasswordRequest` | email | Required field |

**Usage in route handlers:**

```python
from pydantic import SecretStr

from core.models.auth import RegistrationRequest

form_data = await request.form()
try:
    reg = RegistrationRequest(
        username=safe_form_string(form_data.get("username")),
        email=safe_form_string(form_data.get("email")),
        password=SecretStr(safe_form_string(form_data.get("password"))),
        ...
    )
except ValidationError as e:
    return render_error(first_validation_error(e))

await graph_auth.sign_up(email=reg.email, password=reg.password.get_secret_value(), ...)
```

Cross-field validation (password matching, terms acceptance) uses `@model_validator(mode="after")` — business rules live in the model, not the route handler. `SecretStr` compares by secret value, so the password-match validators read unchanged.

### Secret-bearing fields are unprintable

Every field that holds a credential is masked at the declaration, so no log line,
traceback frame or debugger view can disclose it:

| Field | Mechanism |
|-------|-----------|
| `RegistrationRequest` / `LoginRequest` / `ResetPasswordRequest` passwords + reset token | `pydantic.SecretStr` — `repr` and `model_dump()` render `**********` |
| `Session.session_token` | `field(repr=False)` |
| `PasswordResetToken.token` | `field(repr=False)` |
| `User.password_hash` | `field(repr=False)` — a bcrypt digest is offline-crackable |
| `DatabaseConfig.neo4j_password`, `CacheConfig.redis_password`, `MessageQueueConfig.password` | `field(repr=False)` |

Wrap at the boundary (`SecretStr(...)` on the form value), read at the point of use
(`.get_secret_value()`), and never in between. Pinned by
`tests/unit/models/test_secret_fields_unprintable.py`, which asserts both the rendered
`repr()` and the field declaration itself.

⚠ `ValidationError.errors()[0]["input"]` carries the **raw submitted value** even for a
`SecretStr` field. `_first_validation_error` (`adapters/inbound/auth_ui.py`) reads only
`type`, `msg` and `loc`; never log a `ValidationError` from an auth route whole.

### User node schema (the ruling, July 2026 — Arc F/G12)

The graph `:User` node carries exactly the `User` dataclass field names (`core/models/user/user.py`):

- **Username lives in `title`** — there is NO `username` property. `get_user_by_username` matches `{title: $username}`; login resolves username → `title` → node → `.email` → authenticate by email.
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

### Per-IP Throttle

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
