# Production Deployment Scripts

Automated scripts for deploying and validating the async embedding system in production.

---

## Quick Start

### Prerequisites

1. **Environment Variables** (.env file):
   ```bash
   NEO4J_URI=neo4j+s://YOUR_INSTANCE.databases.neo4j.io
   NEO4J_PASSWORD=your_password
   OPENAI_API_KEY=sk-proj-...
   ```

2. **AuraDB Instance**: Running and accessible

3. **Poetry**: Installed (`curl -sSL https://install.python-poetry.org | python3 -`)

---

## Deployment Workflow

### Step 1: Enable Neo4j GenAI Plugin

**Interactive Guide**:
```bash
./scripts/production/enable_genai.sh
```

This script will:
- Check current plugin status
- Guide you through AuraDB console steps
- Verify plugin is working
- Configure OpenAI API key

**Manual Steps** (if preferred):
1. Open https://console.neo4j.io
2. Select database: `c3a6c0c8`
3. Go to Plugins → Enable "GenAI"
4. Configure OpenAI API key
5. Wait 2-3 minutes for activation

**Detailed Documentation**: `/docs/deployment/ENABLE_GENAI_PLUGIN.md`

---

### Step 2: Run Production Validation

**Comprehensive Validation**:
```bash
./scripts/production/deploy_checklist.sh
```

This script validates:
- ✅ Environment variables configured
- ✅ Poetry and dependencies installed
- ✅ Neo4j GenAI plugin enabled
- ✅ Application startup successful
- ✅ Monitoring endpoints working
- ✅ Embedding generation E2E
- ✅ Semantic search functional

**Expected Output**:
```
==========================================
DEPLOYMENT VALIDATION COMPLETE
==========================================

✅ Environment configured
✅ Neo4j GenAI plugin enabled
✅ Application startup successful
✅ Monitoring endpoints working
✅ Embedding generation validated
✅ Semantic search functional

PRODUCTION DEPLOYMENT READY!
```

---

### Step 3: Focused Embedding Validation (Optional)

**Test Embedding System Only**:
```bash
poetry run python scripts/production/validate_embeddings.py
```

This script:
1. Verifies GenAI plugin
2. Creates test task
3. Waits for background worker (35 seconds)
4. Validates embedding generated
5. Tests semantic search
6. Cleans up test data

**Use Case**: Quick validation after configuration changes

---

## Scripts Overview

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `enable_genai.sh` | Interactive GenAI plugin setup | First-time deployment |
| `deploy_checklist.sh` | Full production validation | Before go-live |
| `validate_embeddings.py` | Focused embedding testing | After config changes |

---

## Monitoring

### Worker Metrics

**Health Check**:
```bash
curl http://localhost:8000/api/monitoring/health
```

**Worker Metrics**:
```bash
curl http://localhost:8000/api/monitoring/embedding-worker | python -m json.tool
```

**Expected Response**:
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

**System Metrics**:
```bash
curl http://localhost:8000/api/monitoring/system | python -m json.tool
```

---

## Alert Thresholds

Set up monitoring alerts for:

| Metric | Warning | Critical | Action |
|--------|---------|----------|--------|
| `success_rate` | < 95% | < 90% | Check OpenAI API status |
| `queue_size` | > 100 | > 500 | Tune batch size/interval |
| `uptime_seconds` | Resets | Any | Investigate worker crash |
| Worker status | - | "unavailable" | Check app logs |

---

## Troubleshooting

### GenAI Plugin Not Working

**Symptom**: `enable_genai.sh` fails with "Unknown function 'ai.text.embed'"

**Solutions**:
1. Wait longer (plugin takes 2-3 minutes to activate)
2. Verify API key in AuraDB console
3. Test in Neo4j Browser: `RETURN ai.text.embed("test")`
4. Check AuraDB plugin status page

### Worker Not Processing Embeddings

**Symptom**: `validate_embeddings.py` shows no embedding after 35 seconds

**Checks**:
1. Application running: `poetry run python main.py`
2. Worker started: Check logs for "✅ Embedding background worker started"
3. Events published: Check logs for "TaskEmbeddingRequested"
4. Worker metrics: `curl http://localhost:8000/api/monitoring/embedding-worker`

**Common Causes**:
- Worker not started (check logs)
- Event bus not publishing events
- embeddings_service is None (check startup logs)
- OpenAI API errors (check worker logs)

### High Failure Rate

**Symptom**: `success_rate` < 95%

**Causes**:
- OpenAI API rate limiting
- Network connectivity issues
- Invalid API key
- Entities deleted before embedding generated

**Solutions**:
1. Reduce batch size: `batch_size=10` in `services_bootstrap.py`
2. Increase interval: `batch_interval_seconds=60`
3. Check OpenAI API status/limits
4. Verify API key configuration

---

## Performance Tuning

### Batch Configuration

**Location**: `/services_bootstrap.py`

```python
embedding_worker = EmbeddingBackgroundWorker(
    event_bus=event_bus,
    embeddings_service=embeddings_service,
    driver=driver,
    batch_size=25,  # Adjust based on throughput needs
    batch_interval_seconds=30,  # Adjust based on latency tolerance
)
```

**Guidelines**:
- **Higher throughput**: Increase `batch_size` (25 → 50)
- **Lower latency**: Decrease `batch_interval_seconds` (30 → 15)
- **Rate limit issues**: Decrease `batch_size` (25 → 10), increase `batch_interval_seconds` (30 → 60)

### Cost Optimization

**Current Settings**:
- Batch size: 25 entities
- Batch interval: 30 seconds
- Max throughput: ~50 entities/minute

**Cost Estimate** (1,000 entities/day):
- ~30,000 entities/month
- ~1.5M tokens/month
- ~$0.03/month (negligible)

**Optimization**: No changes needed at current scale

---

## Logs

### Worker Logs

**All embedding-related logs**:
```bash
tail -f logs/skuel.log | grep embedding
```

**Worker startup**:
```bash
tail -f logs/skuel.log | grep "Embedding background worker"
```

**Batch processing**:
```bash
tail -f logs/skuel.log | grep "Processing batch"
```

**Errors only**:
```bash
tail -f logs/skuel.log | grep -E "ERROR|FAIL" | grep embedding
```

---

## Production Validation Checklist

Manual verification after deployment:

### Pre-Deployment
- [ ] Environment variables configured (.env file)
- [ ] AuraDB instance accessible
- [ ] OpenAI API key valid
- [ ] Poetry installed
- [ ] Dependencies installed (`poetry install --without dev`)

### GenAI Plugin
- [ ] Plugin enabled in AuraDB console
- [ ] Plugin status: "Active"
- [ ] OpenAI API key configured at database level
- [ ] Test query works: `RETURN ai.text.embed("test")`

### Application
- [ ] Application starts without errors
- [ ] Worker logs show: "✅ Embedding background worker started"
- [ ] Health endpoint: `GET /api/monitoring/health` returns 200
- [ ] Worker endpoint: `GET /api/monitoring/embedding-worker` returns "running"

### E2E Flow
- [ ] Create task via UI/API
- [ ] Wait 35 seconds
- [ ] Check task has embedding in Neo4j
- [ ] Semantic search finds task
- [ ] Worker metrics show processed count incremented

### 24-Hour Monitoring
- [ ] Success rate > 95%
- [ ] Queue size < 100 (steady state)
- [ ] No worker crashes (uptime doesn't reset)
- [ ] OpenAI API usage within limits

---

## Next Steps After Validation

1. **Deploy to Production**:
   - Same environment variables
   - Same deployment process
   - Monitor for 24 hours

2. **Set Up Alerting**:
   - Success rate < 95%
   - Queue size > 100
   - Worker status != "running"

3. **Load Testing** (Optional):
   - Create 100+ entities rapidly
   - Monitor queue size and processing time
   - Verify batch processing handles spike

4. **User Acceptance Testing**:
   - Real users create tasks/goals
   - Validate semantic search quality
   - Gather feedback on relevance

---

## Documentation

**Deployment**:
- `/docs/deployment/ENABLE_GENAI_PLUGIN.md` - Plugin setup
- `/docs/PRODUCTION_DEPLOYMENT_GUIDE.md` - Complete guide

**Architecture**:
- `/docs/E2E_TEST_RESULTS.md` - Test results
- `/docs/migrations/PHASE3_PRODUCTION_VALIDATION_2026-01-29.md` - Implementation summary

**Monitoring**:
- `/adapters/inbound/monitoring_routes.py` - Monitoring API code
- `/core/services/background/embedding_worker.py` - Worker implementation

---

**Last Updated**: January 30, 2026
**Status**: Production Ready (awaiting GenAI plugin enablement)
