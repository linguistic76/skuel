---
updated: 2026-08-21
---

# Programmatic-Client Auth — Token Path for CSRF-Exempt Endpoints

**Context**: The route-security sweep (PR #1, commits `c78e3861` → `8ab04eb8`,
2026-05-20) brought every mutation handler under a CSRF + auth invariant, gated
by `scripts/audit_route_security.py` (and the `./dev quality` runner + the
`tests/unit/test_route_security_audit.py` guard). Three handlers originally could
not be `@csrf_protected` without breaking their real, non-browser clients, so they
sat in the script's `CSRF_EXEMPT` table with a reason. This file is the plan to
retire such exemptions properly.

**Status**: Deferred — not urgent. *(Re-verified 2026-08-21: `CSRF_EXEMPT` is down
to **one** entry — `device_routes.py:enroll_device_api`, kept exempt **by design**
(sessionless one-time pairing code, ADR-075); GraphQL was folded 2026-07-25 and
batch-transcribe is now `@csrf_protected`. So the bearer-token scheme below is now
motivated by future programmatic clients, not by outstanding exemptions — and the
original "empty the table" acceptance is superseded: the pairing entry is
intentionally permanent.)*

---

## The problem

SKUEL's CSRF defense is **session-cookie-oriented**: `@csrf_protected` verifies a
token (cookie + matching header/form field) that the `htmx:configRequest` hook
injects into browser requests. Programmatic clients — CLI scripts, service-to-
service callers, Jupyter notebooks — authenticate with the same session
mechanism but **cannot produce that token**, so applying `@csrf_protected` to an
endpoint they call would break them.

Today we resolve the conflict per-handler, by exemption. That works but has two
smells:

1. **The exemption list can quietly become the norm.** Each new programmatic
   endpoint is tempted to add itself to `CSRF_EXEMPT` rather than authenticate
   correctly. The list should shrink to zero, not grow.
2. **It conflates "no CSRF token" with "no CSRF risk."** Starlette parses a JSON
   body regardless of `Content-Type`, so a CSRF-exempt admin JSON endpoint is
   still theoretically reachable by a forged cross-site request riding an admin's
   live browser session. The exemption is justified only because there is *no
   browser path* to these endpoints — a property that is asserted, not enforced.

## The destination

A **separate authentication scheme for non-browser clients** that is
CSRF-exempt *by construction*, while browser sessions always require CSRF:

- **Bearer token / API key** (e.g. `Authorization: Bearer <token>`), validated by
  an auth dependency that establishes the caller's identity + role **without** a
  session cookie.
- CSRF verification is **skipped when (and only when) the request authenticated
  via a bearer token**, never when it authenticated via a session cookie. (This
  is the standard pattern: cookie-auth ⇒ CSRF required; token-auth ⇒ CSRF n/a,
  because there is no ambient credential a cross-site request can ride.)
- Tokens are admin-issued, scoped (which endpoints/roles), and revocable —
  graph-native, consistent with SKUEL's "all auth data in Neo4j" principle.

With that in place, the three exempt endpoints authenticate via token and can
**drop their `CSRF_EXEMPT` entries** — the invariant becomes "every mutation is
either CSRF-protected (cookie clients) or bearer-authenticated (token clients),"
with no per-handler holes.

## Exemptions this would clear

From `scripts/audit_route_security.py` `CSRF_EXEMPT` (run `./dev audit-routes
--list-exempt`):

| Endpoint | Current client | After |
|---|---|---|
| `device_routes.py:enroll_device_api` (`POST /api/devices/enroll`) | vault-agent enrollment (sessionless one-time pairing code, ADR-075) | already token-like; kept exempt by design |

(The former `graphql_routes.py:graphql_handler` entry was removed when the
GraphQL adapter was folded, 2026-07-25.)

`batch_transcription_api.py:batch_transcribe` was removed from `CSRF_EXEMPT`
when its admin UI (`/admin/batch-transcribe`) made it browser-reachable: the
handler is now `@csrf_protected`, the browser UI sends `X-CSRF-Token`, and the
CLI (`scripts/batch_transcribe.py`) obtains a `csrf_token` transparently (a GET
mints one via `CSRFMiddleware`) and echoes it — so a session cookie alone works,
no manual token handling. The bearer-token migration below still applies as the
end-state; it would let token-authenticated calls skip CSRF entirely.

**Related:** the `advanced_routes` admin endpoints (`/jupyter/save`,
`/jupyter/sync-to-obsidian`, `/performance/optimize`) are now `@csrf_protected`
(closing the admin-browser-CSRF vector). They have no programmatic caller today;
when a Jupyter-notebook / ops client is wired up, it should authenticate via a
bearer token (this scheme) rather than carrying a CSRF token.

## What to do

1. Add a token model (graph-native): `(User)-[:HAS_API_TOKEN]->(ApiToken {hash,
   scopes, created_at, expires_at, revoked})` or similar; admin-issued.
2. Add an auth dependency that resolves identity from `Authorization: Bearer`
   first, falling back to the session cookie. Surface *how* the request
   authenticated (token vs. cookie).
3. Make `csrf_protected` (or the middleware) **skip enforcement for token-
   authenticated requests** and require it for cookie-authenticated ones.
4. *(Updated 2026-08-21 — the original three exemptions are already resolved: GraphQL
   folded, batch-transcribe now `@csrf_protected`.)* When a new programmatic client is
   wired (Jupyter/ops/CLI), give it a bearer token from day one and keep its endpoint
   `@csrf_protected` — the token path from step 3 means it never needs a `CSRF_EXEMPT`
   entry.
5. **Leave the device-pairing exemption alone** (`device_routes.py:enroll_device_api` —
   sessionless one-time pairing code, ADR-075; permanent by design; bearer tokens don't
   apply to a not-yet-enrolled device). `./dev audit-routes` must stay green with
   `CSRF_EXEMPT` holding exactly that one entry —
   `test_csrf_exempt_holds_exactly_the_by_design_entries` in
   `test_route_security_audit.py` asserts the exact table contents.

## Acceptance

*(Updated 2026-08-21 — the original "empty table" criterion is unreachable by design.)*

- `./dev audit-routes --list-exempt` shows `CSRF_EXEMPT` reduced to the by-design
  device-pairing entry only (already true today) — and any endpoint migrated to
  bearer-token auth leaves the table.
- Migrated endpoints reject tokenless **cookie** requests (CSRF enforced) and
  accept valid **bearer-token** requests.
- CLI/notebook clients work via token; no session-cookie path to them.

## See

- `scripts/audit_route_security.py` — the gate + the `CSRF_EXEMPT` table this retires.
- `adapters/inbound/csrf.py` — current session-cookie CSRF implementation.
- `docs/roadmap/security-hardening-deferred.md` — sibling deferred security items.
- `docs/patterns/AUTH_PATTERNS.md` — current (session-based) auth.
