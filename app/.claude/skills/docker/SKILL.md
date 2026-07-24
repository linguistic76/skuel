---
name: docker
description: Expert guide for SKUEL's Docker setup — the two-directory compose split, the production droplet stack (app + Caddy → AuraDB), Dockerfile.production conventions, correct startup sequences, and ./dev deploy. Use when running the app in Docker, modifying Dockerfile.production or the compose files, debugging container networking, or deploying to the droplet.
allowed-tools: Read, Grep, Glob, Bash
---

# Docker in SKUEL

SKUEL uses Docker in two contexts: **local development** (Neo4j always; optionally the full stack) and the **production droplet** (app + Caddy containers talking to Neo4j AuraDB Free — no Neo4j container in production). Getting the file split wrong is the most common source of "it works locally but not in Docker" confusion.

---

## The Two-Directory Split

```
~/skuel/
├── infrastructure/          ← LOCAL Neo4j only. Independent lifecycle. Deploys nowhere.
│   ├── docker-compose.yml   ← THE canonical Neo4j definition (single source of truth)
│   ├── .env                 ← Neo4j credentials + memory config
│   └── neo4j/               ← Persistent data, logs, plugins (host-side volumes)
│
└── app/                     ← SKUEL application
    ├── docker-compose.yml            ← DEV: Neo4j (via extends) + App; monitoring/finance profiles
    ├── docker-compose.production.yml ← DROPLET: skuel-app + caddy (no Neo4j — AuraDB)
    ├── Caddyfile                     ← TLS termination + reverse proxy for the droplet stack
    ├── Dockerfile                    ← dev image (app/docker-compose.yml builds this)
    ├── Dockerfile.production         ← droplet image (python:3.14-slim, non-root, port 5001)
    ├── .deployignore                 ← rsync exclude list for scripts/deploy.sh
    ├── .env.production.example       ← every droplet env var + the secrets.env shape
    └── scripts/deploy.sh             ← ./dev deploy — rsync + build + health gate
```

**Why two directories?** Neo4j's lifecycle is independent of the app. You restart the app dozens of times a day; you almost never restart Neo4j. The `infrastructure/` directory is also the single place all local graph data lives.

**Compose `extends` pattern:** `app/docker-compose.yml` inherits the Neo4j service from `infrastructure/docker-compose.yml`, overriding only deltas (APOC-only plugins, dev memory defaults). Volume paths resolve relative to the base file, so data still lives in `infrastructure/neo4j/`.

---

## The Three Compose Files

| File | What it runs | When to use it |
|------|--------------|----------------|
| `infrastructure/docker-compose.yml` | Neo4j only (canonical definition) | Local dev database. `./dev up-neo4j` starts it. |
| `app/docker-compose.yml` | Neo4j (via `extends`) + App. Prometheus + Grafana behind the `monitoring` profile; Firefly III + MariaDB behind `finance` (ADR-052). | Full local Docker stack. |
| `app/docker-compose.production.yml` | `skuel-app` + `caddy` — nothing else. Neo4j is AuraDB, reached over `neo4j+s://`. | The droplet. Also local rehearsal with `SKUEL_DOMAIN=localhost`. |

There are no commented-out "future services" anywhere — Redis/Ollama/nginx blocks were deleted when the production compose was rewritten (2026-07-24). One Path Forward: a service enters compose when adopted, not speculatively.

**Profile-gated extras (dev compose):**

```bash
docker compose --profile monitoring up -d              # + Prometheus + Grafana
docker compose --profile finance up -d firefly firefly-db   # Firefly III (web UI :8081)
```

Firefly requires `FIREFLY_APP_KEY` in `.env` with the `base64:` prefix — generate via `printf "base64:%s\n" "$(head -c 32 /dev/urandom | base64)"`. Keep `.env` comments on their own lines (compose absorbs inline `#` into values); after editing `.env`, use `up -d` (not `restart`) so the container is recreated with the new env.

---

## Correct Startup Sequences

**Recommended local workflow (fastest iteration):**

```bash
./dev up-neo4j        # Start Neo4j only (Docker, detached)
./dev serve           # Run the app locally (uv run python main.py)
```

**Full local Docker stack:**

```bash
cd ~/skuel/app
docker compose up -d                          # Neo4j + App
docker compose --profile monitoring up -d     # + Prometheus + Grafana
```

**Production stack (droplet — or local rehearsal):**

```bash
# On the droplet this is what ./dev deploy runs remotely:
cd /opt/skuel/app
docker compose -f docker-compose.production.yml build
docker compose -f docker-compose.production.yml up -d

# Local rehearsal: SKUEL_DOMAIN=localhost in .env.production → https://localhost
# via Caddy's internal CA (browser warning expected). Point NEO4J_URI at a
# scratch AuraDB Free instance to rehearse the real neo4j+s:// path.
```

Config layering on the droplet: `.env.production` (non-secret, survives deploys) + `/opt/skuel/secrets.env` (0600 — `NEO4J_PASSWORD`, `OPENAI_API_KEY`, `DEEPGRAM_API_KEY`, `SESSION_SECRET_KEY`, optional per-feature keys), both loaded via compose `env_file`. Caddy reads `SKUEL_DOMAIN`/`ACME_EMAIL` from `.env.production` via its own `env_file` — no shell exports needed.

Deploying is `./dev deploy` (`--content`, `--dry-run`): rsync via `.deployignore` → chown writable bind mounts to UID 10001 → build + up → poll `/health/ready` (~2 min default, `SKUEL_DEPLOY_HEALTH_ATTEMPTS` widens; covers AuraDB wake-from-pause) → only past a green gate, an ID-based idempotent promote tags `skuel-app:latest` as `skuel-app:rollback`, keeping the previous gate-passed image as `skuel-app:rollback-prev`. No auto-rollback; a failed gate auto-prints app logs. See `/docs/deployment/DO_MIGRATION_GUIDE.md` for the runbook.

---

## Dockerfile.production Conventions

```dockerfile
FROM python:3.14-slim AS builder      # matches .python-version / pyproject.toml
# uv from ghcr.io/astral-sh/uv; RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.14-slim AS production
# useradd -r -m -u 10001 -g skuel     ← UID/GID pinned; -m matters (see below)
# copies .venv from builder — no uv in the final image
# pre-creates /app/logs /app/data/user_vaults + vault mount points, chowned
# ENV APP_HOST=0.0.0.0 APP_PORT=5001  ← container contract baked into the image
# HEALTHCHECK: curl -f http://localhost:5001/health
# CMD ["python", "main.py"]
```

Rules learned the hard way (each broke a real rehearsal or deploy):

- **`uv sync --frozen --no-dev --no-install-project`** — exactly these flags. `--no-root` is a Poetry-ism uv rejects (the image never built); `--frozen` makes a stale `uv.lock` fail the build instead of silently re-resolving; `--no-install-project` because the app ships as source, not a package. `uv.lock` must be committed.
- **`useradd -m`** — CredentialStore initializes `~/.skuel` at import even in the headless env-file shape; a system user without a home directory crashes boot.
- **UID/GID pinned to 10001** — host-side writable bind mounts (droplet personal-vault, `logs/`) must be chowned to the container user by `deploy.sh`, which needs a UID it can rely on. A bind mount hides the image's chowned directory, so ownership is a host-side concern.
- **Pre-create every compose mount point in the image** — a mount point absent from the image is auto-created root-owned by the daemon, and the app then can't write siblings (e.g. `/app/data/reports`).
- **The container contract is port 5001** — baked as `ENV APP_PORT=5001` so a bare `docker run` honors it; Caddy proxies to `skuel-app:5001`, the healthcheck and deploy gate hit it. Do not change it.
- **`.dockerignore` matters** — without it the build context ships the entire worktree (`.venv`, `node_modules`, `htmlcov`, `.env*`) into image layers.
- **The env vars are `APP_HOST` / `APP_PORT` / `APP_DEBUG`** — the config reads `APP_*` (the former `API_*` split was a dead knob that made containers silently listen on 8000; killed 2026-07-24).

---

## Port Map

| Context | Port | How to reach it |
|---------|------|-----------------|
| `uv run python main.py` (local) | 8000 (`APP_PORT` in `.env`) | `http://localhost:8000` |
| `docker compose up` (dev stack) | `APP_PORT` (default 8000), mapped to host | `http://localhost:8000` |
| Droplet `skuel-app` container | 5001, published **loopback-only** (`127.0.0.1:5001`) | droplet-side only: health gate, curl |
| Droplet Caddy | 80/443 (+443/udp HTTP/3) | `https://skuel.app` |

The app port is never exposed to the internet — Caddy fronts the world.

---

## Networking Notes

- **Dev stack:** the app container reaches Neo4j by service name (`NEO4J_URI: bolt://neo4j:7687` — set in the compose file, overriding the `.env` localhost value).
- **Production:** there is no Neo4j container to reach — `NEO4J_URI=neo4j+s://<dbid>.databases.neo4j.io`. Production boot **refuses plaintext schemes** (`/core/config/validation.py`). Startup tolerates a paused/waking Free instance (`connect_with_retry`).
- **Caddy → app:** by service name over the compose default network (`reverse_proxy skuel-app:5001`).
- **Real client IPs behind Caddy:** `main.py` passes `proxy_headers=True` + `FORWARDED_ALLOW_IPS` to uvicorn; the droplet sets `FORWARDED_ALLOW_IPS=172.16.0.0/12` (Docker's default address pools). Unset locally → inert.
- **Reaching the host from a container** (dev, Linux): `172.17.0.1` (default bridge gateway); macOS/Windows: `host.docker.internal`.

---

## Deep Dive Resources

- `/docs/deployment/DO_MIGRATION_GUIDE.md` — droplet deployment guide + operations runbook
- `/docs/deployment/AURADB_MIGRATION_GUIDE.md` — moving the graph data to AuraDB Free
- `/docs/patterns/NEO4J_SERVER_TUNING.md` — every `NEO4J_*` server knob (and which are `AURA-TEMPORARY`)
- `.claude/skills/prometheus-grafana/` — monitoring stack (dev compose, `monitoring` profile)
- `/docs/TROUBLESHOOTING.md` — container-specific failure modes
