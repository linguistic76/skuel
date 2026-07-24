---
title: Droplet Deployment Guide
updated: 2026-07-24
category: deployment
tags: [deployment, droplet, caddy, auradb, operations]
related_skills:
  - docker
  - neo4j-cypher-patterns
---
# Droplet Deployment Guide

**Last Updated:** 2026-07-24
**Scope:** Running skuel.app publicly from a DigitalOcean droplet (app + Caddy in Docker) against Neo4j AuraDB Free
**Filename note:** kept as `DO_MIGRATION_GUIDE.md` for link stability; the App Platform + Neo4j-droplet plan it used to describe was skipped (see [NEO4J_SETUP_MIGRATION_SUMMARY.md](./NEO4J_SETUP_MIGRATION_SUMMARY.md)).

---

## The One Path

```
┌──────────────────────────────────────────┐
│  DigitalOcean droplet                    │      ┌──────────────────────┐
│                                          │      │  Neo4j AuraDB Free   │
│  ┌───────────┐        ┌──────────────┐   │      │  (managed)           │
│  │  caddy    │──5001──│  skuel-app   │───┼──────│  neo4j+s://…         │
│  │  :80/:443 │        │  (loopback)  │   │      │  neo4j.io            │
│  └───────────┘        └──────────────┘   │      └──────────────────────┘
│  auto-TLS (Let's Encrypt)                │
└──────────────────────────────────────────┘
```

Two containers on one droplet, defined in `app/docker-compose.production.yml`:

- **`skuel-app`** — the FastHTML app built from `Dockerfile.production` (Python 3.14-slim, non-root user `skuel` pinned to UID/GID 10001, `APP_PORT=5001` baked into the image). Published on **loopback only** (`127.0.0.1:5001`) — Caddy fronts the world; the deploy health gate curls it directly.
- **`caddy`** — `caddy:2-alpine` terminating TLS on 80/443 (+443/udp for HTTP/3), auto-provisioning Let's Encrypt certificates for `SKUEL_DOMAIN`, redirecting `www.` → apex, and reverse-proxying to `skuel-app:5001`. Config in `app/Caddyfile`.

Neo4j is **not** on the droplet. Production talks to AuraDB Free over `neo4j+s://`; boot refuses plaintext URI schemes (`/core/config/validation.py` — `SKUEL_ENVIRONMENT=production` requires `neo4j+s | bolt+s | neo4j+ssc | bolt+ssc`). Startup tolerates a paused/waking Free instance via bounded connect retry (`connect_with_retry`, ADR-080 H0). Getting data INTO AuraDB is [AURADB_MIGRATION_GUIDE.md](./AURADB_MIGRATION_GUIDE.md).

Local development is untouched by all of this: `infrastructure/docker-compose.yml` Neo4j + `uv run python main.py` (or `app/docker-compose.yml` for the full local stack).

### Config layering on the droplet

| File | Contains | Managed how |
|------|----------|-------------|
| `/opt/skuel/app/` | the rsync'd working tree | `./dev deploy` (mirrors your local checkout) |
| `/opt/skuel/app/.env.production` | non-secret config (copy of `.env.production.example`, filled in) | created once by hand; **survives deploys** (`.deployignore` excludes `.env*` from transfer AND deletion) |
| `/opt/skuel/secrets.env` | secrets, mode **0600** | created once by hand; loaded via compose `env_file` |

The droplet is **headless** — no keychain. `get_credential()` falls back to the process environment, so env-file injection is the secrets path. Required in `secrets.env`: `NEO4J_PASSWORD`, `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `SESSION_SECRET_KEY`. Optional per-feature: `RESEND_API_KEY` (when `EMAIL_ENABLED=true`), `ANTHROPIC_API_KEY`, `STRIPE_WEBHOOK_SECRET`, and `SIGNUP_INVITE_CODE` if you prefer keeping the invite code out of `.env.production` (it resolves through `get_credential()` either way).

`INTELLIGENCE_TIER=full` **boot-fails without `OPENAI_API_KEY` and `DEEPGRAM_API_KEY`** — that is correct fail-fast behavior, not a bug: FULL-tier dependencies are required, never silently degraded.

---

## Prerequisites (first deploy only)

On your machine:

- [ ] An ssh_config `Host` alias for the droplet (default name `skuel-droplet`; override with `SKUEL_DROPLET_SSH`) carrying user/IP/key.
- [ ] The content vault at `INGESTION_PATH` (defaults to `~/0bsidian/0vault`) if deploying content.

On the droplet (Ubuntu LTS assumed):

- [ ] Docker Engine + the compose plugin (`curl -fsSL https://get.docker.com | sh`).
- [ ] `/opt/skuel/` layout — `deploy.sh` creates `app/`, `content-vault/`, `personal-vault/` itself; you create the two env files **before the first `./dev deploy`** (compose refuses to start without them — both are `env_file` entries):
  ```bash
  # On the droplet:
  mkdir -p /opt/skuel/app
  # secrets — 0600, root-owned is fine (compose reads it, the app never does)
  touch /opt/skuel/secrets.env && chmod 0600 /opt/skuel/secrets.env

  # From your machine — the template never lands via deploy (rsync excludes
  # .env* from transfer AND deletion, which is also why your filled-in copy
  # survives every subsequent deploy):
  scp app/.env.production.example skuel-droplet:/opt/skuel/app/.env.production
  ssh skuel-droplet   # then edit /opt/skuel/app/.env.production with real values
  ```
- [ ] Firewall: inbound TCP 22 (your IP), 80, 443 (+ UDP 443 for HTTP/3). Nothing else — the app port is loopback-only.

DNS:

- [ ] A records for the apex (`skuel.app`) **and** `www` pointing at the droplet. Caddy needs both resolvable to provision certificates (the `www` site block issues its own cert for the redirect).

`.env.production` values that trip people up:

- **`FORWARDED_ALLOW_IPS`** — uvicorn trusts `X-Forwarded-For` only from these sources. Caddy is the only other container on the compose network; Docker's default address pools live under `172.16.0.0/12`, so that CIDR is the shipped default. Without it, every visitor shares Caddy's container IP — rate-limit buckets and the AuthEvent audit trail need the real client IP.
- **`APP_URL=https://skuel.app`** — absolute origin used in outbound links (password-reset emails).
- **`SKUEL_DOMAIN` / `ACME_EMAIL`** — read by the caddy container from `.env.production` via compose `env_file` (the `{$VAR}` placeholders in the Caddyfile are resolved by Caddy from its container environment, not by compose interpolation — no shell exports needed).
- **`SIGNUP_INVITE_CODE`** — set it. It is the real throttle on AuraDB Free node-cap growth and LLM-cost abuse. Registration then requires the code (constant-time check **before** any account is created); unset = open signup.

### Local rehearsal

The full stack runs locally without a droplet, but the compose file's two `env_file` entries are mandatory — create both first:

```bash
cd ~/skuel/app
cp .env.production.example .env.production   # set SKUEL_DOMAIN=localhost; point
                                             # NEO4J_URI at a scratch AuraDB Free instance
sudo mkdir -p /opt/skuel                     # same secrets path the droplet uses
sudo touch /opt/skuel/secrets.env && sudo chmod 0600 /opt/skuel/secrets.env
# fill secrets.env: NEO4J_PASSWORD, OPENAI_API_KEY, DEEPGRAM_API_KEY, SESSION_SECRET_KEY

docker compose -f docker-compose.production.yml up --build
```

With `SKUEL_DOMAIN=localhost` Caddy issues a certificate from its internal CA and serves `https://localhost` (browser trust warning expected). The scratch Aura instance rehearses the real `neo4j+s://` path end to end — schema auto-creation, FULL-tier fail-fast, wake-from-pause. Keep the local `.env.production` out of git (already `.gitignore`d).

---

## Deploying

```bash
./dev deploy              # rsync → build → up → health gate
./dev deploy --content    # + sync content vault and run the in-container vault sync
./dev deploy --dry-run    # print every command, execute nothing
```

`/scripts/deploy.sh` is a one-shot push deploy — no CI/CD dependency; what you have locally is what ships:

1. **rsync the working tree** to `/opt/skuel/app` with `--delete` (exact mirror), excluding `.deployignore` paths from both transfer and deletion — the droplet-side `.env.production` and `logs/` survive every deploy.
2. **chown the writable bind mounts** (`/opt/skuel/personal-vault`, `app/logs`) to UID 10001. A bind mount hides the image's chowned directory, so ownership is a host-side concern; the content vault stays root-owned (mounted `:ro`).
3. `--content`: rsync the content vault → `/opt/skuel/content-vault/` (excluding `Resources/` — binary attachments, not ingestible curriculum).
4. **`compose build && up -d`** on the droplet.
5. **Health gate**: poll `http://127.0.0.1:5001/health/ready` over SSH, up to 24 × 5 s ≈ 2 min. `/health/ready` returns 503 until Neo4j answers, so passing means the app booted **and** AuraDB responded — including wake-from-pause on a Free instance.
6. **Only after a green gate**, tag `skuel-app:latest` as `skuel-app:rollback`. The rollback tag is written nowhere else, so it always names the newest image that passed a gate — a failed deploy (or a rerun of one) can never move it.
7. `--content`: run the one-shot in-container content-vault sync (`vault_bridge_sync.py --vault content`).

A failed gate exits non-zero and prints rollback instructions. **No auto-rollback** — rolling back is a deliberate human call (see the runbook below).

---

## Operations Runbook

### Weekly: telemetry retention (keeps the Free node cap safe)

AuraDB Free caps the graph at **200k nodes / 400k relationships** (Aura FAQ, verified 2026-07-24 — the 50k/175k figures still on the product page are the stale 2021 launch limits). System telemetry (AuthEvent/SearchEvent/Interaction/stale VIEWED) grows without bound and dwarfs the curriculum; prune it weekly with a **host-side cron** running the one-shot retention command in-container:

```cron
# /etc/cron.d/skuel-telemetry — weekly, Sunday 04:00
0 4 * * 0  root  cd /opt/skuel/app && docker compose -f docker-compose.production.yml exec -T skuel-app python scripts/telemetry_retention.py >> /opt/skuel/telemetry-cron.log 2>&1
```

One-shot, not a daemon — this preserves the "no background workers" guarantee (ADR-080 H0).

On auto-pause: Aura Free pauses after ~72 hours **without connections** — a weekly cron alone would not prevent that. In practice the question doesn't arise while the app is up: the app's graph-health metrics poller queries Neo4j every 5 minutes for as long as the container runs, so an active deployment never goes idle. Pausing only happens if the app itself is down past the pause window, and that wake-up is exactly what `connect_with_retry` and the deploy health gate absorb.

Saved discussions (`:ConversationSession`) are **never** pruned — explicitly-saved user content, not telemetry. Windows/batch size: `/core/constants.py` `TelemetryRetention`. Dry-run first from any shell: `docker compose … exec -T skuel-app python scripts/telemetry_retention.py --dry-run`.

If the Prometheus alerts `AuraNodeCapApproaching` / `AuraRelationshipCapApproaching` fire (80% of cap on the `skuel_total_entities` / `skuel_total_relationships` gauges, `/monitoring/prometheus/alerts.yml`): run retention, review growth with `./dev knowledge-health`, and consider tightening the invite gate or moving to a paid tier.

### Backups: Aura snapshots + count exports

AuraDB Free has **no automatic backups** — only **on-demand snapshots** (one at a time), triggered manually from the instance's Snapshots tab in the [Aura console](https://console.neo4j.io/), exportable/downloadable as a `.backup` file. Verified 2026-07-24; re-check the [Aura backup docs](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/) before relying on this.

Cheap integrity record to pair with a snapshot — archive a count export:

```bash
# Run against Aura (NEO4J_* env pointing at the instance)
uv run python scripts/export_entity_counts.py > counts_$(date +%Y%m%d).json
```

Pure Cypher, JSON to stdout; `--compare earlier.json` diffs live counts and exits 1 on any mismatch. Take a snapshot + count export before anything risky (bulk ingest, retention with a new window, tier change).

The personal vault (`/opt/skuel/personal-vault`) and per-user vaults (`user_vaults` volume) live only on the droplet — include `/opt/skuel` in whatever host backup you run (DO droplet snapshots are the low-effort answer).

### Uptime

Point an external pinger (UptimeRobot or similar) at **`https://skuel.app/health`** — liveness, unauthenticated, cheap. Don't ping `/health/ready` for uptime: it exercises Neo4j on every probe, and a paused-instance wake would read as flapping.

### Logs

```bash
ssh skuel-droplet
cd /opt/skuel/app
docker compose -f docker-compose.production.yml logs -f skuel-app     # app
docker compose -f docker-compose.production.yml logs -f caddy         # TLS/proxy
docker compose -f docker-compose.production.yml logs --tail 200 skuel-app
```

Both containers use json-file logging capped at 10 MB × 3 files — bounded by construction, no logrotate needed. The app also writes `logs/` under the repo dir (bind-mounted, survives deploys).

### Rollback

`skuel-app:rollback` always holds the last image that **passed a health gate** (absent on a first deploy). To roll back after a bad deploy:

```bash
ssh skuel-droplet
cd /opt/skuel/app
docker compose -f docker-compose.production.yml logs --tail 200 skuel-app   # inspect first
docker tag skuel-app:rollback skuel-app:latest
docker compose -f docker-compose.production.yml up -d
```

Note the code on disk is still the new tree (rsync already ran) — rollback restores the running **image**, buying time to fix forward. `./dev deploy` again when fixed.

### Hardening checklist (what ships, and the knobs)

| Concern | Mechanism | Knob |
|---------|-----------|------|
| Signup abuse | invite code, constant-time check before account creation | `SIGNUP_INVITE_CODE` (via `get_credential()`, env fallback) |
| LLM/transcription cost abuse | per-user AI tier gate (ADR-043) on every AI surface incl. all five journals routes + `/api/journals/folder-transcribe`; REGISTERED resolves to effective CORE | admin grants MEMBER |
| Brute force | 3-layer login protection + per-IP register/reset throttles (`/adapters/inbound/rate_limit.py`, in-memory) | — |
| Transport | Caddy auto-TLS; production boot refuses plaintext `NEO4J_URI` schemes | `SKUEL_DOMAIN`, `ACME_EMAIL` |
| Browser headers | `SecurityHeadersMiddleware` as the **outermost ASGI wrapper** in `main.py` (500s are stamped too): X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, CSP **Report-Only** | promote CSP to enforcing once the console stays clean |
| HSTS | deliberately absent for now — a proxy concern (Caddyfile note); hardcoding it would poison local `SKUEL_DOMAIN=localhost` rehearsal | add scoped to the real domain at launch |
| Client IPs behind proxy | `proxy_headers=True` + `FORWARDED_ALLOW_IPS` in `main.py` | `FORWARDED_ALLOW_IPS` |
| Session cookies | `https_only` + `SameSite=Strict` in production; boot fails without `SESSION_SECRET_KEY` | `SESSION_SECRET_KEY` in secrets.env |
| Password reset email | Resend; boot fails fast when enabled without the key | `EMAIL_ENABLED`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `APP_URL` |
| Node cap | weekly retention cron + 80%-of-cap Prometheus alerts | see above |

Deferred (tracked in [security-hardening-deferred.md](../roadmap/security-hardening-deferred.md) and ADR-080): per-user daily LLM quotas, session invalidation on role change, CSP enforcement, email verification/CAPTCHA, `pip-audit` in CI, mid-request Aura-pause resilience.

---

## Troubleshooting

**Health gate times out** — `docker compose … logs skuel-app`. Usual suspects: missing FULL-tier key in `secrets.env` (boot fails fast, by design), wrong `NEO4J_PASSWORD`, or a plaintext `NEO4J_URI` scheme (production refuses it at boot with the got-scheme named).

**Caddy serves no certificate** — both DNS A records (apex + www) must point at the droplet and ports 80/443 must be reachable from the internet; check `docker compose … logs caddy` for the ACME error.

**Writes fail with EACCES in personal-vault or logs** — the bind mounts must be owned by UID 10001. `./dev deploy` chowns them every run; if you created directories by hand, re-run a deploy or `chown -R 10001:10001` them.

**Every visitor shares one IP in AuthEvents/rate limits** — `FORWARDED_ALLOW_IPS` unset or not matching the compose network; see Prerequisites.

**App container healthy but `https://skuel.app` 502s** — Caddy and the app must share the compose default network (they do unless you changed it); `docker compose … exec caddy wget -qO- http://skuel-app:5001/health`.

---

## Related Documentation

- [AuraDB Migration Guide](./AURADB_MIGRATION_GUIDE.md) — getting the local graph into AuraDB Free
- [Neo4j Setup Migration Summary](./NEO4J_SETUP_MIGRATION_SUMMARY.md) — how the deployment path evolved (and what was skipped)
- [ADR-080](../decisions/ADR-080-auradb-three-horizon-strategy.md) — AuraDB three-horizon strategy
- `/.claude/skills/docker/SKILL.md` — compose-file inventory and container conventions
- [security-hardening-deferred.md](../roadmap/security-hardening-deferred.md) — deferred hardening items

---

**Last Updated:** 2026-07-24
**Maintained By:** SKUEL Core Team
