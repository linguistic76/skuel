---
title: Security Hardening — Deferred Items
updated: 2026-07-24
category: roadmap
tags: [roadmap, security, hardening]
---
# Security Hardening — Deferred Items

**Context**: These items were identified during the security review committed in `14c622c`
(2026-03-04) and intentionally deferred. They are real, valuable improvements — not rejected,
just not urgent before public deployment.

**Status sweep 2026-07-24** (public-launch hardening, PR #794): item 7 (security headers) is
**done**; items 2, 3, and 5 are partially overtaken by shipped work — each carries a dated
status note below. Item 1 remains deferred as written; CAPTCHA (row 6 of the priority
table) is the still-open remainder of item 2. Later the same day, PR #797 shipped item 5's
dependency CVE audit (the `pip_audit` CI job) — its parts B/C remain open — and item 4
(session rotation) shipped as session revocation on privilege change plus per-request
graph-session enforcement.

**See**: `/home/mike/.claude/plans/snazzy-gliding-shore.md` — the original review that produced
the implemented fixes (Phases 1–3) and surfaced these deferrals.

---

## 1. Dependency Version Pinning (Langchain)

> **Status 2026-07-24 — partially overtaken by ADR-067.** The "wildcard `*`" claim below is
> stale: `pyproject.toml` now carries `>=` floors tracking the locked latest, `uv.lock` pins
> exact resolutions (and `Dockerfile.production` builds with `uv sync --frozen`), and Renovate
> opens update PRs gated by CI. What remains of this item is the *judgment call* — whether
> `langchain-*` deserves a deliberate cap like `neo4j` / `deepgram-sdk` (the two documented
> intentional pins) rather than riding the latest-stable default. See ADR-067 for the policy.

**Why deferred**: Requires careful testing across the embedding and AI service layers. Current
wildcard `*` pinning has not caused breakage; the risk is low until we approach production.

**The problem**: `pyproject.toml` uses `langchain-*` with unpinned versions. A breaking
`langchain-core` or `langchain-openai` release could silently degrade embedding generation,
vector search, or AI feedback — failures that are hard to detect without a full regression suite.

**What to do**:

1. Run `uv pip show --tree | grep langchain` to capture current resolved versions.
2. Pin each `langchain-*` package to the currently-resolved version:
   ```toml
   langchain-core = "^0.3.x"
   langchain-openai = "^0.2.x"
   langchain-community = "^0.3.x"
   ```
   Use `^` (compatible release) rather than `==` (exact) so patch-level security fixes apply
   automatically.
3. Run the full test suite. Pay attention to:
   - `tests/unit/test_embeddings*.py`
   - `tests/integration/test_*_intelligence*.py`
   - Any test that calls `BaseAIService` subclasses
4. Commit as a standalone dependency PR with the resolved versions documented in the commit message.

**Enable when**: Preparing for production deployment, or after any langchain upgrade breaks CI.

---

## 2. Rate Limiting and CAPTCHA on Sign-Up

> **Status 2026-07-24 — rate limiting SHIPPED, by a different mechanism than prescribed
> below; CAPTCHA still deferred.** The slowapi/Redis prescription was superseded by the
> in-memory `/adapters/inbound/rate_limit.py` (`@rate_limited` / `@rate_limited_ip`
> decorators — no Redis anywhere in the repo; the "pre-wired Redis" this item referenced
> was a dead knob, deleted in PR #793). What runs today: `/register/submit` has CSRF +
> `@rate_limited_ip(bucket="register", per_ip=5, window_s=300)`; login has 3-layer
> brute-force protection (`/core/auth/graph_auth.py`); password reset is throttled.
> On top of the throttles, PR #794 added the `SIGNUP_INVITE_CODE` gate (constant-time
> check before any account is created; resolves through `get_credential()`) — the real
> control on throwaway-account growth. Remaining from this item: CAPTCHA only, on its
> original trigger below.

**CAPTCHA (the still-deferred part)**: hCaptcha (privacy-preserving) or Cloudflare
Turnstile. CAPTCHA makes sense only if bot-driven sign-up becomes a real problem — don't
add it preemptively, and revisit only if the invite gate is removed or abuse is observed.
Email verification sits in the same bucket (see the fast-follow list in the droplet
deployment plan).

---

## 3. Pre-commit Hooks for Secret Scanning

> **Status 2026-07-24 — largely shipped, home-grown.** `scripts/git-hooks/pre-commit` (installed
> via `/scripts/install_git_hooks.sh`) blocks staged `.env*` files (`.env.*.example` templates
> allowed) and scans added lines for high-confidence credential patterns
> (`SKUEL_ALLOW_SECRETS=1` to bypass). The detect-secrets/baseline approach below remains an
> option if the home-grown patterns prove too narrow; the CI-side history scan (trufflehog/
> gitleaks) is still open — see item 5.

**Why deferred**: The current `.gitignore` covers the obvious secrets (`.env` files, Neo4j logs).
Pre-commit hooks add developer workflow friction with marginal benefit while only one developer
is active.

**The problem**: Hardcoded secrets can accidentally reach the git history. A developer under
time pressure might inline a key to debug something, forget to remove it, and commit. `git
history` is permanent — rotating the key is not enough; the commit remains.

**What to do**:

1. Install `pre-commit` and `detect-secrets`:
   ```bash
   uv add --group dev pre-commit detect-secrets
   ```

2. Create `.pre-commit-config.yaml` at the repo root:
   ```yaml
   repos:
     - repo: https://github.com/Yelp/detect-secrets
       rev: v1.5.0
       hooks:
         - id: detect-secrets
           args: ['--baseline', '.secrets.baseline']
           exclude: |
             (?x)^(
               tests/fixtures/.*|
               docs/.*|
               \.secrets\.baseline
             )$
   ```

3. Generate the baseline (marks known false positives as allowed):
   ```bash
   detect-secrets scan > .secrets.baseline
   # Review .secrets.baseline — remove any real secrets that appear
   git add .secrets.baseline .pre-commit-config.yaml
   ```

4. Install the hooks:
   ```bash
   pre-commit install
   ```

**Additional consideration**: Add `trufflehog` or `gitleaks` to the CI pipeline when CI exists
(see item 5 below). Pre-commit hooks catch issues locally; CI scanning catches anything that
slips through.

**Enable when**: Second developer joins, or before any public repository exposure.

---

## 4. Session Rotation on Privilege Change — ✅ DONE (2026-07-24)

Sharpened by the droplet prep: admin role promotion IS the AI-access grant
(REGISTERED→MEMBER), so stale sessions became a launch concern rather than a theoretical one.

**What shipped** (variant A below, plus the enforcement that makes it real):

1. **Revocation on privilege change** — both `UserService.update_role` and
   `UserService.deactivate_user` commit the privilege change AND the session sweep in ONE
   Cypher transaction (`update_role_and_revoke_sessions` /
   `deactivate_user_and_revoke_sessions` on `SessionBackend`, behind the
   `SessionInvalidationOperations` protocol). Atomicity is load-bearing — three rounds of
   Codex review killed every two-step ordering: update-then-revoke isn't retryable (the
   retry sees the change applied and skips the sweep), revoke-then-update leaves a sign-in
   window whose fresh session dodges the completed sweep, and split deactivation could
   leave an account looking deactivated while its sessions kept validating. The User-node
   write lock serializes against `create_session`, so a concurrent sign-in lands either
   before the transaction (swept) or after it (a legitimate post-change re-login). A no-op
   role set doesn't log anyone out, and an ADMIN→ADMIN self-update can't self-logout.
   Password change/reset keep using the plain `invalidate_all_user_sessions` sweep.
2. **Per-request enforcement** — the finding that reshaped the item: *nothing* validated the
   graph session per request, so server-side invalidation (including the existing password
   change/reset flows) never actually logged out a live cookie for its whole 30-day max_age.
   `AuthContextMiddleware` (`/adapters/inbound/auth/context_middleware.py`) now validates
   `session_token` against the `:Session` node once per authenticated request — ONE indexed
   round trip (`SessionBackend.validate_session_token`: is_valid + expiry + user_is_active,
   with the 5-min-batched last-active touch folded into the same statement) — and clears
   the cookie session
   when the graph says revoked/expired — forced re-login on the very next request. Anonymous
   requests, static/health/PWA paths, and `/logout` skip validation (logout must stay
   possible during a graph outage — its whole job is clearing the cookie); a validation
   *error* (Neo4j unreachable) denies with 503 WITHOUT clearing the cookie. Additionally,
   `create_session` atomically refuses inactive users, closing the deactivate-vs-concurrent
   sign-in race. The now-redundant, never-called `get_current_user_validated()` helper was
   deleted (One Path Forward).
3. **Index fix** — the Session lookup index targeted the nonexistent `session_token` property
   (raw tokens never persist; nodes store `token_hash`), so every token lookup was a label
   scan. Now indexed on `token_hash`; the stale index is dropped at schema sync.

**Deliberately not done** — variant B (session *regeneration* via `role_changed_at`
comparison): revocation + per-request enforcement covers the threat; regeneration only adds
session-fixation protection for the re-login flow, which `sign_in` already handles by minting
a fresh token. Revisit only if role management is exposed to non-admin users.

---

## 5. CI CVE Scanning — ✅ dependency audit DONE (PR #797, 2026-07-24); history scan + SBOM open

> **Status 2026-07-24 — part A shipped (PR #797).** Parts B (secret scanning in history)
> and C (SBOM) below remain open, on their original triggers.

**The problem**: Python dependencies accumulate CVEs over time. Without automated scanning,
vulnerabilities in transitive dependencies go undetected until a developer happens to run
`pip audit` manually.

### A. Dependency CVE scan — ✅ DONE (PR #797)

Shipped as the `pip_audit` job in `.github/workflows/ci.yml`, required (via the CI Gate) on
every Python-file PR — `pyproject.toml` / `uv.lock` changes are what move the resolution, and
running on ordinary Python PRs also catches CVEs published since the last dependency change.
A dedicated `audit` path filter additionally triggers the job when the audit tooling itself
(`/scripts/audit_dependencies.sh`, `/.pip-audit-ignore`) changes, so the check can never be
edited without being exercised.
One audit path for CI and local (`./dev audit-deps`): `/scripts/audit_dependencies.sh` exports
the full locked resolution (`uv export`, all groups, with hashes) and runs
`pip-audit --strict --disable-pip` against the OSV database — the lock is audited, not the
live venv, and no resolver runs.

Accepted findings live in `/.pip-audit-ignore`, one vulnerability ID per line, **each with a
documented reason and an unblock condition**. Currently: the dev-only `mcp-neo4j-cypher`
cluster (fastmcp / mcp / diskcache — upstream 0.6.0 is the latest release and pins the
vulnerable versions; the dev group never reaches the production image, which syncs
`--no-dev`). Delete entries the moment an upgrade path exists.

The first run also surfaced 15 fixable packages; 13 were upgraded in the lock in the same PR
(aiohttp, cryptography, jupyter-server, jupyterlab, langsmith, mistune, pillow,
pydantic-settings, pymdown-extensions, pypdf, starlette, tornado + notebook as a follower)
and setuptools fell out of the resolution entirely.

### B. Secret scanning in history (runs on PR targeting main)

```yaml
- name: Scan for secrets
  uses: trufflesecurity/trufflehog@main
  with:
    path: ./
    base: ${{ github.event.repository.default_branch }}
    head: HEAD
    extra_args: --only-verified
```

`--only-verified` reduces false positives by only flagging secrets that can be verified
against their issuing service (e.g., an AWS key that actually authenticates).

### C. SBOM generation (optional, runs on main branch merge)

Generate a Software Bill of Materials for supply chain visibility:
```bash
uv run cyclonedx-py environment > sbom.json
```

**Enable when** (B and C): B before any public repository exposure (same trigger as item 3's
CI-side remainder — trufflehog/gitleaks would replace the home-grown pre-commit patterns'
blind spot for history); C when supply-chain visibility is asked for (compliance, or a second
deployment target).

---

## 7. HTTP Security Headers Middleware — ✅ DONE (PR #794, 2026-07-24)

Shipped as `SecurityHeadersMiddleware` in `/adapters/inbound/middleware.py`, registered in
`main.py` as the **outermost ASGI wrapper** (not `add_middleware` — that sits inside
Starlette's ServerErrorMiddleware and would leave unhandled-exception 500s unstamped). Every
response carries:

| Header | Shipped value |
|--------|---------------|
| `X-Frame-Options` | `DENY` |
| `X-Content-Type-Options` | `nosniff` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `microphone=(self), camera=(), geolocation=()` (journals records audio) |
| `Content-Security-Policy-Report-Only` | self-hosted assets; `unsafe-eval` (Alpine `x-data`) + `unsafe-inline` (FastHTML inline scripts/styles); `frame-ancestors 'none'` |

Two pieces deliberately remain:

1. **CSP promotion to enforcing** — the policy ships **Report-Only**; promote once the browser
   console stays clean in real use. The original tightening path still applies for removing the
   `unsafe-*` directives (assets are already self-hosted and Tailwind pre-built — the remaining
   steps are the Alpine CSP build and nonce-based inline scripts).
2. **HSTS** — deliberately absent from the middleware; TLS termination (and therefore HSTS) is
   Caddy's job at the edge. Not yet in the `Caddyfile` either: hardcoding it would poison the
   browser HSTS cache for `SKUEL_DOMAIN=localhost` rehearsal. Add it scoped to the real domain
   at launch.

---

## Priority Order

Status as of 2026-07-24 (public-launch hardening shipped in PR #794):

| # | Item | Status / trigger |
|---|------|------------------|
| 1 | **Dependency pinning** | Open — before any langchain upgrade (see the item's status note) |
| 2 | **CI CVE scanning** | ✅ Done (PR #797) — `pip_audit` CI job + `./dev audit-deps`; history scan (B) + SBOM (C) remain on their own triggers |
| 3 | **Rate limiting** | ✅ Done — `/adapters/inbound/rate_limit.py` + invite gate |
| 4 | **Pre-commit secret scanning** | ✅ Done — `scripts/git-hooks/pre-commit` |
| 5 | **Session rotation** | ✅ Done (2026-07-24) — revocation on role change/deactivation + per-request graph-session enforcement |
| 6 | **CAPTCHA** | Open — only if automated sign-up abuse occurs despite the invite gate |
| 7 | **Security headers** | ✅ Done (PR #794) — CSP promotion + Caddy HSTS remain |

---

**Related**:
- `/docs/roadmap/deferred-work.md` — intelligence features, decision points, and other deferred items
- `/docs/patterns/AUTH_PATTERNS.md` — current auth implementation
- `/adapters/inbound/auth/session.py` — session management (Phases 1–2 already hardened)
- `/core/auth/graph_auth.py` — sign-up logic (Phase 3 generic errors already applied)
