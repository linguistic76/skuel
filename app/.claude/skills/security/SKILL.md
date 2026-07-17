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
| **CSRF protection** | `SameSite=Strict` (primary) + double-submit `csrf_token` cookie verified by `@csrf_protected` | Active |
| **Path traversal** | `_validate_ingestion_path` (traversal guard on every ingest route) + `is_relative_to()` containment checks in the vault descriptor/reconciler; see the two rows below for the ingestion allowlist and sync wall | Active |
| **Ingestion path allowlist** | Default-deny: `SKUEL_INGESTION_ALLOWED_PATHS` > `INGESTION_PATH` > fail closed (admin role gates ownership, not filesystem reach) | Active |
| **Vault sync privacy wall** | One predicate (`is_ingestible_path`) at every ingestion door (`collect_files`, `ingest_file`, `reconcile_deletions`; reconciler + `/api/ingest/*` inherit): rejects **symlinks** (target may be external); applies a **`je_*` staging floor** scoped to the personal vault; enforces a **fail-closed allowlist** (`SyncAllowlist`, code-defined `_DEFAULT_SYNC_SUBDIRS` — `periodic_notes/`/`personal_notes/`/`activity_notes/`/`knowledge/`; **not** env-configurable — `SKUEL_VAULT_SYNC_ALLOWED_DIRS` was removed as it let a stale exported var shadow `.env`; dirs must be strictly under the root). Retroactive: narrowing the wall purges now-walled rows via reconciliation (full→smart auto-upgrade when governed). Content vault (outside the root) unaffected | Active (default-on) |
| **Login rate limiting** | **Two-axis:** per-account (5 fails/15min, by email) + per-IP (20 fails/15min, by `AuthEvent.ip_address`); IP check ordered **before** email lookup to block enumeration | Active |
| **Password length pre-validation** | `validate_password` rejects > `MAX_PASSWORD_BYTES = 72` (UTF-8 byte count, not chars) before bcrypt — clean field error, not generic broad-except | Active |
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
| **Relationship types** | `validate_identifier()` + `validate_relationship_type()` | All 5 query builder modules via `_helpers.py`; `_build_direction_pattern()` in `_relationship_crud_mixin.py` (choke point for mixin Cypher); `traverse()` and `find_path()` in `_traversal_mixin.py` |
| **Neo4j labels** | `validate_label()` | All 5 query builder modules via `_helpers.py` — checks against `NeoLabel` enum allowlist |
| **Field/property names** | `validate_identifier()` + `validate_field_name()` | All 5 query builder modules via `_helpers.py` — regex `^[a-zA-Z_][a-zA-Z0-9_]*$`; `_search_mixin.py`, `_user_entity_mixin.py` via `validate_field_name()` (max 64 chars); **`ModelQueryBuilder.filter(**kwargs)` silently drops unsafe keys** (mirrors the `order_by` policy — operator suffixes like `__gte`/`__contains` still validate since the regex allows underscores throughout) |
| **Comparison operators** | `validate_cypher_operator()` | `core/utils/validation_helpers.py` — case-sensitive allowlist `{=, <>, !=, <, >, <=, >=, CONTAINS, STARTS WITH, ENDS WITH, IN}`. Centrally gated in `query_optimizer._validate_request` so all six plan-builders inherit the check from one point. |
| **Sort directions** | `validate_sort_direction()` | `core/utils/validation_helpers.py` — `{ASC, DESC}` (case-insensitive). Same central gate in `query_optimizer._validate_request` (also validates the sort *property* via `validate_field_name`). |

```python
# Shared guards — used by crud_queries, domain_queries, relationship_queries,
# semantic_queries, intelligence_queries
from adapters.persistence.neo4j.query.cypher._helpers import validate_label, validate_identifier

# Infrastructure validates before interpolation — callers don't need to
# _build_direction_pattern() rejects unsafe relationship types with Result.fail()
# Query builder validators raise ValueError for unsafe labels/fields/relationship types
```

**Validators:** `_helpers.py` (`validate_label`, `validate_identifier` — shared by all query builders), `core/utils/validation_helpers.py` (`validate_relationship_type`, `validate_field_name`, `validate_cypher_operator`, `validate_sort_direction`), `_backend_helpers.py` (`_validate_rel_name`, `_ALLOWED_ORDER_BY`).

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

### Credential Handling (SKUEL019)

Every secret read goes through `get_credential()` — the funnel that dispatches to whichever backend is configured. Raw `os.getenv("FOO_API_KEY")` is a SKUEL019 violation.

```python
from core.config.credential_store import get_credential

api_key = get_credential("OPENAI_API_KEY", fallback_to_env=True)
if not api_key:
    raise RuntimeError("OPENAI_API_KEY missing — set via `uv run python -m core.config`")
```

| Layer | Mechanism |
|---|---|
| **Storage** | OS keychain (`SKUEL_CREDENTIAL_BACKEND=keyring`, recommended) → libsecret / macOS Keychain / Windows Credential Locker. Or Fernet-encrypted JSON at `~/.skuel/credentials.enc` keyed by `SKUEL_MASTER_KEY`. |
| **Funnel** | `get_credential(K, fallback_to_env=True)` in `core/config/credential_store.py`. Dispatches via `SKUEL_CREDENTIAL_BACKEND`. Falls back to env, auto-migrates env values into the backend on first read. |
| **Boot validation** | Tier-gated services fail-fast when their credential is missing (commit `fed4287f`) — no silent half-on state. |
| **Lint enforcement** | SKUEL019 — ERROR for catalog credentials, WARNING for credential-shape names not yet in the catalog. Catalog mirrored from `CredentialSetup.CREDENTIALS` and pinned by a drift test. |

**Catalog as the single source of truth:** when adding a new credential, register it in `core/config/credential_setup.py::CredentialSetup.CREDENTIALS`. The drift test (`test_lint_skuel.py::TestCredentialCatalogDrift`) will tell you to mirror it in `SkuelLinter.CREDENTIAL_CATALOG` so SKUEL019 catches future bypasses with ERROR severity.

**Exempt files** (raw env reads ARE the implementation): `credential_store.py`, `credential_setup.py`, `migrate_secrets_to_homedir.py`, `migrate_secrets_to_keychain.py`, test files.

**See:** `docs/roadmap/secrets-out-of-worktree.md` — full storage architecture; `docs/patterns/linter_rules.md` § SKUEL019.

### Session Configuration

- `SESSION_SECRET_KEY` read via `get_credential()` from the active backend — required in production, auto-generated in development.
- Session IDs hashed with SHA-256 before storage
- Cookies: `HttpOnly=True`, `SameSite=strict`, `Secure=True` in production
- Session data stored in Neo4j (graph-native, no separate session store)

### CSRF Protection (Double-Submit Token + SameSite)

Primary defense is `SameSite=Strict` on the session cookie — the browser refuses to send it on cross-site POSTs, so forged requests have no identity. Double-submit is the second line so the app stays safe if `SameSite` is ever loosened (cross-subdomain SSO, OAuth embeds) or if an XSS on the same origin forges writes.

`CSRFMiddleware` mints a non-HttpOnly `csrf_token` cookie on first GET and exposes it via a ContextVar (`core/utils/csrf_token_context.py` — the render surface, written by the middleware, read by form builders). Three mirror paths feed the submitted token back to the server:

1. **Server-render** — `csrf_hidden_input()` (`ui/patterns/csrf.py`) emits a hidden form field from the ContextVar
2. **HTMX header** — `static/js/skuel.js` attaches `X-CSRF-Token` via `htmx:configRequest`
3. **Native form sync** — capture-phase `submit` handler in `skuel.js` refreshes the hidden input from the cookie before serialization (covers SW-cached HTML, extension-mutated DOM)

State-changing routes wear `@csrf_protected`. The decorator reads header first then form field, constant-time compares against the cookie, returns 403 on mismatch. `SKUEL_CSRF_ENFORCE=false` is a revert lever; production runs enforcement on.

```python
from adapters.inbound.csrf import csrf_protected
from ui.patterns.csrf import csrf_hidden_input

@rt("/tasks/create", methods=["POST"])
@csrf_protected
async def create_task(request): ...

# Hand-built forms need the hidden field (FormGenerator adds it automatically)
Form(csrf_hidden_input(), ..., method="POST", action="/login/submit")
```

**CSRF cookie is deliberately `HttpOnly=False`** — JS must read it to echo back via HTMX header. XSS can already post anything as the user; protecting the CSRF token from JS would add no defense against a threat that's already past the perimeter. See `/docs/security/COOKIES_AND_CSRF.md` § 4 for the threat model.

**See:** `/docs/security/COOKIES_AND_CSRF.md` — teaching-focused deep dive on both cookies, the double-submit pattern, and the forward security posture.

### Path Traversal Protection

File access is constrained by two live mechanisms (the old advisory
`VaultConfig.validate_paths`/`restrict_access`/`allowed_subdirs`/`allowed_extensions`
fields were removed — they had no readers):
- **Ingestion routes** — `_validate_ingestion_path` resolves the request path and
  rejects anything not contained under a configured root (see the allowlist section
  below). The vault root itself is `INGESTION_PATH` (default: `data/vault`).
- **Vault descriptor / reconciler** — `is_relative_to()` containment checks resolve
  both sides so `..` segments cannot escape a vault root, backing the fail-closed
  `SyncAllowlist` (see the sync privacy wall section below).

### Ingestion Endpoint Allowlist (default-deny)

`adapters/inbound/ingestion_api.py::_validate_ingestion_path` rejects every request path that does not resolve under at least one configured root. Precedence chain via `_resolve_allowed_ingestion_roots()`:

1. `SKUEL_INGESTION_ALLOWED_PATHS` (colon-separated explicit override — multi-vault / staging setups)
2. `INGESTION_PATH` (the single configured vault root — the documented default)
3. **Neither set → empty list → reject every path** (fail closed)

Admin + CSRF still apply on top — the role gate authorizes *ownership of the action*, not *filesystem reach*. A compromised admin session still can't ingest from `/etc` or `/root`.

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
| No hardcoded secrets | — | All secret reads go through `get_credential(KEY, fallback_to_env=True)` from `core/config/credential_store` — never raw `os.getenv("FOO_API_KEY")`. Backend (keychain / Fernet / direnv-loaded env) is selected by `SKUEL_CREDENTIAL_BACKEND`. Tier-gated services fail-fast at boot when a required credential is missing (commit `fed4287f`). |
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

- `/docs/security/COOKIES_AND_CSRF.md` — teaching-focused deep dive on session + CSRF cookies, double-submit pattern, forward posture
- `/docs/patterns/AUTH_PATTERNS.md` — authentication and authorization implementation
- `/docs/security/ROUTE_AUTH_REQUIREMENTS.md` — per-route auth requirements
- `/docs/patterns/OWNERSHIP_VERIFICATION.md` — ownership verification patterns
- `/docs/roadmap/security-hardening-deferred.md` — deferred security hardening items
- `/docs/roadmap/network-security-monitoring.md` — network monitoring roadmap
- `/docs/patterns/ERROR_HANDLING.md` — boundary_handler and error stripping
