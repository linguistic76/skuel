---
title: Starting SKUEL
related_docs:
  - docs/development/DEVELOPMENT_SETUP.md
  - docs/deployment/DO_MIGRATION_GUIDE.md
updated: 2026-03-17
---
# Starting SKUEL

Quick reference for starting the app. For first-time setup (installing dependencies, seeding users, env vars), see [`DEVELOPMENT_SETUP.md`](DEVELOPMENT_SETUP.md).

---

## Daily Local Dev (Recommended)

Two terminals: Neo4j first, then the app.

**Terminal 1 — start Neo4j:**
```bash
./dev up-neo4j
```
Runs Neo4j in detached Docker container (`docker compose up neo4j -d`). Ready in ~10 seconds.

**Terminal 2 — start the app:**
```bash
./dev serve
```
Equivalent to `uv run python main.py`. App starts on `http://localhost:8000`.

---

## Full Docker Stack

Starts Neo4j + App together (monitoring is opt-in):

```bash
./dev up          # attached (logs in terminal)  — Neo4j + App
./dev up -d       # detached (background)        — Neo4j + App
./dev up-monitoring       # Neo4j + App + Prometheus + Grafana
./dev up-monitoring -d    # same, detached
```

| Service    | URL                        | Starts by default? |
|------------|----------------------------|--------------------|
| App        | http://localhost:8000       | Yes                |
| Neo4j      | http://localhost:7474       | Yes                |
| Prometheus | http://localhost:9090       | No (`monitoring` profile) |
| Grafana    | http://localhost:3000       | No (`monitoring` profile) |

---

## Stopping

```bash
./dev down        # stop all Docker services
```

---

## Command Reference

| Command                        | What it does                              |
|--------------------------------|-------------------------------------------|
| `./dev up-neo4j`               | Start Neo4j only (Docker, detached)       |
| `./dev serve`                  | Start app (`uv run python main.py`)       |
| `./dev up`                     | Start Neo4j + App (Docker)                |
| `./dev up -d`                  | Start Neo4j + App (Docker, detached)      |
| `./dev up-monitoring`          | Start Neo4j + App + Prometheus + Grafana  |
| `./dev up-monitoring -d`       | Same, detached                            |
| `./dev down`                   | Stop all Docker services                  |
| `uv run python main.py`       | Start app directly (same as `./dev serve`)|

---

## Troubleshooting

**App fails to start — database connection error**
Neo4j isn't running. Start it first: `./dev up-neo4j`

**"User not found: user.dev"**
Dev users not seeded. Run once:
```bash
uv run python scripts/seed_dev_users.py
```

**Port 8000 already in use**
```bash
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
```

**Neo4j container won't start**
Check Docker is running, then: `./dev down && ./dev up-neo4j`

For more diagnostic help, see [`/docs/TROUBLESHOOTING.md`](../TROUBLESHOOTING.md).
