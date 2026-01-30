# SKUEL Future Services - Ready but On Hold

**Status**: Pre-wired and ready to enable when needed
**Last Updated**: 2026-01-02

## Overview

SKUEL has pre-existing configuration and code wiring for several infrastructure services that are **intentionally disabled** and will be enabled at a future date when requirements demand them. This document clarifies which services are ready to enable and why they're currently on hold.

## Service Status Matrix

| Service | Status | Code Ready? | Config Ready? | Why On Hold | Enable When |
|---------|--------|-------------|---------------|-------------|-------------|
| **Redis** | 🟡 Ready | ✅ Yes | ✅ Yes | In-memory cache sufficient for development | Production deployment or multi-instance scaling |
| **Ollama** | 🟡 Ready | ✅ Yes | ✅ Yes | OpenAI API sufficient for current needs | Want to reduce API costs or local inference needed |
| **Monitoring** | 🟡 Ready | ✅ Yes | ✅ Yes | Development phase, manual monitoring sufficient | Production deployment |
| **Nginx** | 🟡 Ready | ⚠️ Partial | ✅ Yes | Not needed for local development | Production deployment with SSL/load balancing |
| **RabbitMQ/Kafka** | 🔴 Planned | ⚠️ Partial | ✅ Yes | In-memory event bus sufficient | Distributed architecture or microservices |
| **APOC** | 🔴 On Hold | ⚠️ Tests Only | ✅ Yes | Pure Cypher preferred for transparency | Only if adds significant value over pure Cypher |

## Currently Running Services

| Service | Location | Status | Purpose |
|---------|----------|--------|---------|
| **Neo4j** | `/infra` | ✅ Active | Graph database - PRIMARY DATA STORE |
| **OpenAI API** | External | ✅ Active | AI/LLM features, embeddings |
| **Deepgram API** | External | ✅ Active | Audio transcription |

---

## Future Service Details

### 1. Redis - Distributed Caching

**Current State**: Application uses in-memory cache via `CacheConfig(provider="memory")`

**Pre-Wired Components**:
- ✅ `CacheConfig` in `core/config/unified_config.py` supports Redis
- ✅ `redis_url()` helper in `core/config/settings.py`
- ✅ Docker Compose configuration in `docker-compose.production.yml`
- ✅ Environment variable support: `REDIS_URL`, `CACHE_PROVIDER`

**Configuration Ready**:
```python
# In unified_config.py
class CacheConfig:
    enabled: bool = True
    provider: str = "memory"  # Change to "redis" when enabled
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    ttl_seconds: int = 3600
```

**To Enable**:
1. Add Redis to `/infra/docker-compose.yml`
2. Set in `/skuel/app/.env`:
   ```bash
   REDIS_URL=redis://:password@localhost:6379
   CACHE_PROVIDER=redis
   CACHE_ENABLED=true
   ```
3. Restart application

**Use Cases**:
- Distributed caching across multiple app instances
- Session persistence
- Rate limiting
- Query result caching

**Why On Hold**:
- Single application instance (development)
- In-memory cache performs well for current load
- No distributed deployment yet

**Enable When**:
- Deploying multiple application instances
- Need session persistence across restarts
- Production deployment
- Performance optimization needed

---

### 2. Ollama - Local LLM Inference

**Current State**: Using OpenAI API exclusively

**Pre-Wired Components**:
- ✅ Docker Compose configuration in `docker-compose.production.yml`
- ✅ Environment variable: `OLLAMA_URL` (default: `http://host.docker.internal:11434`)
- ⚠️ Application code uses OpenAI SDK (would need LangChain adapter for Ollama)

**Configuration Ready**:
```yaml
# In docker-compose.production.yml
ollama:
  image: ollama/ollama:latest
  container_name: skuel-ollama
  volumes:
    - ollama-models:/root/.ollama
  ports:
    - "11434:11434"
```

**To Enable**:
1. Uncomment Ollama service in production compose
2. Install models: `docker exec skuel-ollama ollama pull llama2`
3. Update application to use LangChain with Ollama backend
4. Set `OLLAMA_URL` in .env

**Use Cases**:
- Reduce OpenAI API costs
- Local/offline LLM inference
- Privacy-sensitive deployments (data never leaves server)
- Custom model fine-tuning

**Why On Hold**:
- OpenAI API working well
- No cost pressure yet
- Ollama requires significant resources (GPU ideal)
- Development phase focuses on features, not cost optimization

**Enable When**:
- OpenAI API costs become significant
- Need offline LLM capabilities
- Privacy requirements demand local inference
- Have GPU resources available

---

### 3. Monitoring Stack - Prometheus & Grafana

**Current State**: Manual monitoring via logs and Neo4j browser

**Pre-Wired Components**:
- ✅ Docker Compose configuration in `docker-compose.production.yml`
- ✅ Neo4j metrics endpoint exposed (port 2004)
- ✅ Performance monitoring hooks in `core/utils/performance_monitor.py`
- ⚠️ Missing: Prometheus config files, Grafana dashboards

**Configuration Ready**:
```yaml
# In docker-compose.production.yml
prometheus:
  image: prom/prometheus:latest
  ports:
    - "9090:9090"
  volumes:
    - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml

grafana:
  image: grafana/grafana:latest
  ports:
    - "3000:3000"
  volumes:
    - ./monitoring/grafana:/var/lib/grafana
```

**To Enable**:
1. Create `/monitoring/prometheus.yml` configuration
2. Create Grafana dashboards for SKUEL metrics
3. Uncomment monitoring services in production compose
4. Configure alerting rules

**Use Cases**:
- Real-time application metrics
- Neo4j database performance monitoring
- Query performance analysis
- Alerting on issues (high memory, slow queries, errors)
- SLA/uptime tracking

**Why On Hold**:
- Development phase
- Low user load (single developer)
- Manual monitoring sufficient
- Focus on feature development, not ops

**Enable When**:
- Production deployment
- Multiple users
- Need SLA tracking
- Performance tuning phase
- Team needs operational visibility

---

### 4. Nginx - Reverse Proxy

**Current State**: Application runs directly on port 8000

**Pre-Wired Components**:
- ✅ Docker Compose configuration in `docker-compose.production.yml`
- ⚠️ Missing: `/nginx/nginx.conf` configuration file
- ⚠️ Application code doesn't have SSL/proxy awareness

**Configuration Ready**:
```yaml
# In docker-compose.production.yml
nginx:
  image: nginx:alpine
  ports:
    - "80:80"
    - "443:443"
  volumes:
    - ./nginx/nginx.conf:/etc/nginx/nginx.conf
```

**To Enable**:
1. Create `/nginx/nginx.conf` with reverse proxy rules
2. Configure SSL certificates (Let's Encrypt)
3. Update application to trust X-Forwarded-For headers
4. Uncomment nginx service in production compose

**Use Cases**:
- SSL/TLS termination (HTTPS)
- Load balancing across multiple app instances
- Static file serving (offload from Python)
- Rate limiting
- DDoS protection
- Gzip compression

**Why On Hold**:
- Local development (HTTP sufficient)
- Single application instance
- No SSL requirements yet
- Direct access simpler for debugging

**Enable When**:
- Production deployment with domain name
- Need HTTPS/SSL
- Multiple application instances (load balancing)
- Want to serve static files from nginx
- Need rate limiting or DDoS protection

---

### 5. Message Queue - RabbitMQ / Kafka

**Current State**: In-memory event bus via `InMemoryEventBus`

**Pre-Wired Components**:
- ✅ `MessageQueueConfig` in `core/config/unified_config.py`
- ✅ Event bus abstraction supports external queues
- ⚠️ No RabbitMQ/Kafka adapters implemented yet
- ✅ Configuration ready but `enabled: false`

**Configuration Ready**:
```python
# In unified_config.py
class MessageQueueConfig:
    enabled: bool = False  # SET TO TRUE when needed
    provider: str = "memory"  # Options: memory, rabbitmq, kafka
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    kafka_brokers: list[str] = field(default_factory=lambda: ["localhost:9092"])
```

**To Enable**:
1. Choose provider (RabbitMQ or Kafka)
2. Add service to `/infra/docker-compose.yml`
3. Implement adapter in `/adapters/infrastructure/`
4. Update `services_bootstrap.py` to use external queue
5. Set `MESSAGE_QUEUE_ENABLED=true` in .env

**Use Cases**:
- Distributed architecture (microservices)
- Asynchronous job processing
- Event-driven architecture across services
- Guaranteed message delivery
- Service decoupling

**Why On Hold**:
- Monolithic application architecture
- In-memory event bus sufficient
- No distributed services yet
- Adds complexity without current benefit

**Enable When**:
- Breaking into microservices
- Need guaranteed message delivery
- Distributed deployment
- Asynchronous job queue requirements
- Event sourcing architecture

---

### 6. APOC - Advanced Graph Procedures

**Current State**: NO APOC usage in production code (eliminated in Phase 5)

**Pre-Wired Components**:
- ✅ Docker Compose configuration references APOC
- ✅ `infrastructure/apoc.conf` configuration file exists
- ✅ Test suite (`tests/integration/test_apoc_canary.py`) ready to verify APOC if enabled
- ❌ **NO APOC calls in production code** - Phase 5 eliminated all APOC usage
- ✅ SKUEL001 linter rule actively prevents APOC in domain services

**SKUEL Philosophy: Pure Cypher First**:

SKUEL **strongly prefers pure Cypher** over APOC for the following reasons:

1. **Transparency** - Pure Cypher queries are readable and understandable
2. **Query Planner** - Cypher uses cost-based optimization, APOC bypasses it
3. **Index Usage** - Cypher automatically uses indexes, APOC may not
4. **Query Cache** - Cypher queries are cached (10-100x speedup), APOC calls are not
5. **Maintainability** - No plugin versioning headaches (APOC version must exactly match Neo4j)
6. **Portability** - Pure Cypher works everywhere, APOC requires installation

**What Was Eliminated (Phase 5)**:
```cypher
# BEFORE (Phase 4) - APOC traversal
CALL apoc.path.subgraphNodes(n, {
    relationshipFilter: "REQUIRES>|ENABLES>",
    maxLevel: 3
})

# AFTER (Phase 5) - Pure Cypher variable-length pattern
MATCH path = (n)-[:REQUIRES|ENABLES*1..3]->(related)
RETURN DISTINCT related
```

**Result**: Pure Cypher is actually **faster** due to query planner optimization!

**Current Infrastructure**:
- `test_apoc_canary.py` contains tests that would run IF APOC were enabled
- Tests verify APOC procedures work (for infrastructure tasks only, not domain logic)
- SKUEL001 linter rule prevents accidental APOC usage in domain services

**To Enable** (Not Recommended):
1. Uncomment APOC in docker-compose files
2. Add APOC JAR to Neo4j plugins directory
3. Configure APOC security settings in `apoc.conf`
4. Ensure APOC version **exactly matches** Neo4j version (critical!)

**Use Cases Where APOC Might Add Value**:
- **Batch operations** (`apoc.periodic.iterate`) - For bulk data imports
- **Schema introspection** (`apoc.meta.*`) - For tooling/debugging
- **JSON/XML parsing** (`apoc.convert.*`) - For data import from external sources
- **Virtual nodes/relationships** - For graph projections

**Why On Hold**:
- Pure Cypher handles 100% of current use cases
- Query planner optimization outperforms APOC for traversals
- No need for batch operations (current data volume small)
- Schema introspection not needed (we control the schema)
- APOC adds maintenance burden (version matching)

**Enable When**:
- **Batch operations become critical** - Importing millions of nodes requires `apoc.periodic.iterate`
- **Schema tools needed** - Building admin/debugging tools that introspect graph structure
- **Complex data import** - Importing from JSON/XML/CSV that pure Cypher can't handle
- **Proven performance benefit** - Benchmark shows APOC provides measurable speedup over pure Cypher

**Decision Criteria**:

Before enabling APOC, ask:

1. **Can pure Cypher do this?** (Answer is usually "yes")
2. **Have we benchmarked?** (APOC may be slower due to bypassing query planner)
3. **Is this infrastructure or domain logic?** (APOC only acceptable in infrastructure/tooling)
4. **Do we need this feature now?** (Don't add APOC "just in case")

**Documentation**:
- `/docs/patterns/CYPHER_VS_APOC_STRATEGY.md` - Full analysis of when to use what
- `/tests/integration/test_apoc_canary.py` - Tests for APOC procedures (if enabled)
- `/scripts/lint_skuel.py` - SKUEL001 rule prevents APOC in domain services

**Architectural Principle**:

> "APOC should be an adapter layer for infrastructure tasks, NEVER for domain logic.
> If you're tempted to use APOC in a service, write pure Cypher first and benchmark."

**Phase 5 Achievement**: Eliminated ALL APOC from domain services while improving performance through pure Cypher + query planner optimization.

**Recommendation**: Keep APOC disabled unless a specific, benchmarked use case proves it provides measurable value over pure Cypher.

---

## Configuration Files Reference

### Where Future Services Are Configured

| File | What It Contains |
|------|------------------|
| `core/config/unified_config.py` | Service configuration classes (Redis, Cache, MessageQueue) |
| `docker-compose.production.yml` | Docker service definitions (Redis, Ollama, Nginx, Monitoring) |
| `core/config/settings.py` | Helper functions (`redis_url()`, etc.) |
| `core/utils/services_bootstrap.py` | Service initialization logic |

### Environment Variables for Future Services

```bash
# Redis (when enabled)
REDIS_URL=redis://:password@localhost:6379
CACHE_PROVIDER=redis  # Options: memory, redis
CACHE_ENABLED=true

# Ollama (when enabled)
OLLAMA_URL=http://localhost:11434
OLLAMA_ENABLED=true

# Message Queue (when enabled)
MESSAGE_QUEUE_ENABLED=false
MESSAGE_QUEUE_PROVIDER=memory  # Options: memory, rabbitmq, kafka
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
KAFKA_BROKERS=localhost:9092
```

---

## Decision Criteria: When to Enable a Service

### Questions to Ask

1. **Do we have the problem this solves?**
   - Redis: Need distributed caching or session persistence?
   - Ollama: OpenAI API costs too high?
   - Monitoring: Can't diagnose issues with logs alone?

2. **Is the operational overhead worth it?**
   - Each service requires maintenance, updates, monitoring
   - Development time: focus on features vs. infrastructure

3. **Do we have the resources?**
   - Ollama needs GPU for good performance
   - Monitoring stack needs storage for metrics
   - Message queue adds architectural complexity

4. **What's the risk of not enabling it?**
   - No Redis: Worse performance when scaling, but works fine now
   - No monitoring: Slower to diagnose issues, but manageable
   - No message queue: Can't do async processing, but not needed yet

### Enable in This Order (Recommended)

1. **Redis** - Low overhead, high benefit for production
2. **Monitoring** - Critical for production operations
3. **Nginx** - Required for SSL and production deployment
4. **Ollama** - Only if cost or privacy drives the need
5. **Message Queue** - Only if architecture changes to distributed

---

## Maintenance Notes

### Keeping Configurations Up to Date

Even though services are disabled, their configurations should be maintained:

- ✅ **Do**: Update Docker image versions in docker-compose files
- ✅ **Do**: Keep configuration structure aligned with latest best practices
- ✅ **Do**: Test that commented-out services still work (quarterly check)
- ❌ **Don't**: Remove configuration just because it's unused
- ❌ **Don't**: Let documentation drift from actual config

### Testing Future Services

**Quarterly Check** (recommended):
```bash
# Test that future services still start correctly
cd /skuel/app
docker compose -f docker-compose.production.yml up redis
docker compose -f docker-compose.production.yml up ollama
docker compose -f docker-compose.production.yml up prometheus grafana

# Verify they work, then shut down
docker compose -f docker-compose.production.yml down
```

---

## Summary

**Philosophy**: "Wire early, enable late"

SKUEL follows the principle of preparing infrastructure wiring early in development so services can be enabled with minimal friction when requirements demand them. This approach:

- ✅ Reduces future technical debt
- ✅ Documents architectural expansion paths
- ✅ Makes scaling decisions easier (config already exists)
- ✅ Avoids "panic implementation" when service is urgently needed

**Current Focus**: Feature development with lightweight infrastructure (Neo4j + external APIs)

**Future Path**: Clear, documented expansion when production demands it

---

## Related Documentation

- `/infra/README.md` - Current infrastructure setup (Neo4j)
- `docker-compose.production.yml` - Full production stack definition
- `core/config/unified_config.py` - All service configurations
- `/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md` - Application architecture

---

**Questions?** See the "Why On Hold" and "Enable When" sections for each service above.
