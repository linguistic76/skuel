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
status note below. Items 1 and 4 remain deferred as written; CAPTCHA (row 6 of the priority
table) is the still-open remainder of item 2.

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

## 4. Session Rotation on Privilege Change

**Why deferred**: Privilege changes (role upgrades/downgrades) are rare admin operations.
Implementing correct multi-device session rotation requires tracking which sessions exist across
devices — a capability SKUEL doesn't yet need.

**The problem**: If a user's role is elevated (e.g., REGISTERED → TEACHER), their existing
session cookie still carries the old role until it naturally expires or the user logs out and
back in. An attacker who compromised an old session could retain stale elevated access if role
was later downgraded.

**What to do**:

### A. Session invalidation on role change

The minimal safe implementation: invalidate ALL of a user's active sessions when their role
changes. The user is forced to log in again with their new role.

```python
# In user management service, after updating role:
await session_backend.invalidate_all_sessions_for_user(user_uid)
```

This requires `invalidate_all_sessions_for_user(user_uid: UserUID)` on `SessionBackend`:
```cypher
MATCH (u:User {uid: $user_uid})-[:HAS_SESSION]->(s:Session)
WHERE s.expires_at > datetime()
SET s.expires_at = datetime()   -- expire immediately
```

### B. Session regeneration on privilege escalation (stronger)

Instead of invalidating, issue a fresh session token on login after a role change. This
prevents session fixation attacks. Requires:
- Tracking `role_version` or `role_changed_at` on the User node
- Comparing it to the session's `created_at` on each request
- Triggering re-authentication if `role_changed_at > session.created_at`

**Prerequisites**:
- Multi-device session tracking (know which sessions belong to which user)
- `HAS_SESSION` relationship already exists; verify it's indexed on `user_uid`

**Enable when**: Multiple concurrent sessions per user become a use case, or before exposing
role management to non-admin users.

---

## 5. CI CVE Scanning

> **Status 2026-07-24 — now actionable, still not done.** The original blocker is gone: CI
> exists (`.github/workflows/ci.yml` — tests, lint, MyPy, docs jobs). `pip-audit` has not been
> added; it is on the post-launch fast-follow list. The instructions below are current.

**Why deferred**: (historical) No CI pipeline existed when this was written. Adding security
scanning to a non-existent pipeline was not actionable.

**The problem**: Python dependencies accumulate CVEs over time. Without automated scanning,
vulnerabilities in transitive dependencies go undetected until a developer happens to run
`pip audit` manually.

**What to do**:

When a CI pipeline (GitHub Actions, GitLab CI, etc.) is created, add these jobs:

### A. Dependency CVE scan (fast, runs on every PR)

```yaml
# .github/workflows/security.yml
- name: Audit Python dependencies
  run: uv run pip-audit --requirement <(uv export -f requirements.txt)
```

`pip-audit` queries the OSV database (Google's open-source vulnerability database) and fails
if any dependency has a known CVE. Add `pip-audit` to dev dependencies:
```bash
uv add --group dev pip-audit
```

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

**Enable when**: First CI pipeline is created. The dependency audit job is the highest priority
— it's fast, cheap, and catches the most impactful class of vulnerabilities.

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
| 2 | **CI CVE scanning** | Open, now actionable — add `pip-audit` to `ci.yml` (fast-follow) |
| 3 | **Rate limiting** | ✅ Done — `/adapters/inbound/rate_limit.py` + invite gate |
| 4 | **Pre-commit secret scanning** | ✅ Done — `scripts/git-hooks/pre-commit` |
| 5 | **Session rotation** | Open — more relevant now that admin role promotion is the AI-access grant |
| 6 | **CAPTCHA** | Open — only if automated sign-up abuse occurs despite the invite gate |
| 7 | **Security headers** | ✅ Done (PR #794) — CSP promotion + Caddy HSTS remain |

---

**Related**:
- `/docs/roadmap/deferred-work.md` — intelligence features, decision points, and other deferred items
- `/docs/patterns/AUTH_PATTERNS.md` — current auth implementation
- `/adapters/inbound/auth/session.py` — session management (Phases 1–2 already hardened)
- `/core/auth/graph_auth.py` — sign-up logic (Phase 3 generic errors already applied)
