# Production Deployment Guide - Async Embedding System

## Overview

This guide covers deploying the async embedding background worker to production for zero-latency semantic search across all activity domains.

---

## Prerequisites

### Required Services
- ✅ **Neo4j AuraDB** (with GenAI plugin enabled)
- ✅ **OpenAI API Key** (for embeddings generation)
- ✅ **Python 3.11+** with poetry

### Optional (For Monitoring)
- Monitoring dashboard (Grafana/Prometheus)
- Log aggregation (ELK/Datadog)
- Alerting service (PagerDuty/Slack)

---

## Configuration

### Environment Variables

```bash
# Required
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
OPEN AI_API_KEY=sk-xxxxx

# Optional (Recommended for Production)
DEEPGRAM_API_KEY=your_key  # For audio transcription

# Worker Configuration (Optional - Defaults shown)
EMBEDDING_BATCH_SIZE=25
EMBEDDING_BATCH_INTERVAL=30
```

### Neo4j GenAI Plugin Setup

**In Neo4j AuraDB Console**:
1. Navigate to "Plugins" tab
2. Enable "GenAI" plugin
3. Configure OpenAI credentials at database level
4. Verify with: `RETURN ai.text.embed('test')` in Neo4j Browser

---

## Deployment Steps

### 1. Install Dependencies

```bash
poetry install --without dev
```

### 2. Verify Configuration

```bash
# Test Neo4j connection
poetry run python -c "from adapters.persistence.neo4j_adapter import Neo4jAdapter; import asyncio; asyncio.run(Neo4jAdapter().connect())"

# Test embeddings service
poetry run python -c "from core.services.neo4j_genai_embeddings_service import Neo4jGenAIEmbeddingsService; print('OK')"
```

### 3. Start Application

```bash
poetry run python main.py --host 0.0.0.0 --port 8000
```

**Expected Startup Logs**:
```
✅ Neo4j driver validated
✅ Neo4j GenAI embeddings service created
✅ Embedding background worker created (batch_size=25, interval=30s)
   Worker will process embeddings for: Tasks, Goals, Habits, Events, Choices, Principles
🌟 SKUEL Application started on http://0.0.0.0:8000
✅ Embedding background worker started (processes Tasks, Goals, Habits, Events, Choices, Principles)
```

---

## Monitoring

### Health Check Endpoints

**Application Health**:
```bash
curl http://localhost:8000/api/monitoring/health
# Response: {"status": "healthy", "service": "SKUEL", "version": "1.0"}
```

**Worker Metrics**:
```bash
curl http://localhost:8000/api/monitoring/embedding-worker
# Response:
# {
#   "status": "running",
#   "metrics": {
#     "total_processed": 150,
#     "total_success": 148,
#     "total_failed": 2,
#     "batches_processed": 6,
#     "queue_size": 3,
#     "uptime_seconds": 1800,
#     "success_rate": 98.67,
#     "avg_batch_size": 25.0
#   }
# }
```

**System Metrics**:
```bash
curl http://localhost:8000/api/monitoring/system
# Response: Complete system status including all services
```

### Key Metrics to Monitor

| Metric | Alert Threshold | Action |
|--------|----------------|--------|
| `success_rate` | < 95% | Check OpenAI API status |
| `queue_size` | > 100 | Increase batch size or frequency |
| `uptime_seconds` | Resets unexpectedly | Worker crashed - check logs |
| `total_failed` | Increasing rapidly | Investigate error logs |

---

## Performance Tuning

### Batch Size

**Default**: 25 entities per batch

**Adjust based on**:
- OpenAI API rate limits
- Average entity text size
- Desired processing latency

**Change in**: `services_bootstrap.py:1227`
```python
embedding_worker = EmbeddingBackgroundWorker(
    ...
    batch_size=50,  # Increase for higher throughput
    ...
)
```

### Batch Interval

**Default**: 30 seconds

**Adjust based on**:
- User creation patterns
- API cost considerations
- Acceptable embedding latency

**Change in**: `services_bootstrap.py:1228`
```python
embedding_worker = EmbeddingBackgroundWorker(
    ...
    batch_interval_seconds=60,  # Increase to reduce API calls
    ...
)
```

---

## Troubleshooting

### Worker Not Starting

**Symptom**: Log shows "Worker skipped"
```
⏭️  Embedding background worker skipped (embeddings_service not available)
```

**Cause**: OpenAI API key not configured or Neo4j GenAI plugin disabled

**Fix**:
1. Verify `OPENAI_API_KEY` environment variable
2. Check Neo4j GenAI plugin status in AuraDB console
3. Test manually: `RETURN ai.text.embed('test')` in Neo4j Browser

### High Failure Rate

**Symptom**: `success_rate` < 95%

**Common Causes**:
- OpenAI API rate limiting
- Entities deleted before embedding generated
- Network connectivity issues

**Fix**:
1. Check OpenAI API status/limits
2. Reduce batch size
3. Increase batch interval
4. Check Neo4j connection stability

### Queue Buildup

**Symptom**: `queue_size` constantly increasing

**Causes**:
- Batch size too small
- Batch interval too long
- High entity creation rate

**Fix**:
1. Increase batch size (e.g., 25 → 50)
2. Decrease batch interval (e.g., 30s → 15s)
3. Monitor OpenAI API usage to avoid rate limits

### Worker Crashes

**Symptom**: Worker task stops unexpectedly

**Check**:
1. Application logs for exceptions
2. Neo4j connection status
3. OpenAI API errors
4. System memory/resources

**Recovery**: Worker auto-restarts on app restart

---

## Cost Optimization

### OpenAI API Usage

**Estimate**:
- Average entity text: ~200 characters
- Batch size: 25 entities
- Cost per 1M tokens: ~$0.02 (text-embedding-ada-002)

**Monthly Cost Example**:
- 1,000 entities/day = 30,000 entities/month
- ~30K * 200 chars = 6M characters = ~1.5M tokens
- Monthly cost: ~$0.03

**Optimization Strategies**:
1. Increase batch interval for lower-priority domains
2. Skip embedding for very short entities (<20 chars)
3. Cache embeddings for duplicate content
4. Use smaller embedding models if available

---

## Disaster Recovery

### Worker Failure

**Impact**: New entities won't get embeddings automatically

**Mitigation**:
- Entities still created successfully (zero user impact)
- Search falls back to keyword search
- Manual embedding regeneration available via ingestion

**Recovery**:
1. Fix underlying issue (API key, connection, etc.)
2. Restart application
3. Re-ingest affected entities if needed

### Data Loss Prevention

**Embeddings stored in**:
- Neo4j nodes: `entity.embedding` property
- Backup via Neo4j AuraDB automatic backups

**Recovery**:
- Restore from Neo4j backup
- Re-generate embeddings via ingestion if needed

---

## Scaling Considerations

### Single Instance (Current)

**Capacity**:
- ~50-100 entities/minute
- Queue size: Unlimited (in-memory)
- Suitable for: Most deployments

### Multi-Instance (Future)

**When to scale**:
- `queue_size` consistently > 1000
- Entity creation rate > 100/minute
- Multiple regions/datacenters

**Architecture**:
- External message queue (RabbitMQ/Kafka)
- Multiple worker instances
- Distributed locking for batch coordination

---

## Security

### API Key Protection

- Store in environment variables (never in code)
- Use secrets manager (AWS Secrets Manager/HashiCorp Vault)
- Rotate keys regularly
- Monitor for unauthorized usage

### Network Security

- HTTPS only for external APIs
- VPC/private network for Neo4j
- IP whitelisting for production databases
- Rate limiting on monitoring endpoints

---

## Maintenance

### Monitoring Dashboard

**Recommended Metrics**:
```
- Worker uptime
- Success rate trend (last 24h)
- Queue size trend
- Processing latency (p50, p95, p99)
- OpenAI API error rate
```

### Alerts

**Critical**:
- Worker down for > 5 minutes
- Success rate < 90% for > 10 minutes
- Queue size > 500 for > 30 minutes

**Warning**:
- Success rate < 95%
- Queue size > 100
- Batch processing time > 10s

### Log Aggregation

**Key Log Patterns**:
```
# Worker started
"Embedding background worker started"

# Batch processing
"Processing batch of X embedding requests"

# Success
"Generated X/Y embeddings successfully"

# Errors
"Batch embedding generation failed"
"Failed to store embedding"
```

---

## Rollback Plan

### If Issues Arise

1. **Stop worker**: Set `OPENAI_API_KEY` to empty
2. **Restart app**: Worker won't start without API key
3. **Verify**: Check logs for "Worker skipped"
4. **Impact**: Zero user-facing impact (search uses keyword fallback)

### Re-enable After Fix

1. **Fix issue**: Restore API key, fix configuration
2. **Restart app**: Worker starts automatically
3. **Monitor**: Watch `/api/monitoring/embedding-worker`
4. **Verify**: Check success rate returns to > 95%

---

## Support

### Logs Location

```bash
# Application logs
tail -f logs/skuel.log

# Worker-specific logs
tail -f logs/skuel.log | grep "skuel.background.embeddings"

# Error logs only
tail -f logs/skuel.log | grep "ERROR"
```

### Debug Mode

Enable detailed logging:
```python
# In services_bootstrap.py
embedding_worker.logger.setLevel("DEBUG")
```

### Common Issues

| Issue | Log Pattern | Solution |
|-------|-------------|----------|
| API Rate Limit | "Rate limit exceeded" | Increase batch interval |
| Network Timeout | "Connection timeout" | Check Neo4j/OpenAI connectivity |
| Entity Not Found | "Entity not found" | Normal - entity deleted before embedding |
| Worker Crash | "Task exception" | Check full stack trace |

---

**Last Updated**: January 29, 2026
**Version**: 1.0 (Phase 3)
**Status**: Production Ready
