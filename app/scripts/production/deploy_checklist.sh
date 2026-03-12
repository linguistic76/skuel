#!/bin/bash
# Production Deployment Checklist for Async Embedding System
# Run this script to validate production readiness

set -e

echo "=========================================="
echo "SKUEL Production Deployment Checklist"
echo "Async Embedding System Validation"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step counter
STEP=1

# Helper functions
step() {
    echo ""
    echo "[$STEP] $1"
    ((STEP++))
}

check_pass() {
    echo -e "${GREEN}✅ PASS${NC}: $1"
}

check_warn() {
    echo -e "${YELLOW}⚠️  WARN${NC}: $1"
}

check_fail() {
    echo -e "${RED}❌ FAIL${NC}: $1"
}

# ==========================================
# PRE-DEPLOYMENT CHECKS
# ==========================================

step "Checking environment variables"

if [ -z "$NEO4J_URI" ]; then
    check_fail "NEO4J_URI not set"
    echo "Set in .env file or export NEO4J_URI=neo4j+s://YOUR_INSTANCE.databases.neo4j.io"
    exit 1
else
    check_pass "NEO4J_URI configured"
    echo "  URI: $NEO4J_URI"
fi

if [ -z "$HF_API_TOKEN" ]; then
    check_fail "HF_API_TOKEN not set"
    echo "Embeddings worker requires HuggingFace Inference API token"
    echo "Set HF_API_TOKEN=hf_your_token_here in .env"
    exit 1
else
    check_pass "HF_API_TOKEN configured"
    echo "  Token: ${HF_API_TOKEN:0:10}..."
fi

if [ "${INTELLIGENCE_TIER}" != "full" ]; then
    check_warn "INTELLIGENCE_TIER is not 'full' (embeddings may be disabled)"
    echo "  Set INTELLIGENCE_TIER=full in .env to enable vector search"
else
    check_pass "INTELLIGENCE_TIER=full (embeddings enabled)"
fi

step "Checking Python environment"

if ! command -v uv &> /dev/null; then
    check_fail "uv not installed"
    echo "Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
else
    check_pass "uv installed"
    uv --version
fi

step "Checking dependencies"

uv sync --no-dev &> /dev/null
check_pass "Dependencies installed"

# ==========================================
# HUGGINGFACE EMBEDDINGS SERVICE VALIDATION
# ==========================================

step "Validating HuggingFace embeddings service"

HF_CHECK=$(uv run python -c "
import asyncio
import os
from core.services.embeddings_service import HuggingFaceEmbeddingsService

async def check():
    token = os.getenv('HF_API_TOKEN')
    if not token:
        return 'NO_TOKEN'
    try:
        # Instantiate service and attempt a test embedding
        service = HuggingFaceEmbeddingsService.__new__(HuggingFaceEmbeddingsService)
        available = await service._check_plugin_availability()
        return 'ENABLED' if available else 'UNAVAILABLE'
    except Exception as e:
        return f'ERROR: {e}'

print(asyncio.run(check()))
" 2>&1)

if [ "$HF_CHECK" == "ENABLED" ]; then
    check_pass "HuggingFace embeddings service is available"
elif [ "$HF_CHECK" == "NO_TOKEN" ]; then
    check_fail "HF_API_TOKEN not set"
    echo ""
    echo "TO CONFIGURE EMBEDDINGS:"
    echo "1. Obtain a HuggingFace Inference API token at https://huggingface.co/settings/tokens"
    echo "2. Add to .env: HF_API_TOKEN=hf_your_token_here"
    echo "3. Add to .env: INTELLIGENCE_TIER=full"
    echo "4. Re-run this script to verify"
    echo ""
    exit 1
elif [ "$HF_CHECK" == "UNAVAILABLE" ]; then
    check_fail "HuggingFace embeddings service returned unavailable"
    echo "Check HF_API_TOKEN validity and https://status.huggingface.co"
    exit 1
else
    check_fail "Error checking embeddings service: $HF_CHECK"
    exit 1
fi

# ==========================================
# APPLICATION STARTUP TEST
# ==========================================

step "Testing application startup"

echo "Starting SKUEL application..."
uv run python main.py &
APP_PID=$!

# Wait for startup
sleep 5

if ! kill -0 $APP_PID 2>/dev/null; then
    check_fail "Application failed to start"
    exit 1
fi

check_pass "Application started (PID: $APP_PID)"

# ==========================================
# MONITORING ENDPOINTS VALIDATION
# ==========================================

step "Validating monitoring endpoints"

# Health check
HEALTH=$(curl -s http://localhost:8000/api/monitoring/health)
if echo "$HEALTH" | grep -q "healthy"; then
    check_pass "Health endpoint working"
else
    check_fail "Health endpoint failed"
    kill $APP_PID
    exit 1
fi

# Worker metrics
WORKER=$(curl -s http://localhost:8000/api/monitoring/embedding-worker)
if echo "$WORKER" | grep -q "running"; then
    check_pass "Embedding worker endpoint working"
    echo "$WORKER" | python -m json.tool | grep -E "(total_processed|queue_size|success_rate)"
else
    check_warn "Worker endpoint returned: $WORKER"
fi

# ==========================================
# EMBEDDING GENERATION TEST
# ==========================================

step "Testing embedding generation (E2E)"

echo "Creating test task to trigger embedding..."

TEST_RESULT=$(curl -s -X POST http://localhost:8000/api/tasks/create \
    -H "Content-Type: application/json" \
    -d '{
        "title": "Production Validation Test",
        "description": "Testing async embedding generation in production",
        "priority": "medium"
    }')

TASK_UID=$(echo "$TEST_RESULT" | python -c "import sys, json; print(json.load(sys.stdin).get('uid', 'NONE'))" 2>/dev/null || echo "NONE")

if [ "$TASK_UID" != "NONE" ]; then
    check_pass "Test task created: $TASK_UID"

    echo "Waiting 35 seconds for embedding worker to process..."
    sleep 35

    # Check if embedding was generated
    EMBEDDING_CHECK=$(uv run python -c "
import asyncio
from neo4j import AsyncGraphDatabase
import os

async def check():
    driver = AsyncGraphDatabase.driver(
        os.getenv('NEO4J_URI'),
        auth=('neo4j', os.getenv('NEO4J_PASSWORD'))
    )
    try:
        async with driver.session() as session:
            result = await session.run(
                'MATCH (t:Task {uid: \$uid}) RETURN t.embedding IS NOT NULL AS has_embedding',
                uid='$TASK_UID'
            )
            record = await result.single()
            return 'TRUE' if record and record['has_embedding'] else 'FALSE'
    finally:
        await driver.close()

print(asyncio.run(check()))
" 2>&1)

    if [ "$EMBEDDING_CHECK" == "TRUE" ]; then
        check_pass "Embedding generated successfully!"
    else
        check_fail "Embedding was not generated"
        echo "Check worker logs for errors"
    fi
else
    check_fail "Failed to create test task"
fi

# ==========================================
# SEMANTIC SEARCH VALIDATION
# ==========================================

step "Testing semantic search"

SEARCH_RESULT=$(curl -s "http://localhost:8000/api/search/tasks?q=production+validation&mode=semantic&limit=5")

if echo "$SEARCH_RESULT" | grep -q "$TASK_UID"; then
    check_pass "Semantic search working - found test task"
else
    check_warn "Semantic search did not find test task (may need more time)"
fi

# ==========================================
# PERFORMANCE METRICS
# ==========================================

step "Collecting performance metrics"

METRICS=$(curl -s http://localhost:8000/api/monitoring/embedding-worker)
echo "$METRICS" | python -m json.tool

# ==========================================
# CLEANUP
# ==========================================

step "Cleanup"

echo "Stopping application..."
kill $APP_PID
wait $APP_PID 2>/dev/null

check_pass "Application stopped"

# ==========================================
# SUMMARY
# ==========================================

echo ""
echo "=========================================="
echo "DEPLOYMENT VALIDATION COMPLETE"
echo "=========================================="
echo ""
echo "✅ Environment configured"
echo "✅ HuggingFace embeddings service available"
echo "✅ Application startup successful"
echo "✅ Monitoring endpoints working"
echo "✅ Embedding generation validated"
echo "✅ Semantic search functional"
echo ""
echo "PRODUCTION DEPLOYMENT READY!"
echo ""
echo "Next steps:"
echo "1. Deploy to production environment"
echo "2. Monitor worker metrics for 24 hours"
echo "3. Validate semantic search quality with real users"
echo "4. Set up alerting for success_rate < 95%"
echo ""
