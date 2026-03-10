# Security Skill

Expert guide for SKUEL's security posture — existing protections, route security checklist, and code review checks.

---

## Security Posture Summary

SKUEL has a strong security foundation built into the architecture:

| Area | Implementation | Status |
|------|---------------|--------|
| **Query injection** | All Cypher queries use parameterized `$variables` — no string formatting | Enforced (SKUEL001) |
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

### Ownership Verification (404 Not 403)

User-owned entities return "not found" when accessed by non-owners. This prevents attackers
from enumerating valid entity UIDs.

```python
# Pattern: check ownership, return 404 if not owner
entity = await service.get(uid)
if entity.is_error or entity.value.user_uid != user_uid:
    return JSONResponse({"error": "Not found"}, status_code=404)
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

---

## Route Security Checklist

When adding a new route, verify:

1. **Authentication** — `user_uid = require_authenticated_user(request)` at the top
2. **Authorization** — `@require_admin(get_service)` if admin-only; role checks if teacher-only
3. **Ownership** — For USER_OWNED entities, verify `entity.user_uid == user_uid` (return 404 if not)
4. **Error boundary** — `@boundary_handler()` wrapping the route handler
5. **No PII in logs** — Never log user passwords, tokens, or session IDs
6. **Input validation** — Pydantic models for POST bodies, helper functions for query params
7. **Decorator order** — `@rt > @require_admin > @boundary_handler > async def`

---

## Code Review Security Checks

| Check | Rule | Details |
|-------|------|---------|
| No raw Cypher formatting | SKUEL001 | All queries parameterized |
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
