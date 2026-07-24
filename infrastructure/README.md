# SKUEL Infrastructure Layer

**Purpose**: Persistent infrastructure services that run independently of the SKUEL application

**Location**: `/home/mike/skuel/infrastructure`
**Application**: `/home/mike/skuel/app`
**Last Updated**: 2026-07-24

---

## TL;DR - What is This?

This directory contains **all infrastructure services** that SKUEL depends on, completely separated from application code.

**What runs here:** Neo4j 2026.06.0 (graph database)
**What connects here:** SKUEL application (`/home/mike/skuel/app`)

> **This directory is LOCAL DEVELOPMENT only.** Production does not use anything in here:
> skuel.app runs from a droplet (`app/docker-compose.production.yml` — app + Caddy) against
> **Neo4j AuraDB Free** over `neo4j+s://`. Nothing in `infrastructure/` deploys anywhere.
> See `app/docs/deployment/DO_MIGRATION_GUIDE.md` (droplet stack + runbook) and
> `app/docs/deployment/AURADB_MIGRATION_GUIDE.md` (data migration).

**Quick Start:**
```bash
# Primary workflow: unified compose (Neo4j + App — monitoring opt-in)
cd ~/skuel/app && docker compose up -d

# With monitoring (Prometheus + Grafana):
cd ~/skuel/app && docker compose --profile monitoring up -d

# Alternative: Neo4j only (when running app locally with uv)
cd ~/skuel/infrastructure && docker compose up -d
cd ~/skuel/app && uv run python main.py
```

**Key Benefit:** Infrastructure and application have independent lifecycles - start infrastructure once, restart app hundreds of times without losing data.

---

## Overview

This directory contains all infrastructure services that SKUEL depends on. By separating infrastructure from application code, we achieve:

- ✅ **Clean Separation**: Infrastructure can be managed independently
- ✅ **Independent Lifecycle**: Services stay running while application restarts
- ✅ **Data Isolation**: All persistent data in one location
- ✅ **Easier Backups**: Backup ~/skuel/infrastructure to preserve all application data
- ✅ **Development Workflow**: Start infrastructure once, develop/restart app freely

## Benefits of This Architecture

### Development Workflow

**Start infrastructure once, develop freely:**

```bash
# Terminal 1: Infrastructure (start once, leave running)
cd ~/skuel/infrastructure && docker compose up -d

# Terminal 2: Application (restart as needed)
cd ~/skuel/app && uv run python main.py
# Or use hot reload, debugger, tests, etc.
```

**Advantages:**
- ✅ **Fast iteration** - No Docker rebuild for code changes
- ✅ **Persistent data** - Database survives app crashes/restarts
- ✅ **Independent development** - Work on app without touching infrastructure
- ✅ **Easy debugging** - Direct Python debugger access
- ✅ **Quick testing** - Spin up/down app while data persists

### Production

Production does **not** run this directory's Neo4j — the database side of this separation is
handled by a managed service (AuraDB Free), and the app side by the droplet stack
(`app/docker-compose.production.yml`, deployed via `./dev deploy`). The same lifecycle
principle applies there, just with Neo4j's half owned by Neo4j the company instead of this
compose file.

## Architecture Pattern

```
/home/mike/skuel/infrastructure/          ← Infrastructure services (this directory)
    ├── neo4j/             ← Database data and configuration
    ├── docker-compose.yml ← Infrastructure service definitions
    └── .env               ← Infrastructure credentials

/home/mike/skuel/app/        ← SKUEL application code
    ├── core/              ← Business logic
    ├── adapters/          ← External interfaces
    ├── .env               ← Application configuration + connection details
    └── main.py            ← Application entry point
```

**Connection Flow**:
```
Application (~/skuel/app) → Connects to → Infrastructure (~/skuel/infrastructure)
   Uses environment variables to locate services (NEO4J_URI, etc.)
```

**Key Principle**: Infrastructure and application have **independent lifecycles**
- Infrastructure runs continuously (days/weeks)
- Application restarts frequently (development, deployments)
- Data persists across all app changes

## Currently Running Services

### 1. Neo4j Graph Database

**Status**: ✅ Active
**Container**: `skuel-neo4j`
**Image**: `neo4j:2026.06.0`

**Ports**:
- `7474` - HTTP browser interface (http://localhost:7474)
- `7687` - Bolt protocol for application connections

**Volumes**:
- `./neo4j/data` - Database files (persistent storage)
- `./neo4j/logs` - Neo4j logs
- `./neo4j/plugins` - APOC and other plugins
- `./neo4j/import` - For bulk imports
- `./neo4j/backups` - Database backups

**Configuration**: See `.env` file for credentials and memory settings

**Usage**:
```bash
# Access Neo4j browser
open http://localhost:7474
# Login with: neo4j / <password from .env>
```

## Directory Structure

```
/home/mike/skuel/infrastructure/
├── docker-compose.yml     # Neo4j-only service definitions
├── .env                   # Credentials and configuration
├── README.md              # This file
└── neo4j/                 # Neo4j database directory
    ├── data/              # Graph database storage
    ├── logs/              # Neo4j server logs
    ├── plugins/           # APOC and other plugins
    ├── import/            # CSV/data import directory
    └── backups/           # Database backup storage
```

## How to Use

### Starting Infrastructure

```bash
cd ~/skuel/infrastructure
docker compose up -d
```

**This starts all infrastructure services in detached mode.**

### Checking Status

```bash
cd ~/skuel/infrastructure
docker compose ps
```

Expected output:
```
NAME          IMAGE        COMMAND     SERVICE   STATUS      PORTS
skuel-neo4j   neo4j:2026.06.0   ...         neo4j     Up 2 hours  127.0.0.1:7474->7474/tcp, 127.0.0.1:7687->7687/tcp
```

### Viewing Logs

```bash
# All services
docker compose logs -f

# Neo4j only
docker compose logs -f neo4j

# Last 100 lines
docker compose logs --tail=100 neo4j
```

### Stopping Infrastructure

```bash
cd ~/skuel/infrastructure
docker compose down
```

**Note**: This stops containers but preserves data in volumes.

### Restarting a Service

```bash
cd ~/skuel/infrastructure
docker compose restart neo4j
```

## Application Connection

### How SKUEL Connects to Infrastructure

The SKUEL application connects to infrastructure services via **network protocols**, not Docker links or shared volumes. This allows:
- Running app locally (Python) while infrastructure is in Docker
- Running both in Docker but with independent lifecycles
- Running app in multiple instances pointing to same infrastructure

### Connection Configuration

**Infrastructure exposes services on localhost:**
- Neo4j HTTP: `http://localhost:7474` (browser interface)
- Neo4j Bolt: `bolt://localhost:7687` (application connection)

**Application configures connection in `/home/mike/skuel/app/.env`:**

```bash
# Neo4j Connection (points to ~/skuel/infrastructure services)
NEO4J_URI=neo4j://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<must match ~/skuel/infrastructure/.env>
NEO4J_DATABASE=neo4j
```

### Connection Scenarios

**Scenario 1: Local App + Docker Infrastructure (Recommended for Development)**
```bash
# Infrastructure runs in Docker
cd ~/skuel/infrastructure && docker compose up -d

# Application runs locally
cd ~/skuel/app && uv run python main.py
# App connects to localhost:7687 (Docker port is mapped to host)
```

**Scenario 2: Both in Docker**
```bash
# Infrastructure runs in Docker
cd ~/skuel/infrastructure && docker compose up -d

# Application runs in Docker
cd ~/skuel/app && docker compose up -d
# App connects via host.docker.internal:7687 (Docker → host network)
```

**Scenario 3: Production (does not involve this directory)**
```bash
# Droplet app + Caddy against AuraDB Free — see app/docs/deployment/DO_MIGRATION_GUIDE.md
NEO4J_URI=neo4j+s://<dbid>.databases.neo4j.io
```

### Verifying Connection

**Test from application directory:**
```bash
cd ~/skuel/app
uv run python -c "
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()
driver = GraphDatabase.driver(
    os.getenv('NEO4J_URI'),
    auth=(os.getenv('NEO4J_USERNAME'), os.getenv('NEO4J_PASSWORD'))
)
driver.verify_connectivity()
print('✅ Connected to infrastructure!')
driver.close()
"
```

**Important Notes:**
- ✅ Application and infrastructure passwords **must match**
- ✅ Infrastructure must be running before starting application
- ✅ Connection is via network (TCP), not Docker volumes
- ✅ Multiple app instances can connect to same infrastructure

## Development Workflow

**Recommended workflow for development:**

1. **Start infrastructure** (once, stays running):
   ```bash
   cd ~/skuel/infrastructure && docker compose up -d
   ```

2. **Develop application** (restart freely):
   ```bash
   cd ~/skuel/app
   uv run python main.py
   # Or use ./restart_server.sh
   ```

3. **Infrastructure keeps running** while you:
   - Edit code
   - Restart application
   - Run tests
   - Switch branches

4. **Stop infrastructure** only when done for the day:
   ```bash
   cd ~/skuel/infrastructure && docker compose down
   ```

## Environment Variables

### Infrastructure (.env in this directory)

```bash
# Neo4j Authentication
NEO4J_AUTH=neo4j/<password>

# Neo4j Memory Settings
NEO4J_HEAP_INIT=1G
NEO4J_HEAP_MAX=1500M
NEO4J_PAGECACHE=2G
```

### Application Connection (.env in ~/skuel/app)

```bash
# Connection to infrastructure
NEO4J_URI=neo4j://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<same as infra .env>
NEO4J_DATABASE=neo4j

# Application credentials
OPENAI_API_KEY=<your-key>
DEEPGRAM_API_KEY=<your-key>
```

## Data Management

### Backing Up Neo4j

**Manual backup**:
```bash
cd ~/skuel/infrastructure
# The database must be offline for neo4j-admin dump; --to-path is a directory.
docker compose stop neo4j
docker compose run --rm neo4j neo4j-admin database dump neo4j --to-path=/backups
docker compose start neo4j
```

Backup file will be in `./neo4j/backups/neo4j.dump`

**Automated backup** (recommended - create script):
```bash
#!/bin/bash
# ~/skuel/infrastructure/scripts/backup-neo4j.sh
# NOTE: the database must be offline for neo4j-admin dump, and --to-path is a
# DIRECTORY — the tool writes <database>.dump into it.
DATE=$(date +%Y%m%d_%H%M%S)
cd ~/skuel/infrastructure
docker compose stop neo4j
docker compose run --rm neo4j neo4j-admin database dump neo4j --to-path=/backups
docker compose start neo4j
mv neo4j/backups/neo4j.dump "neo4j/backups/neo4j_${DATE}.dump"
echo "Backup created: neo4j_${DATE}.dump"
```

### Restoring from Backup

```bash
cd ~/skuel/infrastructure
# Stop neo4j (exec won't work on a stopped container — use `run --rm` below)
docker compose stop neo4j

# --from-path is a directory; the loader expects <database>.dump inside it
cp neo4j/backups/neo4j_20260102_120000.dump neo4j/backups/neo4j.dump
docker compose run --rm neo4j neo4j-admin database load neo4j \
    --from-path=/backups --overwrite-destination=true
rm neo4j/backups/neo4j.dump

# Start neo4j
docker compose start neo4j
```

### Clearing All Data

**⚠️ Warning: This deletes everything!**

```bash
cd ~/skuel/infrastructure
docker compose down -v  # -v removes volumes
rm -rf neo4j/data/*     # Clear data directory
docker compose up -d    # Start fresh
```

## Monitoring

### Neo4j Browser

- **URL**: http://localhost:7474
- **Username**: neo4j
- **Password**: From `.env` file

**Useful Queries**:
```cypher
// Count all nodes
MATCH (n) RETURN count(n)

// Count by type
MATCH (n)
RETURN labels(n) as type, count(n) as count
ORDER BY count DESC

// Database size
CALL apoc.meta.stats()
```

### Container Health

```bash
# Check if neo4j is healthy
docker inspect skuel-neo4j --format='{{.State.Health.Status}}'

# Expected output: "healthy"
```

### Resource Usage

```bash
# Container stats
docker stats skuel-neo4j

# Shows: CPU%, MEM USAGE/LIMIT, MEM%, NET I/O, BLOCK I/O
```

## What Runs in ~/skuel/infrastructure

### Currently Active Services

| Service | Status | Purpose | Ports |
|---------|--------|---------|-------|
| **Neo4j 2026.06.0** | ✅ Running | Graph database (primary data store) | 7474 (HTTP), 7687 (Bolt) |

**Total Active Services:** 1
**Total Data Volume:** All in `./neo4j/data/`

### Other Services

Prometheus + Grafana (monitoring) and Firefly III + MariaDB (finance, ADR-052) live in
`app/docker-compose.yml` behind the `monitoring` / `finance` profiles — not here. No compose
file runs Redis, Ollama, or nginx: the former "pre-wired future services" blocks in
`docker-compose.production.yml` were deleted when that file was rewritten to the real droplet
stack (app + Caddy, 2026-07-24). Per One Path Forward, a service enters a compose file when it
is actually adopted, not speculatively. (The unused `app/k8s-manifests.yml` example still
sketches Redis/nginx resources — a stale artifact from the same era, not something any
deployment path uses.)

#### Active Infrastructure Plugins

| Plugin | Status | Scope | Purpose |
|--------|--------|-------|---------|
| **APOC (core)** | ✅ Active | `apoc.meta.*` only | Schema introspection (`apoc.meta.schema`) |

**Note:** Embeddings are generated Python-side via the OpenAI Embeddings API (ADR-068) and
written into Neo4j vector indexes — no Neo4j GenAI plugin is loaded in any environment.

**APOC Scope Policy:**
- Only `apoc-core.jar` is loaded (not `apoc-all`) — dangerous procedures (`cypher.run`, `export.*`, `load.*`) are not in the JAR at all
- Allowlist further restricts to `apoc.meta.*` — a second layer of defence
- SKUEL001 linter rule still bans APOC in domain services (`core/services/`) — pure Cypher remains the rule for all application queries
- See `/home/mike/skuel/app/docs/patterns/CYPHER_VS_APOC_STRATEGY.md` for the full strategy

### Adding Services to ~/skuel/infrastructure

**Process:**
1. Define service in `~/skuel/infrastructure/docker-compose.yml`
2. Add credentials to `~/skuel/infrastructure/.env`
3. Document in this README
4. Update application connection in `/home/mike/skuel/app/.env`
5. Test connectivity

**Philosophy:** "Infrastructure should be boring and reliable" - Only add services when production demands them, not speculatively.

## Troubleshooting

### Neo4j Won't Start

**Check logs**:
```bash
docker compose logs neo4j
```

**Common issues**:
- Port 7474 or 7687 already in use
- Insufficient memory (check Docker Desktop settings)
- Corrupted database (restore from backup)

### Application Can't Connect

**Verify Neo4j is running**:
```bash
docker ps | grep neo4j
```

**Test connection**:
```bash
# From application directory
cd ~/skuel/app
uv run python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('neo4j://localhost:7687', auth=('neo4j', 'password'))
driver.verify_connectivity()
print('✅ Connected!')
driver.close()
"
```

**Check password match**:
```bash
# Compare passwords
cat ~/skuel/infrastructure/.env | grep NEO4J_AUTH
cat ~/skuel/app/.env | grep NEO4J_PASSWORD
# These must match!
```

### Port Already in Use

**Find what's using the port**:
```bash
lsof -i :7474  # HTTP port
lsof -i :7687  # Bolt port
```

**Kill the process or change port in .env**

### Out of Disk Space

**Check Docker space**:
```bash
docker system df
```

**Clean up unused data**:
```bash
docker system prune -a  # Remove unused containers, images, networks
```

## Upgrading Neo4j

**Version policy (ADR-067 § 3a):** SKUEL runs the **latest monthly** of Neo4j's
**calendar-versioned** line (`YYYY.MM`) — today **`neo4j:2026.06.0`**. Neo4j hotfixes each monthly
release only until the next monthly ships, so we track the *current* monthly rather than soaking on an
older one (which would already be EOL for fixes). When a new monthly lands, bump to it; take its
`.1`/`.2` hotfixes as they appear. Pinning is deliberate and exact (no floating `latest`/major/minor
tags) so every environment is reproducible. The long-support, no-treadmill alternative is the 5.26
LTS — a separate, ADR-worthy call.

> **Direction matters.** Neo4j auto-migrates the store *forward*, so moving to a newer monthly
> (e.g. `2026.06.0` → `2026.07.0`) is an in-place upgrade — back up, swap the tag, restart.
> It does **not** support *downgrades*: a store written by a newer server will not open on an older
> one, so rolling back means restoring the pre-upgrade backup, not just re-pinning the old tag.

**To move to a newer calendar release**:

1. **Backup first**:
   ```bash
   cd ~/skuel/infrastructure
   docker compose exec neo4j neo4j-admin database dump neo4j --to-path=/backups
   ```

2. **Update docker-compose.yml**:
   ```yaml
   services:
     neo4j:
       image: neo4j:2026.06.0  # current pinned calendar release (ADR-067)
   ```

3. **Restart with new image**:
   ```bash
   docker compose down
   docker compose pull
   docker compose up -d
   ```

4. **Verify**:
   ```bash
   docker compose logs neo4j
   ```

## Configuration Settings (Neo4j 5.26+)

SKUEL uses modern Neo4j 5.26+ configuration syntax:

| Setting Type | Modern Prefix | Old Prefix (deprecated) |
|-------------|---------------|-------------------------|
| Query cache | `server.memory.*` | `dbms.query_cache_size` |
| Query logging | `db.logs.query.*` | `dbms.logs.query.*` |
| Log rotation | Auto-managed | `dbms.logs.query.rotation.*` (removed) |

**Note**: Settings with deprecated prefixes still work but generate warnings.
Our configuration uses modernized syntax to eliminate deprecation warnings.

**Configuration Mapping**:
```yaml
# Query Cache (parameterized query caching)
# Setting: server.memory.query_cache.per_db_cache_num_entries
NEO4J_server_memory_query__cache_per__db__cache__num__entries: "2000"

# Cypher Planner (cost-based optimization)
# Setting: dbms.cypher.planner
NEO4J_dbms_cypher_planner: COST

# Transaction Timeout (for large queries)
# Setting: db.transaction.timeout
NEO4J_db_transaction_timeout: 600s

# Query Logging (slow query detection)
# Setting: db.logs.query.enabled
NEO4J_db_logs_query_enabled: INFO              # Values: OFF, INFO, VERBOSE
NEO4J_db_logs_query_threshold: 1s              # Log queries slower than 1 second
NEO4J_db_logs_query_parameter__logging__enabled: "true"  # Include query parameters in logs
```

**Environment Variable Naming Convention**:
- Dots (`.`) in setting names → single underscore (`_`) in environment variable
- Underscores (`_`) in setting names → double underscore (`__`) in environment variable
- Prefix all settings with `NEO4J_`

Example: `server.memory.query_cache.per_db_cache_num_entries` → `NEO4J_server_memory_query__cache_per__db__cache__num__entries`

## Security Considerations

### Local Development (Current Setup)

- Ports bound to `127.0.0.1` (localhost only) - ✅ Secure
- Password in `.env` file - ✅ Acceptable for local dev
- No SSL/TLS - ✅ Acceptable for local dev

### Production

Production Neo4j is AuraDB Free — TLS, auth, and infrastructure hardening are the managed
service's job; SKUEL's side (encrypted-URI boot guard, secrets handling, headers, rate
limits) is covered in `app/docs/deployment/DO_MIGRATION_GUIDE.md` § Hardening checklist.

## Related Documentation

- **Application Code**: `/home/mike/skuel/app/`
- **Droplet Deployment Guide**: `/home/mike/skuel/app/docs/deployment/DO_MIGRATION_GUIDE.md`
- **AuraDB Migration Guide**: `/home/mike/skuel/app/docs/deployment/AURADB_MIGRATION_GUIDE.md`
- **Application Config**: `/home/mike/skuel/app/core/config/unified_config.py`
- **Neo4j Documentation**: https://neo4j.com/docs/

## Quick Command Reference

```bash
# Start infrastructure
cd ~/skuel/infrastructure && docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f neo4j

# Restart Neo4j
docker compose restart neo4j

# Stop infrastructure
docker compose down

# Backup database (stop first — dump requires the database offline)
docker compose stop neo4j && docker compose run --rm neo4j \
  neo4j-admin database dump neo4j --to-path=/backups && docker compose start neo4j

# Access Neo4j browser
open http://localhost:7474

# Check Neo4j health
curl http://localhost:7474
```

---

**Philosophy**: "Infrastructure should be boring and reliable"

This ~/skuel/infrastructure directory exists to make SKUEL's infrastructure predictable, manageable, and separate from application development. It should "just work" so you can focus on building features.
