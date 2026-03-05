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

### Authenticated Routes (User Required)

| Route Pattern | File | Notes |
|---------------|------|-------|
| `/search/**` | `search_routes.py` | User-scoped search |
| `/api/visualizations/**` | `visualization_routes.py` | User data visualization |
| `/graphql` | `graphql_routes.py` | GraphQL API |
| `/profile/**` | Various | User profile management |
| `/tasks/**`, `/goals/**`, etc. | Domain routes | Activity domain CRUD |

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
| `/ws/ingest/progress/**` | `ingestion_api.py` | WebSocket progress (closes 4003 if unauthorized) |
| `/ingest` | `ingestion_routes.py` | Ingestion dashboard |
| `/debug-session` | `auth_routes.py` | Session debugging |
| `/whoami` | `auth_routes.py` | User identity debugging |
| `/admin/**` | `admin_routes.py` | Admin dashboard |

## Security Patterns

### User-Owned Data Access

All user-owned entities use ownership verification:

```python
# Service-level ownership check
result = await service.verify_ownership(uid, user_uid)
if result.is_error:
    return result  # Returns 404 for both missing and unauthorized

# Decorator-based ownership check
@with_ownership(get_service)
async def route(request, user_uid, entity):
    # entity is pre-verified to belong to user_uid
```

**Key principle:** Return "not found" (not "access denied") to prevent information leakage.

### Admin Role Verification

```python
def get_user_service():
    """Named function per SKUEL012."""
    return services.user_service

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
| `SKUEL_INGESTION_ALLOWED_PATHS` | Allowed ingestion paths (colon-separated) | None (all paths) |
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
| Cypher injection guards — labels + field names | `_validate_label()` (NeoLabel allowlist) and `_validate_identifier()` (regex) added to `build_distinct_values_query`, `build_hierarchy_query` in `crud_queries.py`; same guards plus `_validate_similarity()` added to all 5 DDL methods in `neo4j_schema_manager.py` |
| IDOR fix — `GET /api/submissions/shared-users` | Ownership failure now returns 404 (not 403) — prevents UID enumeration; matches documented pattern |
| Ownership bypass fix — `get_shared_users` | Route now fails fast with `Errors.system()` when `core_service` is absent instead of silently skipping ownership check |
| Service name validation — `POST /api/services/register` | `service_name` validated against `^[a-zA-Z0-9_-]{1,64}$` pattern to prevent phantom service registration |

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
