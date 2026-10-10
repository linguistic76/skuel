# Security Skill

Expert guide for SKUEL's security posture — existing protections, route security checklist, and code review checks.

---

## Security Posture Summary

SKUEL has a strong security foundation built into the architecture:

| Area | Implementation | Status |
|------|---------------|--------|
| **Query injection** | Parameterized `$variables` + allowlist validation for interpolated labels/relationship types/fields | Enforced (CYP003, SKUEL021, SKUEL013) |
| **Authentication** | Graph-native auth in Neo4j; `AuthContextMiddleware` validates the session against its `:Session` node on every request; `require_authenticated_user()` on user-owned routes, `get_current_user()` (optional) on SHARED read pages | Active |
| **Authorization** | Role-based (REGISTERED/MEMBER/TEACHER/ADMIN), `@require_admin` / `@require_teacher` / `@require_role` decorators | Active |
| **Ownership verification** | Returns 404 (not 403) for entities the user doesn't own — no information leakage; reads pass one of two chokepoints (ADR-085) | Active |
| **Error stripping** | `@boundary_handler` strips internal details from HTTP responses | Active |
| **Session security** | SHA-256 hashing, `SameSite=strict`, `HttpOnly`, `Secure` in production | Active |
| **CSRF protection** | `SameSite=Strict` (primary) + double-submit `csrf_token` cookie verified by `@csrf_protected` | Active |
| **Path traversal** | No HTTP route takes a path to ingest — the reconciler walks the vault roots fixed at composition (`VaultRegistry`); `is_relative_to()` containment checks in the vault descriptor/reconciler back the sync wall below | Active |
| **Vault sync privacy wall** | One predicate (`is_ingestible_path`) at every ingestion chokepoint (`collect_files`, `ingest_file`, `reconcile_deletions` — the reconciler and any direct call inherit): rejects **symlinks** (target may be external); applies a **`je_*` staging floor** scoped to the personal vault; enforces a **fail-closed allowlist** (`SyncAllowlist`, code-defined `_DEFAULT_SYNC_SUBDIRS` — `periodic_notes/`/`personal_notes/`/`activity_notes/`/`knowledge/`; **not** env-configurable — `SKUEL_VAULT_SYNC_ALLOWED_DIRS` was removed as it let a stale exported var shadow `.env`; dirs must be strictly under the root). Retroactive: narrowing the wall purges now-walled rows via reconciliation (full→smart auto-upgrade when governed). Content vault (outside the root) unaffected | Active (default-on) |
| **Login rate limiting** | **HTTP layer:** `rate_limited_ip` (`adapters/inbound/rate_limit.py`) on the auth POSTs — login 10/60s, register / forgot-password / reset-password 5/300s, 429 + `Retry-After`. **Graph layer, two-axis:** per-account (5 fails/15min, by email) + per-IP (20 fails/15min, by `AuthEvent.ip_address`); IP check ordered **before** email lookup to block enumeration | Active |
| **Password length pre-validation** | `validate_password` rejects > `MAX_PASSWORD_BYTES = 72` (UTF-8 byte count, not chars) before bcrypt — clean field error, not generic broad-except | Active |
| **Docker production** | Non-root user, minimal image | Active |

---

## Existing Security Patterns

### Parameterized Cypher (CYP003)

All Neo4j queries MUST use parameter binding for values. Never format a value into Cypher —
`scripts/cypher_linter.py` CYP003 (ERROR) flags a value-position interpolation. Cypher itself
lives only below the boundary, in `adapters/persistence/neo4j/` (SKUEL021).

```python
# CORRECT
await tx.run("MATCH (n:Entity {uid: $uid}) RETURN n", uid=entity_uid)

# VIOLATION — a value formatted into the query
await tx.run(f"MATCH (n:Entity {{uid: '{entity_uid}'}}) RETURN n")  # CYP003
```

### Cypher Interpolation Validation (Defense-in-Depth)

Neo4j cannot parameterize labels, property names, or relationship types — these must be interpolated into Cypher strings. Three guarantees are in use at the infrastructure boundary, and they are **not** interchangeable — a consolidation that picks one for every site weakens the sites using a stronger one:

| What | Validator | Location |
|------|-----------|----------|
| **Relationship types** | `validate_identifier()` + `validate_relationship_type()` | The query builder modules via `_helpers.py`; `_build_direction_pattern()` in `_relationship_crud_mixin.py` (choke point for mixin Cypher); `traverse()` in `_traversal_mixin.py` |
| **Neo4j labels** | `validate_label()` | The query builder modules via `_helpers.py` — checks against `NeoLabel` enum allowlist |
| **Field/property names — syntactic** | `validate_identifier()` (raises) / `validate_field_name()` (returns bool, ≤64 chars) | One regex `^[a-zA-Z_][a-zA-Z0-9_]*$`, two contracts. The query builder modules **and** `neo4j_schema_manager`'s DDL share `validate_identifier` from `_helpers.py`; `_search_mixin.py`, `_user_entity_mixin.py`, `unified_query_builder.py` use `validate_field_name()`. **`ModelQueryBuilder.filter(**kwargs)` silently drops unsafe keys** (mirrors the `order_by` policy — operator suffixes like `__gte`/`__contains` still validate since the regex allows underscores throughout) |
| **Field/property names — model-derived** | membership in `fields(entity_class)` | Every `crud_queries` builder. A **sort key** warns and drops on a miss; an interpolated **property name in a pattern** raises, because dropping it would change which rows match rather than only their order |
| **Field/property names — enum-typed** | the parameter's type (`ActivitySortKey`) | `find_connected_activities` (`_knowledge_context_mixin.py`) — the layer's one caller-chosen `ORDER BY` property. Membership is structural and mypy-checked, so no runtime check sits beside the interpolation |
| **Comparison operators** | *structural dispatch — no validator* | No builder interpolates a caller's operator. `build_search_query` (`crud_queries.py`) runs an if/elif chain that emits a literal and warns-and-skips anything unknown; `batch_cypher_builder.py` looks up `_FILTER_OP_MAP` and raises on a miss. An unknown operator cannot reach Cypher at all — stronger than checking one and then interpolating it. |
| **Sort directions** | *derived literals — no validator* | Every `ORDER BY` direction resolves to `"ASC"`/`"DESC"` before interpolation: from a bool (`"DESC" if order_desc else "ASC"`), from the developer-authored `RelationshipSpec.order_direction` (`relationship_registry.py`), or from a literal at the call site. The sort *property* beside it is a separate question — see the three field-name rows above, and the caveat below them. |

```python
# Shared guards — used by crud_queries, domain_queries, semantic_queries,
# and neo4j_schema_manager's DDL (relationship_queries interpolates nothing:
# its batch builders pass relationship types as a $relationship_types parameter)
from adapters.persistence.neo4j.query.cypher._helpers import validate_label, validate_identifier

# These raise ValueError for an unsafe label / field / relationship type.
# _build_direction_pattern() rejects an unsafe relationship type with Result.fail().
# Writing a NEW interpolation means picking a guarantee — the guards above are
# available, not automatic.
```

**Validators:** `_helpers.py` (`validate_label`, `validate_identifier` — shared by all five query builders *and* the schema manager's DDL), `core/utils/validation_helpers.py` (`validate_relationship_type`, `validate_field_name`), `_backend_helpers.py` (`_validate_rel_name`).

**Not every interpolation reaches one.** A handful of backend methods interpolate a property name their caller supplies with no check — `_relationship_ordered_mixin`'s `order_by_property` / `sequence_property` / `get_hierarchical_children_deep`'s whole `match_pattern`, and `PsBackend.list_steps_raw`'s `order_field`. Each caller passes a literal, a registry constant, or sits behind a PLANNED surface; `/docs/roadmap/field-name-guarding-in-cypher.md` records the ruling and what would change it. Assume a guard exists only where you can name it.

**No HTTP route publishes a sort key.** `ORDER BY` on a property the response never renders is a measured disclosure oracle — permitted by Neo4j, observable in the row order, and enumerable through `SKIP`/`LIMIT`. It cannot cross a `WHERE` clause, so it reaches un-rendered properties of already-authorized rows rather than another user's. Adding a `?sort=` parameter means choosing a guarantee, not just forwarding a string.

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
    return error  # bare Response: 404 not-yours/missing, 503 for a backend fault
```

A UI refusal the learner *sees* goes through `refuse(error, render, entity_name)` (same
module): NOT_FOUND renders "<Entity> not found" at **404**, anything else "Could not
load …" at the error's own status, with the `X-SKUEL-Refusal: rendered` header that lets
HTMX swap a 4xx/5xx body (`static/js/skuel.js`). A fragment is not exempt — an ownership
failure answered 200 looks like a successful read to clients, caches and monitoring.

**The two-chokepoint read contract (ADR-085).** A read on behalf of a user passes exactly
one of: the visibility clause (`build_search_visibility_clause()` — every SearchRouter
strategy, and by-UID reads through `BaseService.get_visible_to_user(uid, user_uid)` under
the domain's `read_visibility`), or route-mediated `verify_ownership`. Bare `get()` is
internal mechanics only. **Never add a third mechanism** — a `get()` followed by an inline
`entity.user_uid != user_uid` compare is the ad-hoc check ADR-085 §4 forbids even when its
logic is right. The two sanctioned inline compares (owner-or-teacher in `exercises_api.py`,
student-or-owner in `revised_exercises_api.py`) express rules no service verifier can.

**Teacher reads (ADR-088).** A teacher reads a student's entry only through the entry's own
feedback request — `SUBMITTED_TO_GROUP` an active group the teacher `OWNS`. A `SHARES_WITH`
from the teacher is a share, never a review grant, and sharing a classroom with the author
is not enough (a student may be in several groups). Ask about the entity, never its author.

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
| **Storage** | OS keychain (`SKUEL_CREDENTIAL_BACKEND=keyring`, the default) → libsecret / macOS Keychain / Windows Credential Locker. Or `SKUEL_CREDENTIAL_BACKEND=env` (headless: droplet, CI) → the process environment, read-only. Any other value is refused at boot. |
| **Funnel** | `get_credential(K, fallback_to_env=True)` in `core/config/credential_store.py`. Dispatches via `SKUEL_CREDENTIAL_BACKEND`. Falls back to env, and auto-migrates an env value into a writable backend on first read — only for keys in `CREDENTIAL_CATALOG`, so connection config (`NEO4J_URI`, `NEO4J_USERNAME`) is never stored. |
| **Boot validation** | Tier-gated services fail-fast when their credential is missing (commit `fed4287f`) — no silent half-on state. |
| **Lint enforcement** | SKUEL019 — ERROR for catalog credentials, WARNING for credential-shape names not yet in the catalog. Catalog mirrored from `CREDENTIAL_CATALOG` and pinned by a drift test. |

**Catalog as the single source of truth:** when adding a new credential, register it in `core/config/credential_store.py::CREDENTIAL_CATALOG`. Two drift tests then tell you to mirror the name — `test_lint_skuel.py::TestCredentialCatalogDrift` into `SkuelLinter.CREDENTIAL_CATALOG` (so SKUEL019 catches bypasses at ERROR severity), and `test_secret_scan.py::TestCatalogDrift` into `scripts/git-hooks/credential-keys.txt` (so the commit-time scan looks for it).

**Exempt files** (raw env reads ARE the implementation): `credential_store.py`, `credential_setup.py`, `migrate_secrets_to_keychain.py`, test files.

**See:** `core/config/README.md` — the live credential setup; `docs/roadmap/done/secrets-out-of-worktree.md` — how credentials got out of the worktree; `docs/patterns/linter_rules.md` § SKUEL019.

### Secret-Bearing Fields Are Unprintable

A credential that reaches a model must not survive `repr()`. Two mechanisms, chosen by model kind:

| Model kind | Mechanism | Sites |
|---|---|---|
| Pydantic | `pydantic.SecretStr` — `repr` and `model_dump()` render `**********` | `RegistrationRequest` / `LoginRequest` / `ResetPasswordRequest` passwords, `confirm_password`, reset `token` |
| Dataclass | `field(repr=False)` | `Session.session_token`, `PasswordResetToken.token`, `User.password_hash`, `DatabaseConfig.neo4j_password`, `CacheConfig.redis_password`, `MessageQueueConfig.password` |

Wrap at the boundary, read at the point of use:

```python
# Route: wrap the raw form value immediately
reg = RegistrationRequest(password=SecretStr(safe_form_string(form_data.get("password"))), ...)
# Service call: unwrap only where the plaintext is needed
await graph_auth.sign_up(password=reg.password.get_secret_value(), ...)
```

⚠ `ValidationError.errors()[0]["input"]` holds the **raw submitted value** even for a `SecretStr` field — never log a `ValidationError` from an auth route whole. `_first_validation_error` reads only `type`/`msg`/`loc`.

⚠ `User.password_hash` is a bcrypt digest — offline-crackable, so it is a credential, not an opaque id.

Pinned by `tests/unit/models/test_secret_fields_unprintable.py`, which asserts the rendered `repr()` **and** the field declaration, so a field retyped back to `str` fails.

### Session Configuration

- `SESSION_SECRET_KEY` read via `get_credential()` from the active backend — required in production, auto-generated in development.
- Session tokens are 256-bit `secrets.token_urlsafe`; only the SHA-256 hash is stored
- Cookies: `HttpOnly=True`, `SameSite=strict`, `Secure=True` in production
- Session data stored in Neo4j (graph-native, no separate session store)
- **Validated once per request** — `AuthContextMiddleware` checks the token against its `:Session` node before any route runs: a revoked or expired session is cleared (forced re-login); a validation *error* (graph unreachable) answers 503 without clearing. Route helpers then read the cookie.
- **Revocation is atomic** — each revoking write commits its credential/privilege change AND the session sweep in one transaction on `SessionBackend` (`change_password_and_revoke_sessions`, `reset_password_and_revoke_sessions`, `update_role_and_revoke_sessions`, `deactivate_user_and_revoke_sessions`), so the target's very next request is refused.

### CSRF Protection (Double-Submit Token + SameSite)

Primary defense is `SameSite=Strict` on the session cookie — the browser refuses to send it on cross-site POSTs, so forged requests have no identity. Double-submit is the second line so the app stays safe if `SameSite` is ever loosened (cross-subdomain SSO, OAuth embeds) or if an XSS on the same origin forges writes.

`CSRFMiddleware` mints a non-HttpOnly `csrf_token` cookie on first GET and exposes it via a ContextVar (`core/utils/csrf_token_context.py` — the render surface, written by the middleware, read by form builders). Three mirror paths feed the submitted token back to the server:

1. **Server-render** — `csrf_hidden_input()` (`ui/patterns/csrf.py`) emits a hidden form field from the ContextVar
2. **HTMX header** — `static/js/skuel.js` attaches `X-CSRF-Token` via `htmx:configRequest`
3. **Native form sync** — capture-phase `submit` handler in `skuel.js` refreshes the hidden input from the cookie before serialization (covers SW-cached HTML, extension-mutated DOM)

State-changing routes wear `@csrf_protected`. The decorator reads header first then form field, constant-time compares against the cookie, returns 403 on mismatch. Verification is unconditional in every environment — there is no enforcement toggle. Route tests satisfy it by minting a real cookie+header pair via `tests/fixtures/csrf.py` (`attach_csrf`).

⚠ **Declare the mutation's unsafe method explicitly** — `methods=["POST"]`, or `["DELETE"]` / `["PATCH"]` where that is the route's contract (`transcription_api.py`, `hierarchy_route_factory.py`). `@csrf_protected` verifies every method except GET/HEAD/OPTIONS, and `@rt(path)` without `methods=` answers GET, HEAD *and* POST — so a mutation registered without it is reachable by a GET that the double-submit check never sees (`SameSite=Strict` is then the only line).

```python
from adapters.inbound.csrf import csrf_protected
from ui.patterns.csrf import csrf_hidden_input

@rt("/tasks/create", methods=["POST"])
@csrf_protected
async def task_create_submit(request: Request) -> FT | RedirectResponse: ...

# Hand-built forms need the hidden field (FormGenerator adds it automatically)
Form(csrf_hidden_input(), ..., method="POST", action="/login/submit")
```

**CSRF cookie is deliberately `HttpOnly=False`** — JS must read it to echo back via HTMX header. XSS can already post anything as the user; protecting the CSRF token from JS would add no defense against a threat that's already past the perimeter. See `/docs/security/COOKIES_AND_CSRF.md` § 4 for the threat model.

**See:** `/docs/security/COOKIES_AND_CSRF.md` — teaching-focused deep dive on both cookies, the double-submit pattern, and the forward security posture.

### Path Traversal Protection

File access is constrained by one live mechanism (the old advisory
`VaultConfig.validate_paths`/`restrict_access`/`allowed_subdirs`/`allowed_extensions`
fields were removed — they had no readers):
- **No request-supplied ingestion paths** — no HTTP route takes a path to ingest.
  The reconciler walks the vault roots fixed at composition (`VaultRegistry`: the
  content vault at `INGESTION_PATH`, the personal vault at `VAULT_ROOT`, member
  vaults under `SKUEL_USER_VAULTS_ROOT`), so an admin session — compromised or not —
  cannot point ingestion at `/etc` or `/root`.
- **Vault descriptor / reconciler** — `is_relative_to()` containment checks resolve
  both sides so `..` segments cannot escape a vault root, backing the fail-closed
  `SyncAllowlist` (see the sync privacy wall section below).

---

## Route Security Checklist

When adding a new route, verify:

1. **Authentication** — derive it from `ContentScope`: `user_uid = require_authenticated_user(request)` for user-owned routes; `get_current_user(request)` (returns `None` when anonymous) on SHARED read pages that only enrich for a signed-in user; OR a role decorator (`@require_admin`/`@require_teacher`) for protected routes — never a role decorator plus `require_authenticated_user` (SKUEL036; the decorator already authenticated — use `current_user.uid`)
2. **Authorization** — `@require_admin(get_user_service)` if admin-only; `@require_teacher(get_user_service)` if teacher-only. The handler's first parameter is `request` and the injected user is spelled exactly `current_user: Any = None` — the decorator refuses any other spelling at decoration, and hides the parameter from FastHTML so a caller cannot bind it
3. **Ownership** — For USER_OWNED entities, `verify_entity_ownership` (API) / `require_owned_entity` or `verify_ownership` + `refuse` (UI) — 404 if not the caller's. Never an inline `entity.user_uid == user_uid` compare (ADR-085 §4)
4. **Error boundary** — `@boundary_handler()` wrapping the route handler
5. **CSRF** — an explicit unsafe method (`methods=["POST"]` / `["DELETE"]` / `["PATCH"]`) plus `@csrf_protected` on every state change
6. **No PII in logs** — Never log user passwords, tokens, or session IDs. Secret-bearing model fields are `SecretStr` / `field(repr=False)` so a whole-object log line cannot disclose one (see Secret-Bearing Fields Are Unprintable) — but a `ValidationError` still carries the raw input.
7. **Input validation** — Pydantic models for POST bodies (`parse_body` / `parse_json_body` / `parse_form_body`), helper functions for query params
8. **Decorator order** — `@rt > @csrf_protected > @require_admin > @boundary_handler > async def` (`admin_api.py`)

---

## Code Review Security Checks

| Check | Rule | Details |
|-------|------|---------|
| No raw string role/scope/status comparisons | — | Use `UserRole` enum (not `== "admin"`), `ExerciseScope` enum (not `== "assigned"`), `EntityStatus` enum (not `== "completed"`) |
| No raw Cypher formatting | CYP003 | All values parameterized |
| No Cypher above the boundary | SKUEL021 | Cypher lives in `adapters/persistence/neo4j/` only |
| No auth call inside a role-gated handler | SKUEL036 | `@require_*` already authenticated — `UserUID(current_user.uid)` |
| No uid sniffing | SKUEL034 | Entity kind comes from label / `entity_type` / edge, never a substring of the uid |
| Use RelationshipName enum | SKUEL013 | No hardcoded relationship strings; infrastructure validates before interpolation |
| No `hasattr()` | SKUEL011 | Use Protocol/isinstance/getattr |
| No lambdas | SKUEL012 | Use named functions (prevents injection via closable scope) |
| No `print()` in production | SKUEL015 | Use `logger.*()` — print can leak to stdout |
| No `eval()`/`exec()` | — | Never execute dynamic code |
| No hardcoded secrets | — | All secret reads go through `get_credential(KEY, fallback_to_env=True)` from `core/config/credential_store` — never raw `os.getenv("FOO_API_KEY")`. Backend (OS keychain, or the read-only process environment when headless) is selected by `SKUEL_CREDENTIAL_BACKEND`. Tier-gated services fail-fast at boot when a required credential is missing (commit `fed4287f`). |
| No APOC in domain services | SKUEL001 | APOC scoped to `apoc.meta.*` only |

---

## Deferred Security Items

`/docs/roadmap/security-hardening-deferred.md` is the ledger. What is still open there:

- **CAPTCHA on sign-up** (item 6, only if automated abuse occurs) — sign-up rate limiting shipped as `rate_limited_ip`
- **CI-side history secret scan** (items 3 and 5) — the commit-time scan shipped (`scripts/git-hooks/pre-commit` + `credential-keys.txt`)
- **SBOM** (item 5) — the dependency CVE audit shipped as the `dep_audit` job (osv-scanner over both lockfiles)

Done: dependency pinning (closed by deleting the packages), session revocation on privilege change, the security-headers middleware, and the CSRF enforcement toggle's removal.

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
