---
name: docker
description: Expert guide for SKUEL's Docker setup — the two-directory compose split, Dockerfile.production conventions, correct startup sequences, and the differences between local, Droplet, and App Platform Docker usage. Use when running the app in Docker, modifying Dockerfile.production, debugging container networking, or deploying to DigitalOcean.
allowed-tools: Read, Grep, Glob, Bash
---

# Docker in SKUEL

SKUEL uses Docker in three contexts: local development, DigitalOcean Droplet (Neo4j), and App Platform (app). The setup is deliberately split across two directories. Getting this wrong is the most common source of "it works locally but not in Docker" confusion.

---

## The Two-Directory Split

```
~/skuel/
├── infrastructure/          ← Neo4j only. Independent lifecycle.
│   ├── docker-compose.yml   ← THE canonical Neo4j definition (single source of truth)
│   ├── .env                 ← Neo4j credentials + memory config
│   └── neo4j/               ← Persistent data, logs, plugins (host-side volumes)
│       ├── data/
│       ├── logs/
│       └── plugins/
│
└── app/                     ← SKUEL application + monitoring
    ├── docker-compose.yml           ← Neo4j (via extends) + App + Monitoring (profile-gated)
    ├── docker-compose.production.yml ← Production app + pre-wired future services
    ├── Dockerfile.production        ← The image App Platform deploys
    ├── .env                         ← App config (Neo4j URI, API keys, ports)
    └── main.py                      ← Entry point
```

**Why two directories?** Neo4j's lifecycle is independent of the app. You restart the app during development dozens of times; you almost never restart Neo4j. Putting them in the same compose file couples those lifecycles. It also makes Neo4j backup and data management cleaner — the `infrastructure/` directory is the single place where all graph data lives.

**Compose `extends` pattern:** `app/docker-compose.yml` inherits the Neo4j service from `infrastructure/docker-compose.yml` using `extends`, overriding only what differs (no GenAI plugin, memory defaults, network). This eliminates duplication and prevents configuration drift. Volume paths resolve relative to the base file, so data still lives in `infrastructure/neo4j/`.

---

## The Three Compose Files

| File | What it runs | When to use it |
|------|--------------|----------------|
| `infrastructure/docker-compose.yml` | Neo4j (canonical definition, with GenAI + APOC plugins) | Standalone Neo4j (e.g., on a Droplet). Also the base that `app/docker-compose.yml` extends. |
| `app/docker-compose.yml` | Neo4j (via `extends`) + App. Prometheus + Grafana behind `monitoring` profile. | Default dev workflow. `docker compose up` starts Neo4j + App only. |
| `app/docker-compose.production.yml` | SKUEL app + pre-wired future services (Redis, Ollama, nginx, etc.) | Production deployment reference. Most services are disabled. See `FUTURE_SERVICES.md`. |

**The Neo4j definition inside `docker-compose.production.yml` is commented out.** It exists as a fallback reference only. Always use `infrastructure/docker-compose.yml` for Neo4j.

**Monitoring is profile-gated.** Prometheus and Grafana are behind the `monitoring` profile — they do not start by default. To include them:

```bash
docker compose --profile monitoring up       # All services including monitoring
docker compose --profile monitoring up -d    # Detached
```

---

## Correct Startup Sequence

Order matters. Neo4j must be healthy before the app starts, because the app connects and probes the database on boot.

**Recommended local workflow (fastest iteration):**

```bash
./dev up-neo4j        # Start Neo4j only (Docker, detached)
./dev serve           # Start app locally (uv run python main.py)
```

**Full Docker stack (Neo4j + App):**

```bash
cd ~/skuel/app
docker compose up -d                          # Neo4j + App (no monitoring)
docker compose --profile monitoring up -d     # Neo4j + App + Prometheus + Grafana
```

The `depends_on` with `condition: service_healthy` in the compose file ensures the app waits for Neo4j automatically.

**Standalone Neo4j (infrastructure directory):**

```bash
cd ~/skuel/infrastructure
docker compose up -d     # Runs the canonical Neo4j definition directly
```

Use this when running Neo4j independently (e.g., on a Droplet) without the app compose layer.

---

## Dockerfile.production Conventions

```dockerfile
FROM python:3.12-slim as builder   # Must match pyproject.toml python = ">=3.12"
# ... installs uv, runs `uv sync --only=main`

FROM python:3.12-slim as production
# Non-root user (skuel:skuel) for security
# Copies .venv from builder stage — no uv in the final image
# Health check: curl http://localhost:5001/health
# EXPOSE 5001
# CMD ["python", "main.py"]        # Entry point is main.py
```

Key rules when modifying this file:
- **Python version must match `pyproject.toml`.** `pyproject.toml` declares `python = ">=3.12,<4.0"`. The Dockerfile base image must be `3.12` or later.
- **The entry point is `main.py`.** Not `skuel.py`. There is no `skuel.py`.
- **The container always listens on port 5001.** The `APP_PORT` in `.env` (currently 8000) is for `uv run` local dev. Inside the container, the port is 5001. See TROUBLESHOOTING.md if you get confused here.
- **uv is a build-time dependency only.** The production stage copies the `.venv` directory. Do not add uv to the production stage.
- **`uv.lock` must be committed.** The builder stage copies `pyproject.toml` and `uv.lock` before installing. If `uv.lock` is missing or stale, the build will fail or produce an unpredictable environment.

---

## Port Map: Local vs Docker

| Context | APP_PORT | Where it listens | How to reach it |
|---------|----------|------------------|-----------------|
| `uv run python main.py` | 8000 (from `.env`) | Host port 8000 | `http://localhost:8000` |
| `docker compose up` (app/) | 5001 (container) mapped to host | Host port 5001 | `http://localhost:5001` |
| App Platform deploy | 5001 (container) | Managed URL | `https://skuel-app-xxx.ondigitalocean.app` |

The `APP_PORT` variable in `.env` is read by `uv run` for local development. Docker compose sets the container's `APP_PORT` independently. Do not change the container port in `Dockerfile.production` — downstream health checks and port mappings depend on 5001.

---

## Neo4j Port Binding: Local vs Droplet

The single difference between the local `infrastructure/docker-compose.yml` and the Droplet version is the Bolt binding:

| Environment | Bolt listen address | Why |
|-------------|--------------------|----|
| Local | `127.0.0.1:7687` | Nothing outside the machine needs to reach it |
| Droplet | `0.0.0.0:7687` | App Platform connects over the network |

HTTP (7474) stays on `127.0.0.1` in both cases. If you need Neo4j Browser on a Droplet, SSH-tunnel it:

```bash
ssh -L 7474:localhost:7474 root@<droplet-ip>
# Then open http://localhost:7474 locally
```

See `docs/deployment/DO_MIGRATION_GUIDE.md` for the full Droplet setup.

---

## Cross-Platform Gotcha: Reaching the Host from a Container

When the app container needs to reach Neo4j running on the same machine (but outside its network namespace), the address depends on the OS:

| Host OS | Address to use | Notes |
|---------|---------------|-------|
| macOS / Windows | `host.docker.internal` | Built into Docker Desktop |
| Linux | `172.17.0.1` | Default Docker bridge gateway |

`app/docker-compose.yml` documents this in its comments. If you are on Linux and Neo4j is unreachable from the app container, this is the first thing to check.

On a Droplet or App Platform, this is not relevant — Neo4j is on a different machine entirely, reached by its IP address.

---

## Deep Dive Resources

- `docs/deployment/DO_MIGRATION_GUIDE.md` — Droplet Neo4j + App Platform app deployment
- `docs/deployment/AURADB_MIGRATION_GUIDE.md` — Stage 3: replacing Droplet Neo4j with AuraDB
- `docs/development/GENAI_SETUP.md` — GenAI/embeddings setup (HuggingFace Inference API, Python-side)
- `.claude/skills/prometheus-grafana/` — Monitoring stack (runs in app compose)
- See TROUBLESHOOTING.md in this directory for container-specific failure modes
