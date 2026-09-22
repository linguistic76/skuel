---
related_skills: [security]
updated: 2026-09-22
---
# Route Authentication Requirements

This document defines the authentication requirements for SKUEL routes — the level each
route family carries and the standing hardening rules the route layer enforces. Re-derive
a route's existence with `uv run python scripts/health/route_claims.py --file <this file>`
(the runtime catalog) before adding a row.

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
| `/health`, `/health/ready` | `system_api.py` | Liveness / readiness probes (the deploy gate reads `/health/ready`) |
| `/metrics` | `metrics_routes.py` | Prometheus exposition — auth-exempt so a local scraper can read it; production Caddy answers 403 for it (`Caddyfile`), read on-droplet via `docker compose exec` |

### Authenticated Routes (User Required)

| Route Pattern | File | Notes |
|---------------|------|-------|
| `/search/**` | `search_routes.py` | User-scoped search |
| `/api/visualizations/**` | `visualization_routes.py` | User data visualization |
| `/profile/shared`, `/profile/shared/list-fragment` | `user_profile_ui.py` | Shared-with-me inbox (the only `/profile/*` routes; `GET /profile` is a 404) |
| `/api/sidebar/badges` | `sidebar_badges_ui.py` | Tasks+ sidebar badges (OOB fragments, `UserContext` build) |
| `/settings`, `/settings/content`, `/settings/save` | `settings_routes.py` | Account page + preferences |
| `/settings/vault/sync`, `/settings/vault/preview`, `/settings/vault/preview/consent`, `/settings/vault/consent` | `vault_routes.py` | Personal-vault sync, dry-run preview and the first-run consent gate (all POST, CSRF-protected) |
| `/tasks/**`, `/goals/**`, etc. | Domain routes | Activity domain CRUD |
| `/settings/devices/**`, `/api/devices/pairing-code`, `/api/devices/{uid}/revoke` | `device_routes.py` | Vault-agent device management (ADR-075) |

### Admin Routes (Admin Role Required)

| Route Pattern | File | Notes |
|---------------|------|-------|
| `/api/health` | `system_api.py` | System health check |
| `/api/status` | `system_api.py` | System status |
| `/api/diagnostics` | `system_api.py` | System diagnostics |
| `/api/services/**` | `system_api.py` | Service registration |
| `/api/alerts/**` | `system_api.py` | Alert management |
| `/api/chunks/regenerate` | `ingestion_api.py` | Chunk regeneration (the ingestion dashboard's one API route; ingestion itself is `vault_routes.py`) |
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
```

These two helpers are the only route-layer doors; there is no decorator form.

**Key principle:** Return "not found" (not "access denied") to prevent information leakage.

### Admin Role Verification

```python
get_user_service = make_service_getter(services.user)

@rt("/api/admin/users")
@require_admin(get_user_service)
async def admin_route(request: Request, current_user: Any = None):
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
| `INGESTION_PATH` | The content vault root — the one directory the admin content sync walks. | `/home/mike/0bsidian/0vault/` |
| `SESSION_SECRET_KEY` | Session signing key | Generated (dev), **required** in production/staging |
| `SKUEL_ENVIRONMENT` | Environment name | `local` |

## Standing Hardening Rules

Each row is a rule the route layer enforces now, with the code that enforces it. The
history of how each arrived is `git log -S` on the named symbol, not this table.

| Rule | Enforced by |
|------|-------------|
| No impersonation route — there is no `/switch-user` | (absent from the route table) |
| System API is admin-only (`/api/health`, `/api/status`, `/api/diagnostics`, `/api/services/**`, `/api/alerts/**`) | `@require_admin` on every `system_api.py` handler except the two probes |
| Debug endpoints are admin-only (`/debug-session`, `/whoami`) | `@require_admin` in `auth_api.py` |
| Session cookie is `SameSite=strict` | `adapters/inbound/auth/session.py` |
| AI routes gate on ownership: a `USER_OWNED` `AIRouteSpec` runs `verify_entity_ownership` (404, never 403) before invoking the facade's `.ai`; the 13 ps/lp specs are `ContentScope.SHARED` | `ai_routes.py` — `ContentScope` on each `AIRouteSpec`, an enum so a domain-attr rename cannot flip a route to fail-open |
| Service registration validates `service_name` against `^[a-zA-Z0-9_-]{1,64}$` | `POST /api/services/register` in `system_api.py` |
| Cypher labels, field names, relationship types and property keys are validated before any f-string interpolation | `validate_label()` / `validate_identifier()` in `query/cypher/_helpers.py`, applied by the `build_*` functions; the DDL methods in `neo4j_schema_manager.py` carry their own `_validate_label` / `_validate_identifier` / `_validate_similarity`; `ModelQueryBuilder.filter` / `order_by` (`unified_query_builder.py`) → `validate_field_name`. No live builder interpolates a caller-supplied operator or sort direction; `validate_cypher_operator` / `validate_sort_direction` (`core/utils/validation_helpers.py`) are the allowlist one would use |
| No HTTP route takes a path to ingest — the reconciler walks vault roots fixed at composition | `VaultRegistry` (`core/services/vault/vault_descriptor.py`); `POST /api/vault/sync` / `/api/vault/sync/content` take an empty body |
| Login is throttled per IP (20 failures / 15 min, keyed on `AuthEvent.ip_address`) **before** the email lookup, so a throttled IP cannot enumerate accounts; `"unknown"` short-circuits CLI/non-HTTP paths | `is_ip_rate_limited` (`session_backend.py`) |
| Passwords are capped at `MAX_PASSWORD_BYTES = 72` UTF-8 bytes (bcrypt's hard limit) as a field-level validation error | `validate_password` in `core/auth/password.py` |
| Every ownership failure is a 404, never a 403 | `verify_entity_ownership` / `require_owned_entity` (OWNERSHIP_VERIFICATION.md) |

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
