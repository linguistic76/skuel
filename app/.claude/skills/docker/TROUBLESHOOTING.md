# Docker Troubleshooting

Failure modes specific to SKUEL's Docker setup, in order of likelihood.

---

## Container starts but app cannot connect to Neo4j

**Symptom:** App logs show connection errors or timeouts to Neo4j. Neo4j container is healthy.

**Cause 1 — Neo4j is not ready yet.**
The GenAI plugin takes 60-90 seconds to initialize on first container start. Neo4j's health check passes (HTTP 7474 responds) before the plugin is fully loaded. If the app started before the plugin finished initializing, it may have connected fine but embedding operations will fail silently.

```bash
# Check if Neo4j is actually fully ready (not just HTTP-alive):
docker exec skuel-neo4j cypher-shell -u neo4j -p <password> \
  "CALL db.indexes() YIELD name RETURN count(*) AS n"
# If this hangs or errors, Neo4j is still initializing.
```

Fix: wait for the GenAI plugin log message, then restart the app container:
```bash
docker compose -f ~/skuel/infrastructure/docker-compose.yml logs neo4j | tail -20
# Look for: "GenAI plugin loaded" or similar
docker compose restart skuel-app
```

**Cause 2 — Wrong host address (Linux).**
On Linux, `host.docker.internal` does not resolve. The app container cannot reach Neo4j on the host machine.

```bash
# In app/.env or docker-compose environment, NEO4J_URI should be:
NEO4J_URI=bolt://172.17.0.1:7687    # Linux
NEO4J_URI=bolt://host.docker.internal:7687  # macOS / Windows
```

**Cause 3 — Neo4j Bolt is bound to localhost only.**
If `infrastructure/docker-compose.yml` has `127.0.0.1:7687:7687`, nothing outside that machine can connect. This is correct for local dev (the app reaches it via the host bridge), but wrong for a Droplet where App Platform connects over the network. Change to `0.0.0.0:7687:7687` on the Droplet.

---

## App container exits immediately on start

**Symptom:** `docker compose up` shows the container starting and stopping. Logs show a Python error.

**Check the logs first:**
```bash
docker compose logs skuel-app
```

Common causes:

**Entry point not found.** If you see `python: can't open file 'skuel.py'`, the CMD in `Dockerfile.production` or the `command:` in `docker-compose.yml` is wrong. The entry point is `main.py`. Both files were corrected on 2026-02-05; if you are on an older image, rebuild:
```bash
docker compose build skuel-app
docker compose up -d skuel-app
```

**Import error due to Python version mismatch.** `pyproject.toml` requires Python 3.12+. If `Dockerfile.production` uses `python:3.11-slim`, any file using 3.12 syntax (e.g., `type` statements, PEP 695 generics) will fail at import time. Rebuild with the corrected Dockerfile:
```bash
docker compose build --no-cache skuel-app
```

**Missing dependency.** If `uv.lock` is out of date or not committed, `uv sync` in the builder stage installs different versions than expected. Regenerate:
```bash
uv lock
git add uv.lock
docker compose build --no-cache skuel-app
```

---

## Health check fails, container restarts

**Symptom:** Container shows as `unhealthy` and keeps restarting (if `restart: unless-stopped` is set, it stays up but logged as unhealthy).

The health check in `Dockerfile.production` and `docker-compose.production.yml` hits `http://localhost:5001/health`. Two things go wrong here:

**The app is listening on the wrong port.** If `APP_PORT` inside the container is set to something other than 5001 (e.g., 8000 from `.env`), the app listens on that port but the health check hits 5001. In `docker-compose.yml`, the container environment sets `APP_PORT: ${APP_PORT:-5001}`. If your `.env` has `APP_PORT=8000`, Docker Compose reads that and passes 8000 into the container. The app then listens on 8000, health check hits 5001, fails.

Fix: either remove `APP_PORT` from `.env` (it defaults to 5001 in compose), or set it explicitly to 5001 in the compose `environment` block:
```yaml
environment:
  APP_PORT: "5001"   # Hardcoded for container. .env APP_PORT is for uv run only.
```

**The `/health` endpoint does not exist or returns non-200.** Check:
```bash
docker exec skuel-app curl -f http://localhost:5001/health
```
If this returns an error, the endpoint itself is broken — that is an app issue, not a Docker issue.

---

## Neo4j data disappears after container restart

**Symptom:** Neo4j starts fresh (empty database) after a `docker compose down` or Droplet reboot.

The volumes in `infrastructure/docker-compose.yml` are bind mounts to `./neo4j/data` (relative to the compose file). If that directory does not exist or the container was run from a different working directory, data goes into an ephemeral anonymous volume inside the container.

Verify:
```bash
ls -la ~/skuel/infrastructure/neo4j/data/
# Should contain Neo4j data files (graph.db, etc.)
```

If it is empty, the data was never persisted to the host. On a Droplet, make sure you `cd /opt/skuel-neo4j` (or wherever the compose file lives) before running `docker compose up`. The relative paths resolve from the directory containing `docker-compose.yml`.

---

## Build is slow or pulls wrong dependencies

**Symptom:** `docker compose build` takes 5+ minutes even when only code changed.

Docker layers cache by file hash. The Dockerfile copies `pyproject.toml` and `uv.lock` first, then runs `uv sync`. If either file changed, the entire install layer is invalidated.

If you changed only application code (not dependencies), the install layer should be cached and the build should be fast. If it is not:

```bash
# Verify the cache is actually being used:
docker compose build skuel-app --progress=plain 2>&1 | grep -i "cache"

# Force a clean build only if you suspect a corrupt cache:
docker compose build --no-cache skuel-app
```

If `uv.lock` keeps changing between builds (e.g., CI regenerates it), pin it in version control and do not regenerate unless dependencies actually changed.

---

## Prometheus cannot scrape the app metrics

**Symptom:** Grafana shows "no data". Prometheus targets page shows the app as `DOWN`.

Prometheus in `app/docker-compose.yml` scrapes `http://host.docker.internal:5001/metrics` (or `172.17.0.1:5001` on Linux, configured via `extra_hosts`). This only works if the app is reachable on that address.

If the app is running via `uv run` (not in Docker), it is on port 8000, not 5001. Either:
- Run the app in Docker (`docker compose up skuel-app`) so it is on 5001, or
- Update `monitoring/prometheus/prometheus.yml` to scrape port 8000 for local dev.

If the app IS in Docker but Prometheus still can't reach it, check that both containers are on the same Docker network (`skuel-network` in the compose file).
