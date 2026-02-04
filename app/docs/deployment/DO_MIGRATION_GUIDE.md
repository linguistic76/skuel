---
title: DigitalOcean Migration Guide
related_skills:
  - neo4j-cypher-patterns
  - neo4j-genai-plugin
---
# DigitalOcean Migration Guide

**Last Updated:** 2026-02-05
**Migration Type:** Infrastructure Change (Local Docker → DigitalOcean)
**Position in deployment roadmap:** Intermediate step between local development and AuraDB production

---

## Where This Fits in the Deployment Roadmap

SKUEL's infrastructure evolves in three stages. This guide covers Stage 2.

```
Stage 1 (Current)          Stage 2 (This Guide)           Stage 3 (End Goal)
─────────────────          ────────────────────           ──────────────────
Local Docker Neo4j    →    DO Droplet Neo4j          →    AuraDB
Local app (poetry)         DO App Platform (app)          DO App Platform (app)
                                                          See: AURADB_MIGRATION_GUIDE.md
```

Stage 2 is the production-validation step. It proves the app works in a cloud environment, establishes operational habits (backups, monitoring, networking security), and reduces risk when Stage 3 swaps Neo4j for AuraDB — which is a single `.env` change at that point.

---

## Architecture Decision: Why Two Services, Not One

Neo4j on App Platform is not viable. App Platform is built for stateless workloads: it provides no guarantees on local disk persistence, no fine-grained memory tuning controls, and no stable network identity between restarts. Neo4j is a stateful database that requires all three.

The architecture for Stage 2 is therefore:

```
┌─────────────────────────────────────────────────────┐
│  DigitalOcean                                       │
│                                                     │
│  App Platform                   Droplet             │
│  ┌─────────────┐               ┌───────────────┐   │
│  │  SKUEL App  │───Bolt:7687──►│  Neo4j Docker │   │
│  │  (FastHTML) │               │  (stateful)   │   │
│  │  Port 5001  │               │  Port 7687    │   │
│  └─────────────┘               └───────────────┘   │
│  Managed PaaS                  Self-managed VM      │
│  Auto-deploy from git          Persistent volumes   │
│  Built-in secrets              Memory-tunable       │
│  Health checks                 Firewall control     │
└─────────────────────────────────────────────────────┘
```

**App Platform** is the right home for SKUEL: it's a stateless web server, `Dockerfile.production` already exists, and App Platform handles deploys, health checks, and secrets natively.

**Droplet** is the right home for Neo4j: identical Docker setup to local development, full volume and memory control, and a stable network identity that App Platform can reach.

---

## Networking: How App Platform Reaches the Droplet

App Platform services do not attach to user-managed VPCs, so private networking between App Platform and a Droplet is not available. The connection goes over the public network. This means:

1. Neo4j Bolt (port 7687) must be exposed on the Droplet's public IP.
2. The Droplet firewall must restrict port 7687 to known source IPs only.
3. The connection string uses the Droplet's public IP: `bolt://<droplet-ip>:7687`.

DigitalOcean App Platform publishes its outbound IP ranges in the [App Platform documentation](https://docs.digitalocean.com/products/app-platform/). Add those CIDRs to the Droplet's firewall inbound rule for TCP 7687. No other port (7474 HTTP browser) needs to be open in production — Bolt is sufficient.

If the outbound IPs change or are not stable, an alternative is to place both the app and Neo4j on a single Droplet behind Docker Compose. This trades App Platform's managed deploys for simpler networking. See the "Single-Droplet Alternative" section at the end of this guide.

---

## Prerequisites

- [ ] DigitalOcean account created
- [ ] SSH key added to your DO account
- [ ] Current Neo4j data backed up (see Phase 1)
- [ ] `Dockerfile.production` reviewed (note: currently targets Python 3.11; align with `pyproject.toml` if it requires 3.12+)
- [ ] OpenAI API key available (for GenAI plugin)
- [ ] Domain name (optional for this stage, required for TLS in production)

---

## Phase 1: Backup Local Neo4j

Back up before touching anything. This is the same procedure used in the AuraDB guide.

```bash
cd ~/skuel/infrastructure

# Stop the container cleanly
docker compose stop neo4j

# Dump the database
docker compose run --rm neo4j \
  neo4j-admin database dump neo4j \
  --to-path=/backups/backup_$(date +%Y%m%d_%H%M%S).dump

# Copy to host
docker cp skuel-neo4j:/backups/backup_*.dump ./neo4j/backups/

# Restart
docker compose start neo4j
```

Verify the backup file exists and has non-zero size before proceeding.

---

## Phase 2: Provision the Neo4j Droplet

### 2.1 Create the Droplet

Neo4j's memory config in `infrastructure/.env` is:
- Heap: 1G init / 1.5G max
- Page cache: 2G

That totals ~3.5G for Neo4j alone. The OS and Docker runtime need headroom on top. **Choose the 8GB RAM Droplet** ($48/month, 2 vCPU). A 4GB Droplet will work under light load but will pressure the page cache.

| Setting | Value |
|---------|-------|
| Image | Ubuntu 24.04 LTS |
| Size | 2 vCPU, 8 GB RAM ($48/mo) |
| Region | Closest to your users |
| Hostname | `skuel-neo4j` |
| SSH Key | Your DO SSH key |
| Firewall | See 2.2 |

### 2.2 Configure the Firewall

Create a firewall rule set for the Droplet. Start locked down, then open only what is needed:

| Type | Protocol | Port | Source | Purpose |
|------|----------|------|--------|---------|
| Inbound | TCP | 22 | Your IP only | SSH management |
| Inbound | TCP | 7687 | App Platform outbound CIDRs | Bolt (application traffic) |
| Outbound | TCP | All | All | Allows Neo4j to reach OpenAI for GenAI |

Do **not** open port 7474 (Neo4j Browser HTTP). If you need to inspect the database during setup, SSH-tunnel it locally:

```bash
ssh -L 7474:localhost:7474 -L 7687:localhost:7687 root@<droplet-ip>
# Then open http://localhost:7474 on your machine
```

### 2.3 Install Docker

```bash
ssh root@<droplet-ip>

# Standard Docker install for Ubuntu 24.04
curl -fsSL https://get.docker.com | sh

# Verify
docker --version
docker compose version
```

### 2.4 Deploy the Neo4j Container

The Droplet's Neo4j setup is a direct lift of `infrastructure/docker-compose.yml`. The only change is that port bindings move from `127.0.0.1:` (localhost-only) to `0.0.0.0:` for Bolt, because App Platform needs to reach it from outside the machine. HTTP stays on localhost since only the SSH tunnel uses it.

```bash
mkdir -p /opt/skuel-neo4j
cd /opt/skuel-neo4j

# Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
services:
  neo4j:
    image: neo4j:2025.12.1
    container_name: skuel-neo4j
    restart: unless-stopped
    ports:
      - "0.0.0.0:7687:7687"       # Bolt — open for App Platform
      - "127.0.0.1:7474:7474"     # HTTP — localhost only (SSH tunnel)
    environment:
      NEO4J_PLUGINS: '["apoc", "genai"]'
      NEO4J_AUTH: "${NEO4J_AUTH}"
      OPENAI_API_KEY: "${NEO4J_OPENAI_API_KEY}"
      NEO4J_server_memory_heap_initial__size: "${NEO4J_HEAP_INIT}"
      NEO4J_server_memory_heap_max__size: "${NEO4J_HEAP_MAX}"
      NEO4J_server_memory_pagecache_size: "${NEO4J_PAGECACHE}"
      NEO4J_db_transaction_timeout: 600s
      NEO4J_server_memory_query__cache_per__db__cache__num__entries: "2000"
      NEO4J_dbms_cypher_planner: COST
      NEO4J_db_logs_query_enabled: INFO
      NEO4J_db_logs_query_threshold: 1s
      NEO4J_db_logs_query_parameter__logging__enabled: "true"
      NEO4J_dbms_security_procedures_unrestricted: "genai.*,apoc.meta.*"
      NEO4J_dbms_security_procedures_allowlist: "genai.*,apoc.meta.*"
      NEO4J_server_bolt_enabled: "true"
      NEO4J_server_bolt_listen__address: 0.0.0.0:7687
      NEO4J_server_http_enabled: "true"
      NEO4J_server_http_listen__address: 0.0.0.0:7474
    volumes:
      - ./data:/data
      - ./logs:/logs
      - ./conf:/conf
      - ./plugins:/plugins
      - ./import:/import
      - ./backups:/backups
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:7474"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 40s
EOF

# Create .env with your actual values
cat > .env << 'EOF'
NEO4J_AUTH=neo4j/<your-password>
NEO4J_OPENAI_API_KEY=sk-proj-...
NEO4J_HEAP_INIT=1G
NEO4J_HEAP_MAX=1500M
NEO4J_PAGECACHE=2G
EOF
```

**Do not commit the `.env` file.** It contains credentials.

```bash
docker compose up -d
docker compose logs -f neo4j   # Wait for "Neo4j started" message
```

### 2.5 Restore Data

Copy the backup from Phase 1 to the Droplet, then restore:

```bash
# From your local machine:
scp ./neo4j/backups/backup_*.dump root@<droplet-ip>:/opt/skuel-neo4j/backups/

# On the Droplet:
cd /opt/skuel-neo4j
docker compose stop neo4j

docker compose run --rm neo4j \
  neo4j-admin database load neo4j \
  --from-path=/backups/backup_YYYYMMDD_HHMMSS.dump \
  --force

docker compose start neo4j
```

### 2.6 Verify the Droplet Neo4j

SSH into the Droplet and test via the Bolt driver:

```bash
docker exec skuel-neo4j cypher-shell -u neo4j -p <your-password> \
  "RETURN count(*) AS nodes"
```

Compare the node count to the pre-backup count from Phase 1.

---

## Phase 3: Deploy the App on App Platform

### 3.1 Review Dockerfile.production

`Dockerfile.production` exists at the repo root. Before deploying, verify:

- The Python version matches `pyproject.toml` (`python:3.12-slim`). If `pyproject.toml` is updated to require a newer version, bump the base image in both builder and production stages.
- The `CMD` runs `main.py` on port 5001. Do not change the entry point or port — health checks and port mappings depend on both.
- The health check hits `/health` on port 5001. Confirm this endpoint exists in the app.

### 3.2 Create the App Platform App

In the DigitalOcean console:

1. **Apps** → **Create App**
2. Source: Connect your Git repository (GitHub, GitLab, etc.)
3. App Platform will auto-detect `Dockerfile.production`. If not, specify `dockerfile_path: Dockerfile.production` in the app spec.
4. Component type: **Web Service**
5. Name: `skuel-app`
6. Instance size: Start with **Basic** ($5/month, 512MB). Scale up if the app needs more.

### 3.3 Configure Environment Variables

These are the secrets and config the app needs. Set them in the App Platform UI under **Environment Variables**, marked as **Secret** where indicated.

| Variable | Value | Secret? |
|----------|-------|---------|
| `NEO4J_URI` | `bolt://<droplet-ip>:7687` | Yes |
| `NEO4J_USERNAME` | `neo4j` | No |
| `NEO4J_PASSWORD` | `<your-neo4j-password>` | Yes |
| `OPENAI_API_KEY` | `sk-proj-...` | Yes |
| `DEEPGRAM_API_KEY` | `<your-key>` | Yes |
| `APP_HOST` | `0.0.0.0` | No |
| `APP_PORT` | `5001` | No |
| `GENAI_ENABLED` | `true` | No |
| `GENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | No |
| `GENAI_EMBEDDING_DIMENSION` | `1536` | No |
| `LOG_LEVEL` | `INFO` | No |

App Platform encrypts Secret-typed variables. They are not visible in plaintext after initial entry.

### 3.4 Deploy and Verify

App Platform auto-deploys on push to the configured branch. After the first deploy:

1. Check the deploy logs in the App Platform UI for startup errors.
2. The app should log successful Neo4j connection within the first few seconds.
3. Hit the App Platform-assigned URL (e.g., `https://skuel-app-xxxxx.ondigitalocean.app`) and confirm the UI loads.
4. Run a search or create an entity to confirm the full read/write path works end-to-end.

---

## Phase 4: Verify GenAI and Embeddings

The GenAI plugin on the Droplet uses per-query token passing (same as local Docker). The app code already handles this — it is environment-agnostic. Verify:

```bash
# SSH tunnel to the Droplet, then run from your local machine:
ssh -L 7687:localhost:7687 root@<droplet-ip> &

poetry run python -c "
import asyncio, os
from neo4j import AsyncGraphDatabase

async def test():
    driver = AsyncGraphDatabase.driver(
        'bolt://localhost:7687',
        auth=('neo4j', os.getenv('NEO4J_PASSWORD'))
    )
    result = await driver.execute_query('''
        RETURN genai.vector.encode(\$text, \"OpenAI\", {
            token: \$key,
            model: \"text-embedding-3-small\",
            dimensions: 1536
        }) AS embedding
    ''', {'text': 'test', 'key': os.getenv('OPENAI_API_KEY')})
    print(f'GenAI working. Embedding dimensions: {len(result[0][0][\"embedding\"])}')
    await driver.close()

asyncio.run(test())
"
```

Expected output: `GenAI working. Embedding dimensions: 1536`

---

## Phase 5: Operational Checklist

Once Stage 2 is running, these are the operational responsibilities that did not exist in local development. Getting comfortable with them before moving to AuraDB is the point of this stage.

### Backups

Neo4j on the Droplet has no automatic backups. Set up a cron job:

```bash
# On the Droplet, add to crontab (crontab -e):
0 3 * * * cd /opt/skuel-neo4j && docker compose run --rm neo4j \
  neo4j-admin database dump neo4j \
  --to-path=/backups/backup_$(date +%Y%m%d_%H%M%S).dump

# Rotate old backups (keep 7 days):
0 4 * * * find /opt/skuel-neo4j/backups -name "backup_*.dump" -mtime +7 -delete
```

Consider pushing backups to DigitalOcean Spaces for off-Droplet durability.

### Monitoring

SKUEL already ships Prometheus + Grafana (see `docker-compose.yml` in the app). On the Droplet, you can run a lightweight Neo4j metrics exporter or simply monitor via the health check endpoint. At minimum, set up a simple uptime monitor (e.g., UptimeRobot, or DO's built-in health checks) on the Droplet.

### Security

- Rotate the Neo4j password and OpenAI API key on a regular cadence.
- Keep the Droplet's OS and Docker updated: `apt update && apt upgrade -y` monthly.
- The firewall rule for port 7687 should be the only inbound rule besides SSH.

### Updates

When `infrastructure/docker-compose.yml` changes Neo4j version or configuration locally, apply the same change on the Droplet:

```bash
cd /opt/skuel-neo4j
# Update docker-compose.yml to match infrastructure/docker-compose.yml
# (only the port binding difference: 0.0.0.0 vs 127.0.0.1 for Bolt)
docker compose pull
docker compose up -d
```

---

## Phase 6: Preparing for AuraDB (Stage 3)

Stage 2 is explicitly a stepping stone. When you are ready to move to AuraDB, the transition is minimal:

1. **App Platform stays.** No changes to the app deployment.
2. **Neo4j connection string changes.** In App Platform environment variables, update `NEO4J_URI` from `bolt://<droplet-ip>:7687` to `neo4j+s://<auradb-host>`. Update `NEO4J_PASSWORD` to the AuraDB credential.
3. **GenAI token passing changes.** AuraDB configures the OpenAI API key at the database level. The app code handles this automatically — the `token` parameter is simply not needed when it is not present in the environment.
4. **Droplet is decommissioned** after data is migrated and verified in AuraDB.

Follow `AURADB_MIGRATION_GUIDE.md` for the full procedure. The data backup and restore steps in that guide are identical to what you already practiced in Phases 1 and 2.5 here.

---

## Cost Summary

| Component | Service | Monthly Cost | Notes |
|-----------|---------|--------------|-------|
| SKUEL App | App Platform (Basic) | $5 | Scale to $12 (Pro) if needed |
| Neo4j | Droplet (8GB) | $48 | Includes 160GB SSD |
| **Total** | | **$53** | Before OpenAI/Deepgram API costs |

For comparison: AuraDB Professional alone is ~$65/month. Stage 2 is slightly cheaper and provides hands-on operational experience before committing to the managed service.

---

## Single-Droplet Alternative

If the App Platform → Droplet networking proves problematic (e.g., outbound IPs are not stable, firewall rules are difficult to maintain), everything can run on a single Droplet:

```
┌───────────────────────────┐
│  Droplet (8GB)            │
│                           │
│  ┌─────────┐ ┌─────────┐  │
│  │ SKUEL   │ │ Neo4j   │  │
│  │ App     │ │ Docker  │  │
│  │ :5001   │ │ :7687   │  │
│  └─────────┘ └─────────┘  │
│  localhost networking      │
└───────────────────────────┘
```

In this layout:
- `NEO4J_URI=bolt://localhost:7687` (same as local development)
- Both services run via a single `docker-compose.yml` that merges the app and Neo4j definitions
- A reverse proxy (nginx or Caddy) handles TLS termination for the app
- The tradeoff: you lose App Platform's auto-deploy and managed secrets, but networking is trivial

This layout still validates cloud deployment and prepares for AuraDB. The AuraDB migration from here is identical: swap the connection string, decommission Neo4j.

---

## Troubleshooting

### "Connection refused" from App Platform to Droplet

1. Confirm the Droplet firewall allows TCP 7687 from the App Platform outbound CIDRs.
2. Confirm Neo4j is running: `docker ps` on the Droplet shows the container as `Up`.
3. Confirm Bolt is bound to `0.0.0.0:7687`, not `127.0.0.1:7687`.
4. Test from outside: `nc -zv <droplet-ip> 7687` from any machine that is not the Droplet.

### "GenAI plugin not available" on the Droplet

The GenAI plugin takes 60-90 seconds to initialize on first container start. If the app starts before the plugin is ready, embeddings will fail silently and fall back to keyword search. Wait for the Neo4j health check to pass, then restart the app deployment in App Platform.

### App Platform deploy fails

Check the deploy logs. Common causes:
- `Dockerfile.production` Python version mismatch with `pyproject.toml`
- Missing `poetry.lock` in the build context (ensure it is committed to git)
- Health check failing: `/health` endpoint must return 200 within the configured timeout

### Data loss after Droplet restart

The volumes in `docker-compose.yml` map to `/opt/skuel-neo4j/data` on the host. As long as the Droplet's block storage is not destroyed, data survives restarts. Verify with `docker compose logs neo4j | grep "Neo4j started"` — it should not log a fresh database message.

---

## Related Documentation

- [AuraDB Migration Guide](./AURADB_MIGRATION_GUIDE.md) — Stage 3: the end goal
- [Neo4j Setup Migration Summary](./NEO4J_SETUP_MIGRATION_SUMMARY.md) — history of the Docker ↔ AuraDB doc split
- [GenAI Setup](../development/GENAI_SETUP.md) — local Docker GenAI configuration (reference for Droplet setup)
- [Neo4j Database Architecture](../architecture/NEO4J_DATABASE_ARCHITECTURE.md) — query patterns and schema

---

**Last Updated:** 2026-02-05
**Maintained By:** SKUEL Core Team
