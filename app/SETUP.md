# SKUEL Setup Guide

**Last Updated:** 2026-01-02
**Infrastructure Version:** Neo4j 5.26 (Consolidated)

---

## Architecture Overview

SKUEL uses a **separated infrastructure pattern** where infrastructure services run independently from application code:

```
/home/mike/skuel/infrastructure/          ← Infrastructure (Neo4j, future services)
/home/mike/skuel/app/        ← SKUEL application code
```

**Benefits:**
- ✅ Infrastructure runs independently (survives app restarts)
- ✅ Single source of truth for infrastructure config
- ✅ Clean separation of concerns
- ✅ Easier backups (backup ~/skuel/infrastructure = backup all data)
- ✅ Production-ready Neo4j 5.26+ configuration

---

## Prerequisites

1. **Python 3.11+** with Poetry installed
2. **Docker** and Docker Compose
3. **Git** (for cloning/version control)

---

## Quick Start (Local Development)

### 1. Start Infrastructure

```bash
cd ~/skuel/infrastructure
docker compose up -d
```

This starts Neo4j 5.26 with:
- HTTP interface: http://localhost:7474
- Bolt connection: bolt://localhost:7687
- Production-ready memory tuning
- Zero deprecation warnings

**Verify Neo4j is healthy:**
```bash
docker compose ps
# Expected: "healthy" status
```

### 2. Configure Application

Create `/home/mike/skuel/app/.env`:

```bash
# Neo4j Connection (connects to ~/skuel/infrastructure instance)
NEO4J_URI=neo4j://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<password from ~/skuel/infrastructure/.env>
NEO4J_DATABASE=neo4j

# AI Service API Keys
OPENAI_API_KEY=<your-openai-key>
DEEPGRAM_API_KEY=<your-deepgram-key>

# Application Settings
APP_HOST=0.0.0.0
APP_PORT=8000
APP_DEBUG=false
LOG_LEVEL=INFO
```

**Important:** `NEO4J_PASSWORD` must match the password in `/home/mike/skuel/infrastructure/.env`

### 3. Install Dependencies

```bash
cd ~/skuel/app
uv sync
```

### 4. Run Application

**Option A: Local Python (Recommended for development)**
```bash
cd ~/skuel/app
uv run python main.py
```

**Option B: Dockerized Application**
```bash
cd ~/skuel/app
docker compose up -d
```

### 5. Access SKUEL

- **Application:** http://localhost:8000
- **Neo4j Browser:** http://localhost:7474

---

## Infrastructure Configuration

### Neo4j Memory Settings

Configure in `/home/mike/skuel/infrastructure/.env`:

```bash
NEO4J_AUTH=neo4j/<your-password>
NEO4J_HEAP_INIT=1G
NEO4J_HEAP_MAX=1500M
NEO4J_PAGECACHE=2G
```

**Tuning Guidelines:**
- **Heap:** 1-4GB (for Java operations)
- **Page Cache:** 50% of system RAM (for graph traversal)
- **Total Neo4j Memory:** Heap + Page Cache + ~1GB overhead

Example for 16GB system:
```bash
NEO4J_HEAP_INIT=2G
NEO4J_HEAP_MAX=4G
NEO4J_PAGECACHE=8G
```

### Neo4j 5.26 Modern Configuration

The infrastructure uses Neo4j 5.26+ configuration syntax (zero deprecation warnings):

| Setting | Environment Variable | Purpose |
|---------|---------------------|---------|
| Query cache | `NEO4J_server_memory_query__cache_per__db__cache__num__entries` | Parameterized query caching |
| Cypher planner | `NEO4J_dbms_cypher_planner` | Cost-based optimization |
| Transaction timeout | `NEO4J_db_transaction_timeout` | Large query timeout (600s) |
| Query logging | `NEO4J_db_logs_query_enabled` | Slow query detection (INFO) |

See `/home/mike/skuel/infrastructure/README.md` for complete configuration reference.

---

## Development Workflows

### Recommended: Infrastructure + Local App

**Best for active development:**

```bash
# Terminal 1: Infrastructure (start once, leave running)
cd ~/skuel/infrastructure && docker compose up -d

# Terminal 2: Application (restart as needed)
cd ~/skuel/app && uv run python main.py
```

**Benefits:**
- Fast iteration (no Docker rebuild for code changes)
- Direct access to Python debugger
- Instant code reload with hot reload tools
- Infrastructure persists between app restarts

### Alternative: Full Docker Stack

**Best for testing containerized deployment:**

```bash
cd ~/skuel/infrastructure && docker compose up -d     # Start Neo4j
cd ~/skuel/app && docker compose up -d   # Start app in Docker
```

**Benefits:**
- Tests production-like environment
- Validates Dockerfile and dependencies
- Useful for CI/CD pipeline testing

### Production: Consolidated Stack

**For production deployment:**

```bash
cd ~/skuel/app
docker compose -f docker-compose.production.yml up -d
```

This includes all services (Neo4j, app, optional future services like Redis, Ollama, etc.)

---

## Infrastructure Management

### Check Status

```bash
cd ~/skuel/infrastructure
docker compose ps
```

### View Logs

```bash
# All services
docker compose logs -f

# Neo4j only
docker compose logs -f neo4j

# Last 100 lines
docker compose logs --tail=100 neo4j
```

### Restart Services

```bash
# Restart Neo4j
docker compose restart neo4j

# Restart all
docker compose restart
```

### Stop Infrastructure

```bash
cd ~/skuel/infrastructure
docker compose down  # Stops containers, preserves data
```

### Complete Cleanup (⚠️ Deletes all data!)

```bash
cd ~/skuel/infrastructure
docker compose down -v  # Removes volumes
rm -rf neo4j/data/*     # Clear data directory
```

---

## Database Management

### Backup Neo4j

```bash
cd ~/skuel/infrastructure
docker compose exec neo4j neo4j-admin database dump neo4j --to-path=/backups
```

Backup file saved to: `/home/mike/skuel/infrastructure/neo4j/backups/`

### Restore from Backup

```bash
cd ~/skuel/infrastructure
docker compose stop neo4j
docker compose exec neo4j neo4j-admin database load neo4j \
    --from-path=/backups/<backup-file>.dump --overwrite-destination=true
docker compose start neo4j
```

### Clear Database (Keep Structure)

```bash
cd ~/skuel/app
uv run python scripts/clear_neo4j.py reset
# Type: DELETE EVERYTHING
```

This clears data, constraints, and indexes.

---

## Troubleshooting

### Neo4j Won't Start

**Check logs:**
```bash
cd ~/skuel/infrastructure
docker compose logs neo4j
```

**Common issues:**
- Port 7474 or 7687 already in use
- Insufficient memory (check Docker Desktop settings)
- Corrupted database (restore from backup)

### Application Can't Connect

**Verify Neo4j is running:**
```bash
docker ps | grep neo4j
# Should show "healthy" status
```

**Test connection:**
```bash
cd ~/skuel/app
uv run python -c "
from neo4j import GraphDatabase
driver = GraphDatabase.driver('neo4j://localhost:7687', auth=('neo4j', 'password'))
driver.verify_connectivity()
print('✅ Connected!')
driver.close()
"
```

**Check password match:**
```bash
# Compare passwords
cat ~/skuel/infrastructure/.env | grep NEO4J_AUTH
cat ~/skuel/app/.env | grep NEO4J_PASSWORD
# These must match!
```

### Port Conflicts

**Find what's using the port:**
```bash
lsof -i :7474  # HTTP port
lsof -i :7687  # Bolt port
```

**Solutions:**
- Kill the conflicting process
- Change port in `~/skuel/infrastructure/.env` (not recommended)

---

## File Structure

```
/home/mike/skuel/infrastructure/
├── docker-compose.yml     # Neo4j configuration (SINGLE SOURCE OF TRUTH)
├── .env                   # Infrastructure credentials
├── README.md              # Infrastructure documentation
└── neo4j/                 # Persistent storage
    ├── data/              # Database files
    ├── logs/              # Neo4j logs
    ├── conf/              # Auto-generated config
    ├── plugins/           # Future: plugins if needed
    ├── import/            # Bulk data imports
    └── backups/           # Database backups

/home/mike/skuel/app/
├── docker-compose.yml              # App-only (connects to ~/skuel/infrastructure)
├── docker-compose.production.yml   # Full production stack
├── .env                            # App config + Neo4j connection
├── main.py                         # Application entry point
├── core/                           # Business logic
├── adapters/                       # External interfaces
├── docs/                           # Documentation
└── SETUP.md                        # This file
```

---

## Environment Variables Reference

### Infrastructure (.env in ~/skuel/infrastructure)

```bash
# Authentication
NEO4J_AUTH=neo4j/<password>

# Memory Settings (adjust for your system)
NEO4J_HEAP_INIT=1G
NEO4J_HEAP_MAX=1500M
NEO4J_PAGECACHE=2G
```

### Application (.env in /skuel/app)

```bash
# Neo4j Connection
NEO4J_URI=neo4j://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<must match ~/skuel/infrastructure/.env>
NEO4J_DATABASE=neo4j

# AI Services
OPENAI_API_KEY=<your-key>
DEEPGRAM_API_KEY=<your-key>
ANTHROPIC_API_KEY=<your-key>  # Optional

# Application
APP_HOST=0.0.0.0
APP_PORT=8000
APP_DEBUG=false
LOG_LEVEL=INFO

# Future Services (not yet enabled)
REDIS_URL=redis://:password@localhost:6379
OLLAMA_URL=http://localhost:11434
```

---

## Future Services

SKUEL has pre-wired support for additional infrastructure services that are **ready but disabled**:

| Service | Status | Enable When |
|---------|--------|-------------|
| **Redis** | 🟡 Ready | Multi-instance deployment |
| **Ollama** | 🟡 Ready | Local LLM inference needed |
| **Prometheus** | 🟡 Ready | Production monitoring |
| **Grafana** | 🟡 Ready | Operational dashboards |
| **Nginx** | 🟡 Ready | SSL/load balancing |

See `/home/mike/skuel/app/FUTURE_SERVICES.md` for detailed activation instructions.

---

## Next Steps

1. ✅ Infrastructure running (`cd ~/skuel/infrastructure && docker compose ps`)
2. ✅ Application configured (`.env` file created)
3. ✅ Dependencies installed (`uv sync`)
4. ✅ Application running (`uv run python main.py`)
5. 📚 Read `/home/mike/skuel/app/CLAUDE.md` for development patterns
6. 📚 Explore `/home/mike/skuel/app/docs/` for architecture documentation

---

## Quick Command Reference

```bash
# Infrastructure
cd ~/skuel/infrastructure && docker compose up -d              # Start Neo4j
cd ~/skuel/infrastructure && docker compose ps                 # Check status
cd ~/skuel/infrastructure && docker compose logs -f neo4j      # View logs
cd ~/skuel/infrastructure && docker compose restart neo4j      # Restart Neo4j
cd ~/skuel/infrastructure && docker compose down               # Stop (preserves data)

# Application (Local)
cd ~/skuel/app && uv sync                  # Install dependencies
cd ~/skuel/app && uv run python main.py       # Start app
cd ~/skuel/app && ./restart_server.sh             # Restart app (if script exists)

# Application (Docker)
cd ~/skuel/app && docker compose up -d            # Start app container
cd ~/skuel/app && docker compose logs -f          # View app logs
cd ~/skuel/app && docker compose restart          # Restart app

# Database
cd ~/skuel/infrastructure && docker compose exec neo4j neo4j-admin database dump neo4j --to-path=/backups
open http://localhost:7474                      # Neo4j Browser
```

---

## Related Documentation

- **Infrastructure:** `/home/mike/skuel/infrastructure/README.md`
- **Future Services:** `/home/mike/skuel/app/FUTURE_SERVICES.md`
- **Development Guide:** `/home/mike/skuel/app/CLAUDE.md`
- **Architecture:** `/home/mike/skuel/app/docs/architecture/`
- **Archived Infrastructure:** `/home/mike/skuel/app/docs/archive/infrastructure/` (historical reference)

---

**Philosophy:** "Infrastructure should be boring and reliable"

SKUEL's infrastructure separation makes setup predictable, development fast, and deployment clean. Start infrastructure once, develop freely, deploy confidently.
