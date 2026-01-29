# Enable Neo4j GenAI Plugin in AuraDB

## Overview

The async embedding system requires the Neo4j GenAI plugin to generate embeddings via OpenAI. This plugin must be enabled manually in the AuraDB console.

**Time Required**: 5-10 minutes (including plugin activation wait time)

---

## Prerequisites

✅ AuraDB instance running (neo4j+s://c3a6c0c8.databases.neo4j.io)
✅ Admin access to AuraDB console
✅ OpenAI API key available

---

## Step-by-Step Instructions

### 1. Log in to AuraDB Console

Navigate to: https://console.neo4j.io

Use your Neo4j credentials to log in.

### 2. Select Your Database Instance

- Click on your database instance: **c3a6c0c8**
- You should see the database dashboard

### 3. Navigate to Plugins Tab

- Click on the **"Plugins"** tab in the left sidebar
- You'll see a list of available plugins

### 4. Enable GenAI Plugin

- Find **"GenAI"** in the plugin list
- Click **"Enable"** button
- The plugin will begin installation (this takes 2-3 minutes)

### 5. Configure OpenAI Credentials

After the plugin is enabled, you need to configure OpenAI credentials at the **database level** (not application level):

**Option A: Via AuraDB Console (Recommended)**

1. In the GenAI plugin settings, find "API Keys" section
2. Add OpenAI API key:
   - Provider: `openai`
   - API Key: `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`
3. Save configuration

**Option B: Via Cypher Query**

If console configuration isn't available, configure via Cypher:

```cypher
CALL ai.config.set('openai.apiKey', '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');
```

### 6. Wait for Plugin Activation

- The GenAI plugin takes **2-3 minutes** to fully activate
- Monitor the plugin status in the console
- Status should change from "Installing" → "Active"

### 7. Verify Plugin is Working

**Via Neo4j Browser:**

1. Open Neo4j Browser (from AuraDB console)
2. Run test query:

```cypher
RETURN ai.text.embed("Hello world") AS embedding;
```

**Expected Result**: Array of 1536 floats (embedding vector)

**If Error**: "Unknown function 'ai.text.embed'" → Wait longer, plugin not fully activated yet

**Via Command Line (from application server):**

```bash
poetry run python -c "
import asyncio
from neo4j import AsyncGraphDatabase
import os

async def test():
    driver = AsyncGraphDatabase.driver(
        os.getenv('NEO4J_URI'),
        auth=('neo4j', os.getenv('NEO4J_PASSWORD'))
    )
    async with driver.session() as session:
        result = await session.run('RETURN ai.text.embed(\"test\") AS e')
        record = await result.single()
        print(f'✅ GenAI plugin working! Embedding dimension: {len(record[\"e\"])}')
    await driver.close()

asyncio.run(test())
"
```

### 8. Configure Embedding Model (Optional)

The default model is `text-embedding-ada-002`. To use `text-embedding-3-small` (recommended):

```cypher
CALL ai.config.set('openai.embedding.model', 'text-embedding-3-small');
CALL ai.config.set('openai.embedding.dimension', 1536);
```

---

## Troubleshooting

### Plugin Not Appearing

**Problem**: GenAI plugin not visible in plugin list

**Solution**:
- Ensure you're on an AuraDB instance (not self-hosted Neo4j)
- GenAI plugin is AuraDB-exclusive feature
- For self-hosted: Download plugin from https://neo4j.com/docs/genai/current/

### Plugin Stuck "Installing"

**Problem**: Plugin status stuck at "Installing" for >5 minutes

**Solution**:
1. Refresh the page
2. Check AuraDB status page for outages
3. Contact Neo4j support if issue persists

### "Unknown function 'ai.text.embed'" Error

**Problem**: Query fails even after plugin shows "Active"

**Solutions**:
1. Wait 2-3 more minutes (activation is asynchronous)
2. Disconnect and reconnect to database
3. Restart application connections
4. Verify API key configured correctly

### Embedding Generation Fails

**Problem**: `ai.text.embed()` returns error

**Common Causes**:
1. OpenAI API key not configured
2. API key invalid or expired
3. OpenAI rate limits exceeded
4. Network connectivity issues

**Verify OpenAI Key**:
```cypher
CALL ai.config.list() YIELD key, value
WHERE key CONTAINS 'openai'
RETURN key, value;
```

### Rate Limiting

**Problem**: Embeddings fail intermittently

**Solution**:
- Reduce batch size in `services_bootstrap.py`:
  ```python
  embedding_worker = EmbeddingBackgroundWorker(
      batch_size=10,  # Reduce from 25
      batch_interval_seconds=60,  # Increase from 30
  )
  ```
- Upgrade OpenAI API tier if needed

---

## Verification Checklist

After enabling the plugin, verify:

- [ ] Plugin status shows "Active" in AuraDB console
- [ ] `ai.text.embed("test")` returns 1536-dimension vector
- [ ] `ai.config.list()` shows OpenAI API key configured
- [ ] Application logs show: "✅ Neo4j GenAI embeddings service created"
- [ ] No errors in application startup logs
- [ ] Worker starts: "✅ Embedding background worker started"

---

## Next Steps

Once GenAI plugin is verified:

1. **Run Production Deployment Checklist**:
   ```bash
   ./scripts/production/deploy_checklist.sh
   ```

2. **Monitor Worker Metrics**:
   ```bash
   curl http://localhost:8000/api/monitoring/embedding-worker
   ```

3. **Create Test Entity**:
   - Create a task via UI or API
   - Wait 35 seconds
   - Check if embedding was generated

4. **Validate Semantic Search**:
   - Search for tasks using semantic mode
   - Verify results include semantically similar tasks

---

## Security Notes

**API Key Storage**:
- ✅ GOOD: Configured at AuraDB database level (encrypted, managed by Neo4j)
- ⚠️ AVOID: Passing API key in every query (security risk)
- ❌ NEVER: Commit API keys to git

**Best Practices**:
- Use separate OpenAI keys per environment (dev/staging/prod)
- Rotate keys quarterly
- Monitor OpenAI usage dashboard for anomalies
- Set up OpenAI spending limits

---

## Cost Monitoring

**OpenAI Embeddings Pricing**: ~$0.02 per 1M tokens

**Monthly Cost Estimate**:
- 1,000 entities/day × 200 chars avg = 6M chars/month
- ~1.5M tokens/month
- **Cost**: ~$0.03/month (negligible)

**At Scale (10,000 entities/day)**:
- ~15M tokens/month
- **Cost**: ~$0.30/month

**Recommendation**: Set up OpenAI usage alerts at $5/month threshold

---

## Support

**Neo4j GenAI Documentation**: https://neo4j.com/docs/genai/current/
**OpenAI API Documentation**: https://platform.openai.com/docs/guides/embeddings
**AuraDB Support**: https://console.neo4j.io/support

**SKUEL-Specific Issues**:
- Check logs: `tail -f logs/skuel.log | grep "embedding"`
- Check worker metrics: `GET /api/monitoring/embedding-worker`
- Review: `/docs/PRODUCTION_DEPLOYMENT_GUIDE.md`

---

**Last Updated**: January 30, 2026
**Status**: Production Ready (awaiting GenAI plugin enablement)
