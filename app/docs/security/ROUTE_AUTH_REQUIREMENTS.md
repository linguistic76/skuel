---
related_skills: [security]
---
# Route Authentication Requirements

**Date:** 2026-01-21
**Version:** 1.0 (Security Hardening Release)

This document defines the authentication requirements for all SKUEL routes.

## Authentication Levels

| Level | Description | Decorator/Check |
|-------|-------------|-----------------|
| **Public** | No authentication required | None |
| **Authenticated** | Requires logged-in user | `require_authenticated_user(request)` |
| **Admin** | Requires admin role | `@require_admin(get_user_service)` |

## Route Categories

### Public Routes (No Authentication)

| Route Pattern | File | Rationale |
|---------------|------|-----------|
| `/nous/**` | `nous_routes.py` | Public knowledge documentation |
| `/register` | `auth_routes.py` | User registration |
| `/login` | `auth_routes.py` | User login |
| `/forgot-password` | `auth_routes.py` | Password reset initiation |
| `/reset-password` | `auth_routes.py` | Password reset with token |
| `/api/devices/enroll` | `device_routes.py` | Agent enrollment (ADR-075): the one-time pairing code IS the credential (hashed, 10-min TTL, single-use); IP rate-limited |
| `WS /ws/agent` | `device_routes.py` | Vault-agent channel (ADR-075): Ed25519 challenge-signature handshake authenticates the device; pre-accept per-IP rate limit + concurrent-handshake cap |

### Authenticated Routes (User Required)

| Route Pattern | File | Notes |
|---------------|------|-------|
| `/search/**` | `search_routes.py` | User-scoped search |
| `/api/visualizations/**` | `visualization_routes.py` | User data visualization |
| `/graphql` | `graphql_routes.py` | GraphQL API |
| `/profile/**` | Various | User profile management |
| `/tasks/**`, `/goals/**`, etc. | Domain routes | Activity domain CRUD |
| `/settings/devices/**`, `/api/devices/pairing-code`, `/api/devices/{uid}/revoke` | `device_routes.py` | Vault-agent device management (ADR-075) |

### Admin Routes (Admin Role Required)

| Route Pattern | File | Notes |
|---------------|------|-------|
| `/api/health` | `system_api.py` | System health check |
| `/api/status` | `system_api.py` | System status |
| `/api/metrics` | `system_api.py` | System metrics |
| `/api/diagnostics` | `system_api.py` | System diagnostics |
| `/api/services/**` | `system_api.py` | Service registration |
| `/api/alerts/**` | `system_api.py` | Alert management |
| `/api/ingest/**` | `ingestion_routes.py` | Content ingestion |
| `/ingest` | `ingestion_routes.py` | Ingestion dashboard |
| `/debug-session` | `auth_routes.py` | Session debugging |
| `/whoami` | `auth_routes.py` | User identity debugging |
| `/admin/**` | `admin_routes.py` | Admin dashboard |

## Security Patterns

### User-Owned Data Access

All user-owned entities use ownership verification:

```python
from adapters.inbound.route_factories import verify_entity_ownership, require_owned_entity

# API routes — verify_entity_ownership helper
ownership_error = await verify_entity_ownership(service, uid, user_uid, "domain")
if ownership_error:
    return ownership_error  # Returns 404 Result

# UI routes — require_owned_entity helper
entity, error = await require_owned_entity(service, uid, user_uid, "Entity")
if error:
    return error  # Returns 404 Response

# Decorator-based ownership check (alternative)
@with_ownership(get_service)
async def route(request, user_uid, entity):
    # entity is pre-verified to belong to user_uid
```

**Key principle:** Return "not found" (not "access denied") to prevent information leakage.

### Admin Role Verification

```python
get_user_service = make_service_getter(services.user)

@rt("/api/admin/endpoint")
@require_admin(get_user_service)
async def admin_route(request, current_user):
    # current_user is guaranteed to be admin
```

### Session Configuration

```python
# Session cookie settings (session.py)
SESSION_COOKIE_NAME = "skuel_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
same_site = "strict"  # CSRF protection
https_only = True  # In production
```

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `SKUEL_DEFAULT_DEV_USER` | Development fallback user | `user.mike` |
| `SKUEL_INGESTION_ALLOWED_PATHS` | Allowed ingestion paths (colon-separated). Explicit override for multi-vault / staging setups. | None — falls back to `INGESTION_PATH` |
| `INGESTION_PATH` | Single ingestion vault root. Also the documented default vault location. **Fallback** when `SKUEL_INGESTION_ALLOWED_PATHS` is unset. If both unset, ingestion fails closed (every path rejected). | `/home/mike/0bsidian/0vault/` |
| `SESSION_SECRET_KEY` | Session signing key | Generated (dev), **required** in production/staging |
| `SKUEL_ENVIRONMENT` | Environment name | `local` |

## Security Decisions (January 2026)

### Removed Routes

| Route | Reason |
|-------|--------|
| `/switch-user` | User impersonation vulnerability |

### Hardened Routes

| Change | Rationale |
|--------|-----------|
| GraphQL requires auth | No development fallback |
| Visualization IDOR fixed | No user_uid query param |
| System API admin-only | Prevents info disclosure |
| SameSite strict | Enhanced CSRF protection |
| Debug endpoints admin-only | Prevents session info leakage |

## Security Hardening (March 2026)

| Change | Rationale |
|--------|-----------|
| WebSocket ingestion requires admin session | Was unauthenticated; closes with 4003 before `ws.accept()` |
| GraphQL GET requires auth | Playground UI was accessible without login |
| Cypher injection guards — labels + field names | `validate_label()` and `validate_identifier()` promoted to shared `_helpers.py`, applied across all 5 query builder modules (`crud_queries.py`, `domain_queries.py`, `relationship_queries.py`, `semantic_queries.py`, `intelligence_queries.py`) — 17 functions validate labels, field names, relationship types, and property keys before f-string interpolation; same guards plus `_validate_similarity()` added to all 5 DDL methods in `neo4j_schema_manager.py` |
| IDOR fix — `GET /api/submissions/shared-users` | Ownership failure now returns 404 (not 403) — prevents UID enumeration; matches documented pattern |
| Ownership bypass fix — `get_shared_users` | Route now fails fast with `Errors.system()` when `core_service` is absent instead of silently skipping ownership check |
| Service name validation — `POST /api/services/register` | `service_name` validated against `^[a-zA-Z0-9_-]{1,64}$` pattern to prevent phantom service registration |
| Submissions API session auth — all 19 routes in `submissions_api.py` | `user_uid` no longer accepted as query param or form field; all routes use `require_authenticated_user(request)` from session. Single-submission routes verify ownership via `_get_owned_submission()` returning 404 for non-owned resources. Closes IDOR where callers could submit files as or browse submissions of another user |

## Security Hardening (May 2026)

| Change | Rationale |
|--------|-----------|
| AI-route owner gating (PR #73, `760d375b`) | `ai_routes.py::_ai_route` was discarding the auth result and passing only `uid` to `facade.ai`, so any logged-in user could read another user's PRIVATE entity via the AI endpoints and burn LLM budget. Fix: `ContentScope` enum on each `AIRouteSpec` (default `USER_OWNED`); USER_OWNED routes route through `verify_entity_ownership` (404, not 403) before invoking AI. The 13 ps/lp specs are explicitly `SHARED`. Enum-not-string-set so a domain-attr rename can't silently flip a route to fail-open. |
| WebSocket admin re-checks Neo4j role (PR #91, `07b5bae4`) | `require_websocket_admin(ws, user_service)` fetches the user and gates on `User.has_permission(UserRole.ADMIN)` — mirrors HTTP `@require_admin`. No longer trusts the session `is_admin` cookie flag, so a user demoted from ADMIN loses WS access on next connection rather than only on re-login. |
| Allowlisted Cypher operators + sort directions (PR #92, `b4bf5e01`) | `validate_cypher_operator` + `validate_sort_direction` added to `core/utils/validation_helpers.py`. `query_optimizer._validate_request` centrally gates unsafe constraint property/operator + sort property/direction so all six plan-builders inherit the check from one point. `ModelQueryBuilder.filter(**kwargs)` validates keys with `validate_field_name` (silent-drop with warning, mirrors `order_by`). Closed a latent injection seam — not exploitable from external routes today (callers internal). |
| Ingestion path default-denied (PR #93, `d080bf4e`) | `_validate_ingestion_path` precedence: `SKUEL_INGESTION_ALLOWED_PATHS` > `INGESTION_PATH` > fail closed. Was: ANY absolute host path was reachable when the env var was unset. Admin + CSRF bounded impact, but the role gate is for ownership not filesystem reach. |
| Per-IP login throttle + bcrypt 72-byte UX (PR #94, `cb1c9eff`) | Per-IP: `is_ip_rate_limited` (20 fails/15min, by `AuthEvent.ip_address`) ordered **before** email lookup so a throttled IP can't enumerate accounts. `"unknown"` sentinel short-circuits CLI/non-HTTP paths. Bcrypt: `validate_password` enforces `MAX_PASSWORD_BYTES = 72` (UTF-8 bytes, not chars — a 36-emoji password is 144 bytes) front-running bcrypt's hard limit, so the user gets a clean field-level error instead of a generic broad-except surface. |

## Verification Checklist

When adding new routes:

- [ ] Determine authentication level (public/authenticated/admin)
- [ ] Use appropriate decorator or check function
- [ ] For user data: implement ownership verification
- [ ] Document in this file
- [ ] Test unauthorized access returns appropriate status

## Related Documentation

- `/docs/patterns/AUTH_PATTERNS.md` - Authentication patterns
- `/docs/patterns/OWNERSHIP_VERIFICATION.md` - Ownership verification
- `/docs/decisions/ADR-022-graph-native-authentication.md` - Auth architecture
