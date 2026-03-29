# Security Skill

Expert guide for SKUEL's security posture — existing protections, route security checklist, and code review checks.

---

## Security Posture Summary

SKUEL has a strong security foundation built into the architecture:

| Area | Implementation | Status |
|------|---------------|--------|
| **Query injection** | Parameterized `$variables` + allowlist validation for interpolated labels/relationship types/fields | Enforced (SKUEL001, SKUEL013) |
| **Authentication** | Graph-native auth in Neo4j, `require_authenticated_user()` on all user routes | Active |
| **Authorization** | Role-based (REGISTERED/MEMBER/TEACHER/ADMIN), `@require_admin` decorator | Active |
| **Ownership verification** | Returns 404 (not 403) for entities the user doesn't own — no information leakage | Active |
| **Error stripping** | `@boundary_handler` strips internal details from HTTP responses | Active |
| **Session security** | SHA-256 hashing, `SameSite=strict`, `HttpOnly`, `Secure` in production | Active |
| **Path traversal** | `VaultConfig.validate_paths`, `restrict_access`, allowed subdirs/extensions | Active |
| **Login rate limiting** | Account lockout after failed attempts | Active |
| **Docker production** | Non-root user, minimal image | Active |

---

## Existing Security Patterns

### Parameterized Cypher (SKUEL001 — Critical)

All Neo4j queries MUST use parameter binding. Never format strings into Cypher.

```python
# CORRECT
await tx.run("MATCH (n:Entity {uid: $uid}) RETURN n", uid=entity_uid)

# VIOLATION — raw string formatting
await tx.run(f"MATCH (n:Entity {{uid: '{entity_uid}'}}) RETURN n")  # SKUEL001
```

### Cypher Interpolation Validation (Defense-in-Depth)

Neo4j cannot parameterize labels, property names, or relationship types — these must be interpolated into Cypher strings. SKUEL validates all such values at the infrastructure boundary before interpolation:

| What | Validator | Location |
|------|-----------|----------|
| **Relationship types** | `validate_relationship_type()` | `_build_direction_pattern()` in `_relationship_crud_mixin.py` (single choke point for all relationship pattern building), `traverse()` and `find_path()` in `_traversal_mixin.py`, `build_relationship_traversal_query()` and `build_graph_aware_search_query()` in `crud_queries.py` |
| **Neo4j labels** | `_validate_label()` | `crud_queries.py` — checks against `NeoLabel` enum allowlist |
| **Field/property names** | `validate_field_name()` | `_search_mixin.py`, `_user_entity_mixin.py`, `crud_queries.py` — regex `^[a-zA-Z_][a-zA-Z0-9_]*$`, max 64 chars |

```python
from core.utils.validation_helpers import validate_relationship_type, validate_field_name

# Infrastructure validates before interpolation — callers don't need to
# _build_direction_pattern() rejects unsafe relationship types with Result.fail()
# crud_queries validators raise ValueError for unsafe labels/fields
```

**Validators:** `core/utils/validation_helpers.py` (relationship types, field names), `crud_queries.py` (`_validate_label`, `_validate_identifier`).

**See:** SKUEL013 in `/docs/patterns/linter_rules.md` for the `RelationshipName` enum that makes most interpolation type-safe at the call site.

### Ownership Verification (404 Not 403)

User-owned entities return "not found" when accessed by non-owners. This prevents attackers
from enumerating valid entity UIDs.

```python
from adapters.inbound.route_factories import verify_entity_ownership

# API routes: use verify_entity_ownership helper
ownership_error = await verify_entity_ownership(service, uid, user_uid, "domain")
if ownership_error:
    return ownership_error  # Returns NotFound Result (404)

# UI routes: use require_owned_entity helper
from adapters.inbound.route_factories import require_owned_entity
entity, error = await require_owned_entity(service, uid, user_uid, "Entity")
if error:
    return error  # Returns Response(404)
```

### boundary_handler Error Stripping

`@boundary_handler()` catches service-layer errors and converts them to safe HTTP responses.
Internal error details (stack traces, Cypher queries, Neo4j internals) are never exposed.

### Session Configuration

- `SESSION_SECRET_KEY` env var — required in production, auto-generated in development
- Session IDs hashed with SHA-256 before storage
- Cookies: `HttpOnly=True`, `SameSite=strict`, `Secure=True` in production
- Session data stored in Neo4j (graph-native, no separate session store)

### Path Traversal Protection

`VaultConfig` restricts file access to:
- Explicitly allowed subdirectories (`allowed_subdirs`)
- Explicitly allowed file extensions (`.md`, `.yaml`, `.yml`, `.json`, `.csv`)
- Path validation enabled by default (`validate_paths=True`, `restrict_access=True`)
- Ingestion data directory configured via `INGESTION_PATH` env var (default: `data/vault` relative to CWD)

---

## Route Security Checklist

When adding a new route, verify:

1. **Authentication** — `user_uid = require_authenticated_user(request)` for standard routes, OR role decorator (`@require_admin`/`@require_teacher`) for protected routes — never both (the decorator already authenticates; use `current_user.uid` instead)
2. **Authorization** — `@require_admin(get_service)` if admin-only; `@require_teacher(get_service)` if teacher-only
3. **Ownership** — For USER_OWNED entities, verify `entity.user_uid == user_uid` (return 404 if not)
4. **Error boundary** — `@boundary_handler()` wrapping the route handler
5. **No PII in logs** — Never log user passwords, tokens, or session IDs
6. **Input validation** — Pydantic models for POST bodies, helper functions for query params
7. **Decorator order** — `@rt > @require_admin > @boundary_handler > async def`

---

## Code Review Security Checks

| Check | Rule | Details |
|-------|------|---------|
| No raw string role/scope/status comparisons | — | Use `UserRole` enum (not `== "admin"`), `ExerciseScope` enum (not `== "assigned"`), `EntityStatus` enum (not `== "completed"`) |
| No raw Cypher formatting | SKUEL001 | All queries parameterized |
| Use RelationshipName enum | SKUEL013 | No hardcoded relationship strings; infrastructure validates before interpolation |
| No `hasattr()` | SKUEL011 | Use Protocol/isinstance/getattr |
| No lambdas | SKUEL012 | Use named functions (prevents injection via closable scope) |
| No `print()` in production | SKUEL015 | Use `logger.*()` — print can leak to stdout |
| No `eval()`/`exec()` | — | Never execute dynamic code |
| No hardcoded secrets | — | All secrets via env vars or credential store |
| No APOC in domain services | SKUEL001 | APOC scoped to `apoc.meta.*` only |

---

## Deferred Security Items

The following are tracked in `/docs/roadmap/security-hardening-deferred.md`:

1. Dependency version pinning (Langchain)
2. Rate limiting and CAPTCHA on sign-up
3. Pre-commit hooks for secret scanning
4. Session rotation on privilege change
5. CI CVE scanning
6. CAPTCHA (only if automated abuse occurs)
7. HTTP security headers middleware (CSP, HSTS, X-Frame-Options, etc.)

Network security monitoring is tracked in `/docs/roadmap/network-security-monitoring.md`.

---

## References

- `/docs/patterns/AUTH_PATTERNS.md` — authentication and authorization implementation
- `/docs/security/ROUTE_AUTH_REQUIREMENTS.md` — per-route auth requirements
- `/docs/patterns/OWNERSHIP_VERIFICATION.md` — ownership verification patterns
- `/docs/roadmap/security-hardening-deferred.md` — deferred security hardening items
- `/docs/roadmap/network-security-monitoring.md` — network monitoring roadmap
- `/docs/patterns/ERROR_HANDLING.md` — boundary_handler and error stripping
