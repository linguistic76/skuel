# Security Hardening — Deferred Items

**Context**: These items were identified during the security review committed in `14c622c`
(2026-03-04) and intentionally deferred. They are real, valuable improvements — not rejected,
just not urgent before public deployment.

**See**: `/home/mike/.claude/plans/snazzy-gliding-shore.md` — the original review that produced
the implemented fixes (Phases 1–3) and surfaced these deferrals.

---

## 1. Dependency Version Pinning (Langchain)

**Why deferred**: Requires careful testing across the embedding and AI service layers. Current
wildcard `*` pinning has not caused breakage; the risk is low until we approach production.

**The problem**: `pyproject.toml` uses `langchain-*` with unpinned versions. A breaking
`langchain-core` or `langchain-openai` release could silently degrade embedding generation,
vector search, or AI feedback — failures that are hard to detect without a full regression suite.

**What to do**:

1. Run `poetry show --tree | grep langchain` to capture current resolved versions.
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

**Why deferred**: SKUEL is not publicly deployed yet. Rate limiting adds operational complexity
(Redis dependency, bypass edge cases) that has zero user impact in the current single-developer
phase.

**The problem**: `/api/auth/register` is currently unthrottled. An attacker can:
- Enumerate valid emails via response timing differences (partially mitigated by generic
  error messages in Phase 3, but timing side-channels remain)
- Flood the registration endpoint to exhaust Neo4j write capacity
- Create large numbers of throwaway accounts

**What to do**:

### A. Rate limiting on auth endpoints

Redis is already pre-wired (see `/docs/roadmap/future-services.md`). Once Redis is enabled,
add `slowapi` (or equivalent) to throttle:

```python
# Suggested limits
POST /api/auth/register  →  5 requests / 10 minutes per IP
POST /api/auth/login     →  10 requests / 5 minutes per IP
POST /api/auth/reset-password  →  3 requests / hour per IP
```

Apply limits at the FastHTML route level using a decorator pattern consistent with
`@require_admin` / `@boundary_handler` ordering conventions (SKUEL012: no lambdas).

### B. CAPTCHA on sign-up (optional, higher friction)

Consider hCaptcha (privacy-preserving) or Cloudflare Turnstile. CAPTCHA makes sense only
if bot-driven sign-up becomes a real problem — don't add it preemptively.

**Prerequisites**:
- Redis enabled (rate limiting store)
- Public deployment with a domain name
- `SKUEL_ENVIRONMENT=production` enforced at startup

**Enable when**: Going to public production. Rate limiting is the higher priority; CAPTCHA only
if automated abuse actually occurs.

---

## 3. Pre-commit Hooks for Secret Scanning

**Why deferred**: The current `.gitignore` covers the obvious secrets (`.env` files, Neo4j logs).
Pre-commit hooks add developer workflow friction with marginal benefit while only one developer
is active.

**The problem**: Hardcoded secrets can accidentally reach the git history. A developer under
time pressure might inline a key to debug something, forget to remove it, and commit. `git
history` is permanent — rotating the key is not enough; the commit remains.

**What to do**:

1. Install `pre-commit` and `detect-secrets`:
   ```bash
   poetry add --group dev pre-commit detect-secrets
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

**Why deferred**: No CI pipeline exists yet. Adding security scanning to a non-existent
pipeline is not actionable.

**The problem**: Python dependencies accumulate CVEs over time. Without automated scanning,
vulnerabilities in transitive dependencies go undetected until a developer happens to run
`pip audit` manually.

**What to do**:

When a CI pipeline (GitHub Actions, GitLab CI, etc.) is created, add these jobs:

### A. Dependency CVE scan (fast, runs on every PR)

```yaml
# .github/workflows/security.yml
- name: Audit Python dependencies
  run: poetry run pip-audit --requirement <(poetry export -f requirements.txt)
```

`pip-audit` queries the OSV database (Google's open-source vulnerability database) and fails
if any dependency has a known CVE. Add `pip-audit` to dev dependencies:
```bash
poetry add --group dev pip-audit
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
poetry run cyclonedx-py poetry > sbom.json
```

**Enable when**: First CI pipeline is created. The dependency audit job is the highest priority
— it's fast, cheap, and catches the most impactful class of vulnerabilities.

---

## Priority Order

When production deployment approaches, implement in this order:

| # | Item | Trigger |
|---|------|---------|
| 1 | **Dependency pinning** | Before any langchain upgrade; before production |
| 2 | **CI CVE scanning** | When CI pipeline is created |
| 3 | **Rate limiting** | When `SKUEL_ENVIRONMENT=production` is first set |
| 4 | **Pre-commit secret scanning** | When second developer joins |
| 5 | **Session rotation** | When multi-device sessions are tracked |
| 6 | **CAPTCHA** | Only if automated sign-up abuse occurs |

---

**Related**:
- `/docs/roadmap/future-services.md` — Redis, monitoring, and other deferred infrastructure
- `docs/patterns/AUTH_PATTERNS.md` — current auth implementation
- `adapters/inbound/auth/session.py` — session management (Phases 1–2 already hardened)
- `core/auth/graph_auth.py` — sign-up logic (Phase 3 generic errors already applied)
