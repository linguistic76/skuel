---
title: Cookies and CSRF in SKUEL
updated: '2026-04-20'
category: security
audience: learners
related_skills: [security]
related_docs:
  - /docs/patterns/AUTH_PATTERNS.md
  - /docs/security/ROUTE_AUTH_REQUIREMENTS.md
  - /docs/roadmap/security-hardening-deferred.md
---

# Cookies and CSRF in SKUEL

**Audience:** someone new to web security who wants to understand how sessions and CSRF protection actually work in this codebase, why we made the choices we made, and what's on the roadmap.

**TL;DR:** SKUEL sets two cookies. Most of the real security comes free from the browser (`SameSite=Strict`) and Starlette's session middleware. On top of that we add a small, explicit double-submit token so the app stays safe when — not if — we ever need to loosen `SameSite` for SSO or cross-subdomain use.

The design goal is this: *the smallest possible custom surface on top of primitives the browser and standard library already guarantee.* Every item in the roadmap at the end of this doc is either a configuration knob or a library drop-in. We don't write our own crypto. We don't parse our own cookies. The custom code is glue.

---

## 1 · The two cookies SKUEL sets

### `skuel_session` — who you are

A signed, opaque session cookie managed by Starlette's `SessionMiddleware`. Contains `user_uid` after login. Starlette signs it with `SESSION_SECRET_KEY` so the server can detect tampering; if someone edits the cookie in devtools, the signature no longer validates and the session is rejected.

| Attribute | Value | Why |
|---|---|---|
| `HttpOnly` | `True` | JavaScript (including any malicious injected JS) cannot read or exfiltrate this cookie |
| `SameSite` | `strict` | Browsers refuse to attach it to cross-site requests — the primary CSRF defense |
| `Secure` | `True` in production | Never sent over plain HTTP; TLS only |
| `max_age` | 30 days | Forced rotation on logout, password reset, or admin invalidation |

**Source:** [`adapters/inbound/auth/session.py:718-724`](../../adapters/inbound/auth/session.py)

### `csrf_token` — the double-submit token

32 bytes of URL-safe randomness from Python's `secrets.token_urlsafe()`. Minted on the first response to a new browser, reused thereafter. Unlike the session cookie, this one is **deliberately readable by JavaScript** — see §4 for why.

| Attribute | Value | Why |
|---|---|---|
| `HttpOnly` | `False` | Your page's JS needs to read it to echo it back as a form field or header |
| `SameSite` | `strict` | Same reason as session — first-party only |
| `Secure` | `True` in production | TLS only |
| `max_age` | 30 days | Matches session lifetime |

**Source:** [`adapters/inbound/csrf.py:207-215`](../../adapters/inbound/csrf.py)

---

## 2 · What CSRF actually is

CSRF — Cross-Site Request Forgery — is the attack where a malicious site tricks your browser into submitting an authenticated request to SKUEL on your behalf. The concrete scenario:

1. You are logged into `skuel.app` — the browser is holding your `skuel_session` cookie.
2. In another tab, you visit `evil.com`.
3. `evil.com` has a hidden form that auto-POSTs to `skuel.app/tasks/delete-all`.
4. The browser — obliviously — attaches your session cookie because the cookie is for `skuel.app` and the request is going to `skuel.app`.
5. Your tasks are gone.

The defense is **to make the server refuse requests that didn't originate from your own pages**, even when a valid session cookie is present.

---

## 3 · SKUEL's layered defense

Each layer is cheap. Together they cover the failure modes of any individual layer.

### Layer A — `SameSite=Strict` (the browser does the work)

The browser itself refuses to attach the session cookie to any request that didn't originate from `skuel.app`. `evil.com`'s auto-POST arrives at the server with *no cookies* and is treated as an anonymous request. This is the main line of defense and it **comes free** — we configure one value and the browser enforces it.

**Why we don't stop here.** `SameSite=Strict` is fragile against legitimate product needs. Any future feature that involves cross-site traffic — SSO, OAuth callbacks, embedding SKUEL in a cross-subdomain context — will force loosening to `Lax` or even `None`. We want to design the system so that loosening `SameSite` doesn't also unlock CSRF.

### Layer B — Double-submit token (the server's belt)

Independently of `SameSite`, SKUEL requires every **mutating** request (POST, PUT, DELETE) to contain the same value in *two places simultaneously*:

1. **The `csrf_token` cookie** — set by the server; the browser echoes it back on any request.
2. **The request body or `X-CSRF-Token` header** — attached by the page's own code.

The server reads both and compares with `hmac.compare_digest()` (constant-time so attackers can't learn the value by timing responses). A mismatch returns `403 CSRF_INVALID`.

**The key insight:** a cross-site page at `evil.com` *cannot read* your `csrf_token` cookie (same-origin policy in the browser). It can *cause* the browser to send the cookie with a forged request — that's what SameSite normally blocks — but it cannot *forge the matching body field or header*. Both sides of the double-submit have to match, or the request is rejected.

A route opts in with a decorator:

```python
from adapters.inbound.csrf import csrf_protected

@rt("/tasks/delete")
@csrf_protected
async def delete_task(request: Request):
    ...
```

GET, HEAD, OPTIONS are always allowed through — they shouldn't change state. (If a GET route changes state, that's a separate bug worth fixing regardless of CSRF.)

### Layer C — Three ways the cookie value gets back to the server

The cookie is the single source of truth. Three mirror paths carry that value into the outgoing request, so handlers always see it to compare against:

| Path | When it runs | How |
|---|---|---|
| **Server-rendered hidden input** | At page-render time | `csrf_hidden_input()` (`ui/patterns/csrf.py`) reads a `ContextVar` the middleware set for this request (`core/utils/csrf_token_context.py`) and emits `<input type="hidden" name="csrf_token" value="...">` as a child of the `<form>` |
| **HTMX header hook** | Every HTMX mutating request | `static/js/skuel.js` listens for `htmx:configRequest` and attaches `X-CSRF-Token` from `document.cookie` |
| **Native form sync** | Every native `<form method="POST">` submit | Same file, capture-phase `submit` listener re-injects and refreshes the hidden input from the cookie right before the browser serialises the form |

The three paths are redundant **on purpose**:
- If JS is disabled, the server-rendered input still works for native forms.
- If an extension, a stale cached HTML page, or a now-unregistered service worker ever strips the server-rendered input, the JS sync restores it synchronously at submit time.
- If a request is issued via HTMX, the header carries the token without needing a form at all.

All three paths end at the same comparison: cookie value `==` submitted value.

---

## 4 · Why `HttpOnly=False` on the CSRF cookie looks wrong but isn't

The instinct: "making a security cookie readable by JavaScript is bad."

The reality: the `csrf_token` cookie has to be JS-readable because that's the entire mechanic — JS reads it and echoes it back. And the threat that `HttpOnly` actually defends against (XSS stealing cookies) doesn't apply here:

- If an attacker has XSS on `skuel.app`, they're already running code in your origin. They can issue authenticated fetches directly, cookie attached automatically. Reading the CSRF token buys them nothing extra.
- The real defence against XSS is **not having XSS** — parameterised queries, Pydantic at the edges, `boundary_handler` stripping internal errors, `SKUEL001`/`SKUEL013` linter rules, no `eval`.
- The `skuel_session` cookie *is* `HttpOnly=True`. XSS cannot steal *that* one, which is the cookie that actually authorises requests.

So the design is: session cookie hidden from JS, CSRF cookie exposed to JS by necessity. Each cookie's `HttpOnly` setting reflects what that specific cookie is for.

---

## 5 · Two subtle edges worth understanding

These aren't bugs; they're places where the design is less obvious than it looks. Both were hardened in commit `04949179` after being discovered during real debugging.

### 5.1 · Mint exemption for static assets

When a browser first visits SKUEL, it opens the HTML **and in parallel** fires subresource requests for CSS, JS, the PWA manifest, the service worker, and the favicon. If `CSRFMiddleware` minted a fresh cookie on each of those parallel requests, the last one to complete would overwrite the cookie that the HTML's hidden input was seeded from. The form would then carry an old token, and the next POST would fail with `token_mismatch`.

The fix: the middleware never mints on `/static/*`, `/manifest.json`, `/service-worker.js`, `/favicon.ico`, `/robots.txt`. Only HTML requests mint.

**Source:** [`adapters/inbound/csrf.py:78-92, 195-199`](../../adapters/inbound/csrf.py)

### 5.2 · `Cache-Control: no-store` on /login

Browsers may cache the login page. If the cookie later rotates (user logs out and comes back, or their cookies get cleared), a cached HTML page with a stale hidden input would mismatch the fresh cookie. `/login` now sets `Cache-Control: no-store` so this class of staleness can't happen, regardless of JS state.

**Source:** [`adapters/inbound/auth_ui.py:232-240`](../../adapters/inbound/auth_ui.py)

---

## 6 · What we *don't* write ourselves

The philosophy, concretely.

| Capability | Who provides it | What SKUEL touches |
|---|---|---|
| Signed session cookies | Starlette `SessionMiddleware` | One call in bootstrap; secret from env |
| Cookie serialisation | Starlette + browser | Nothing |
| `SameSite`, `HttpOnly`, `Secure` flag enforcement | Browsers (Firefox, Chrome, Safari) | Configuration only |
| Cryptographic randomness | Python `secrets` | `secrets.token_urlsafe(32)` |
| Constant-time string compare | Python `hmac` | `hmac.compare_digest()` |
| TLS termination | Reverse proxy (Caddy/Nginx) at deploy time | Configuration only |
| Password hashing | `bcrypt` library | One call |
| Parameterised queries (injection protection) | Neo4j driver | Every query uses `$variables`; `SKUEL001` linter proves it |
| Label/field name allowlisting | Pure functions in `_helpers.py` | ~30 lines of regex validators |

Everything SKUEL-specific in the CSRF story is roughly **300 lines**, mostly orchestration, split along the hexagonal seam: enforcement in `adapters/inbound/csrf.py` (the middleware, the decorator, the mint exemption), the request-scoped token context in `core/utils/csrf_token_context.py`, and the hidden-input renderer in `ui/patterns/csrf.py`. No hand-rolled crypto. No custom cookie parsing. No custom hashing.

This is the posture the project commits to keeping.

---

## 7 · When you'll touch this code

| Situation | What to do |
|---|---|
| Adding a new mutating route | Wrap the handler in `@csrf_protected`. For hand-built forms, drop `csrf_hidden_input()` as the first child of `Form()`. Forms rendered through `FormGenerator` include it automatically. |
| Adding a new static-asset path | Nothing — `/static/*` is already mint-exempt by prefix. |
| Adding a non-form JSON POST from JS | Either use HTMX (the hook handles it) or attach `'X-CSRF-Token': window.SKUEL.csrf()` to the request `headers`. `window.SKUEL.csrf()` (in `static/js/skuel.js`) is the single helper that reads the cookie — never hand-roll the `document.cookie` regex. |
| Adding a new auth page like /login | Return it with `Cache-Control: no-store` (see §5.2). |
| Loosening `SameSite` on any cookie | Audit. This is the scenario the double-submit exists for. Verify all three mirror paths from §3 still fire in whatever flow you're enabling. |
| Writing anything cryptographic | Don't. Use `secrets`, `hmac`, `bcrypt`, and whatever the framework provides. |

---

## 8 · The forward posture

The through-line: **rely on open, well-maintained primitives; add the smallest custom piece that closes the specific gap.**

### In place today (open-source, zero custom code)

- Starlette `SessionMiddleware` for session signing
- Browser `SameSite=Strict` as the primary CSRF defence
- `secrets.token_urlsafe` for the CSRF token
- `hmac.compare_digest` for constant-time matching
- Neo4j parameter binding for query safety
- `bcrypt` for password hashing
- `SKUEL001`/`SKUEL013` linter rules as compile-time proof nothing hand-formats Cypher

### Minimally custom (~300 lines total)

- `CSRFMiddleware` — mints the cookie, owns the mint-exemption
- `@csrf_protected` — gates state-changing routes
- `csrf_hidden_input()` (`ui/patterns/csrf.py`) — renders the hidden field from the request `ContextVar` (`core/utils/csrf_token_context.py`)
- `@boundary_handler` — strips internal errors at HTTP boundaries
- Ownership helpers — return 404 (not 403) to prevent UID enumeration

### On the roadmap, in priority order

Full detail in [`docs/roadmap/security-hardening-deferred.md`](../roadmap/security-hardening-deferred.md). Each item is **deferred, not rejected** — the current state is safe for pre-public use. Each item has a concrete trigger condition.

| # | Item | Trigger |
|---|---|---|
| 1 | Pin `langchain-*` dependency versions | Before any langchain upgrade; before production |
| 2 | CI CVE scanning (`pip-audit` against OSV) | When a CI pipeline exists |
| 3 | ~~Rate limiting on auth endpoints~~ **Done (in-process):** `rate_limited_ip` on all four auth POST handlers (login 10/60s, register/forgot-password/reset-password 5/300s). **Remaining:** Redis-backed cluster-wide limiting for multi-worker deployments | Multi-worker deployment |
| 4 | Pre-commit `detect-secrets` | When a second developer joins |
| 5 | Session rotation on role change | Before exposing role management to non-admins |
| 6 | HTTP security headers middleware — `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, HSTS | Before public deployment |
| 7 | Content Security Policy (nonce-based) | After (6); requires the tightening path — remove `'unsafe-eval'` by switching to Alpine.js CSP build, self-host remaining CDN dependencies, move inline scripts to external files. The vendoring done in commit `04949179` already retired the CDN origins. |
| 8 | CAPTCHA on sign-up | Only if automated abuse actually occurs |

Notice how many of these are *configuration* or *library drop-ins*, not new code. That is the point.

---

## Related

- [`adapters/inbound/csrf.py`](../../adapters/inbound/csrf.py) — the enforcement half (middleware, decorator, mint/verify), including the design doc at the top
- [`core/utils/csrf_token_context.py`](../../core/utils/csrf_token_context.py) — the request-scoped token ContextVar the middleware writes and form builders read
- [`ui/patterns/csrf.py`](../../ui/patterns/csrf.py) — `csrf_hidden_input()`, the render half
- [`adapters/inbound/auth/session.py`](../../adapters/inbound/auth/session.py) — session cookie configuration
- [`static/js/skuel.js`](../../static/js/skuel.js) — the `window.SKUEL.csrf()` cookie-read helper plus the two JS mirror paths (HTMX `htmx:configRequest` hook and the capture-phase native-form `submit` sync)
- [`.claude/skills/security/SKILL.md`](../../.claude/skills/security/SKILL.md) — broader security patterns: ownership verification, error stripping, Cypher injection guards
- [`docs/security/ROUTE_AUTH_REQUIREMENTS.md`](./ROUTE_AUTH_REQUIREMENTS.md) — per-route auth requirements
- [`docs/patterns/AUTH_PATTERNS.md`](../patterns/AUTH_PATTERNS.md) — authentication patterns (cookie-based + graph-native)
- [`docs/roadmap/security-hardening-deferred.md`](../roadmap/security-hardening-deferred.md) — priority-ordered future work
