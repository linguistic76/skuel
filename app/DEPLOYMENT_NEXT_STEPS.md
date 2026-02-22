# Production Deployment - Next Steps

## Current Status ✅

**Async Embedding System Implementation**: COMPLETE

- ✅ Background worker implemented (6 activity domains)
- ✅ Event-driven architecture (zero latency)
- ✅ Batch processing (25 entities every 30 seconds)
- ✅ Production monitoring infrastructure
- ✅ E2E testing validated (worker mechanics)
- ✅ Deployment automation scripts
- ✅ Comprehensive documentation

**Environment**: PRODUCTION-READY

- ✅ AuraDB instance connected (`neo4j+s://c3a6c0c8.databases.neo4j.io`)
- ✅ OpenAI API key configured
- ✅ Deepgram API key configured
- ⚠️ Neo4j GenAI plugin: **NOT YET ENABLED** (manual step required)

---

## What's Blocking Production?

**ONE THING**: Neo4j GenAI plugin must be enabled in AuraDB console

This is a **manual step** that requires AuraDB console access (cannot be automated).

---

## How to Deploy (3 Steps)

### Step 1: Enable Neo4j GenAI Plugin (5 minutes)

**Interactive Guide**:
```bash
export $(cat .env | grep -v '^#' | xargs)
./scripts/production/enable_genai.sh
```

The script will guide you through:
1. Opening AuraDB console (https://console.neo4j.io)
2. Selecting database: `c3a6c0c8`
3. Enabling GenAI plugin
4. Configuring OpenAI API key
5. Verifying plugin works

**Manual Alternative**:
- Follow detailed guide: `/docs/deployment/ENABLE_GENAI_PLUGIN.md`

---

### Step 2: Run Production Validation (2 minutes)

**Full Deployment Checklist**:
```bash
export $(cat .env | grep -v '^#' | xargs)
./scripts/production/deploy_checklist.sh
```

This validates:
- Neo4j GenAI plugin enabled ✅
- Application starts successfully ✅
- Monitoring endpoints working ✅
- Embedding generation E2E ✅
- Semantic search functional ✅

**Focused Embedding Test** (alternative):
```bash
export $(cat .env | grep -v '^#' | xargs)
poetry run python scripts/production/validate_embeddings.py
```

---

### Step 3: Start Production Application

```bash
export $(cat .env | grep -v '^#' | xargs)
poetry run python main.py
```

**Expected Startup Logs**:
```
✅ Neo4j driver validated
✅ Neo4j GenAI embeddings service created
✅ Embedding background worker created (batch_size=25, interval=30s)
   Worker will process embeddings for: Tasks, Goals, Habits, Events, Choices, Principles
🌟 SKUEL Application started on http://0.0.0.0:8000
✅ Embedding background worker started
```

---

## Monitoring (After Deployment)

### Health Check

```bash
curl http://localhost:8000/api/monitoring/health
```

Expected: `{"status": "healthy", "service": "SKUEL", "version": "1.0"}`

### Worker Metrics

```bash
curl http://localhost:8000/api/monitoring/embedding-worker | python -m json.tool
```

Expected:
```json
{
  "status": "running",
  "metrics": {
    "total_processed": 150,
    "total_success": 148,
    "total_failed": 2,
    "batches_processed": 6,
    "queue_size": 3,
    "uptime_seconds": 1800,
    "success_rate": 98.67,
    "avg_batch_size": 25.0
  }
}
```

**Alert on**:
- `success_rate` < 95% → Check OpenAI API
- `queue_size` > 100 → Tune batch config
- Worker status != "running" → Check logs

### System Metrics

```bash
curl http://localhost:8000/api/monitoring/system | python -m json.tool
```

---

## Validation Checklist

After deployment, verify:

- [ ] Application started without errors
- [ ] Worker logs show: "✅ Embedding background worker started"
- [ ] Health endpoint returns 200
- [ ] Worker endpoint shows "running" status
- [ ] Create a test task via UI
- [ ] Wait 35 seconds
- [ ] Check task has embedding in Neo4j Browser:
  ```cypher
  MATCH (t:Task {uid: 'task.YOUR_TEST_TASK'})
  RETURN t.embedding IS NOT NULL AS has_embedding,
         size(t.embedding) AS dimension
  ```
- [ ] Test semantic search finds the task
- [ ] Monitor for 24 hours (success_rate > 95%)

---

## Troubleshooting

### GenAI Plugin Not Enabled

**Error**: "Unknown function 'ai.text.embed'"

**Solution**:
1. Open https://console.neo4j.io
2. Select database: `c3a6c0c8`
3. Go to Plugins → Enable "GenAI"
4. Wait 2-3 minutes for activation
5. Verify: Run `RETURN ai.text.embed("test")` in Neo4j Browser

### Worker Not Processing

**Error**: Embeddings not generated after 35 seconds

**Check**:
```bash
# Worker started?
tail -f logs/skuel.log | grep "Embedding background worker"

# Events published?
tail -f logs/skuel.log | grep "TaskEmbeddingRequested"

# Worker metrics
curl http://localhost:8000/api/monitoring/embedding-worker
```

### High Failure Rate

**Issue**: success_rate < 95%

**Solutions**:
1. Check OpenAI API status/limits
2. Reduce batch size in `services_bootstrap.py`:
   ```python
   embedding_worker = EmbeddingBackgroundWorker(
       batch_size=10,  # Reduce from 25
       batch_interval_seconds=60,  # Increase from 30
   )
   ```
3. Check logs: `tail -f logs/skuel.log | grep embedding`

---

## Documentation

**Deployment Guides**:
- `/scripts/production/README.md` - Script usage
- `/docs/deployment/ENABLE_GENAI_PLUGIN.md` - GenAI setup
- `/docs/PRODUCTION_DEPLOYMENT_GUIDE.md` - Complete guide

**Architecture**:
- `/docs/E2E_TEST_RESULTS.md` - Test results
- `/docs/migrations/PHASE3_PRODUCTION_VALIDATION_2026-01-29.md` - Implementation

**Monitoring**:
- `GET /api/monitoring/health` - Health check
- `GET /api/monitoring/embedding-worker` - Worker metrics
- `GET /api/monitoring/system` - System status

---

## Performance Characteristics

**Throughput**:
- Batch size: 25 entities
- Batch interval: 30 seconds
- Max throughput: ~50 entities/minute

**Latency**:
- User creation: Instant (zero latency)
- Embedding available: 30-60 seconds (eventual consistency)

**Cost** (1,000 entities/day):
- ~30,000 entities/month
- ~$0.03/month (OpenAI embeddings)

**Resource Usage**:
- Memory: ~10MB (worker)
- CPU: <1% (average, 30s sleep cycles)
- Network: ~100KB per batch (OpenAI API + Neo4j)

---

## Success Criteria

**Production Ready When**:
- ✅ Neo4j GenAI plugin enabled
- ✅ Application starts without errors
- ✅ Worker processes embedding requests
- ✅ Embeddings stored in Neo4j
- ✅ Semantic search returns results
- ✅ Success rate > 95% (24-hour average)
- ✅ Queue size < 100 (steady state)
- ✅ No worker crashes

---

## Summary

**What's Done**: Everything except enabling the GenAI plugin

**What's Needed**: Enable GenAI plugin in AuraDB console (5-minute manual step)

**What Happens Next**: Complete deployment in <10 minutes

**Expected Result**: Zero-latency async embedding generation across all activity domains with production-grade monitoring

---

**Last Updated**: January 30, 2026
**Status**: Ready for Production Deployment
**Blocker**: Enable Neo4j GenAI plugin (manual step)

**Run**: `./scripts/production/enable_genai.sh` to get started
