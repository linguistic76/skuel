#!/bin/bash
# Test Observability Phase 1 Implementation
# =========================================
# Verifies that all Phase 1 changes are working correctly.
#
# Usage:
#   ./scripts/test_observability_phase1.sh
#
# Requirements:
#   - Prometheus running on localhost:9090
#   - SKUEL app running on localhost:5001
#   - jq installed (for JSON parsing)

set -e

echo "🧪 Testing Observability Phase 1 Implementation"
echo "================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Helper function for tests
test_step() {
    local test_name="$1"
    local test_command="$2"

    echo -n "Testing: $test_name... "

    if eval "$test_command" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ PASS${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}"
        ((TESTS_FAILED++))
        return 1
    fi
}

echo "📋 Phase 1: Configuration Validation"
echo "------------------------------------"

test_step "Prometheus config valid" \
    "docker run --rm -v $(pwd)/monitoring/prometheus:/etc/prometheus --entrypoint promtool prom/prometheus:v2.50.0 check config /etc/prometheus/prometheus.yml"

test_step "Prometheus dev config valid" \
    "docker run --rm -v $(pwd)/monitoring/prometheus:/etc/prometheus --entrypoint promtool prom/prometheus:v2.50.0 check config /etc/prometheus/prometheus.dev.yml"

test_step "Alert rules valid" \
    "docker run --rm -v $(pwd)/monitoring/prometheus:/etc/prometheus --entrypoint promtool prom/prometheus:v2.50.0 check rules /etc/prometheus/alerts.yml"

echo ""
echo "📋 Phase 2: Prometheus Service"
echo "------------------------------"

test_step "Prometheus is running" \
    "curl -sf http://localhost:9090/-/healthy"

test_step "Prometheus is scraping SKUEL" \
    "curl -sf 'http://localhost:9090/api/v1/targets' | jq -e '.data.activeTargets[] | select(.job == \"skuel-app\") | select(.health == \"up\")'"

test_step "Alert rules loaded (13 expected)" \
    "curl -sf http://localhost:9090/api/v1/rules | jq -e '.data.groups[].rules | length' | grep -q 13"

test_step "skuel_critical alert group exists" \
    "curl -sf http://localhost:9090/api/v1/rules | jq -e '.data.groups[] | select(.name == \"skuel_critical\")'"

echo ""
echo "📋 Phase 3: SKUEL Metrics Endpoint"
echo "----------------------------------"

test_step "SKUEL /metrics endpoint accessible" \
    "curl -sf http://localhost:5001/metrics"

test_step "OpenAI request metric exists" \
    "curl -sf http://localhost:5001/metrics | grep -q 'skuel_openai_requests_total'"

test_step "OpenAI duration metric exists" \
    "curl -sf http://localhost:5001/metrics | grep -q 'skuel_openai_duration_seconds'"

test_step "OpenAI tokens metric exists" \
    "curl -sf http://localhost:5001/metrics | grep -q 'skuel_openai_tokens_total'"

test_step "OpenAI errors metric exists" \
    "curl -sf http://localhost:5001/metrics | grep -q 'skuel_openai_errors_total'"

test_step "Embedding queue size metric exists" \
    "curl -sf http://localhost:5001/metrics | grep -q 'skuel_embedding_queue_size'"

test_step "Embeddings processed metric exists" \
    "curl -sf http://localhost:5001/metrics | grep -q 'skuel_embeddings_processed_total'"

test_step "Embedding batch size metric exists" \
    "curl -sf http://localhost:5001/metrics | grep -q 'skuel_embedding_batch_size'"

echo ""
echo "📋 Phase 4: Alert Definitions"
echo "-----------------------------"

ALERTS=(
    "HighErrorRate"
    "SlowHttpRequests"
    "Neo4jDown"
    "SlowDatabaseQueries"
    "HighDatabaseErrorRate"
    "HighEventHandlerErrorRate"
    "SlowEventHandlers"
    "HighOrphanedEntityCount"
    "LongDependencyChains"
    "HighOpenAIErrorRate"
    "EmbeddingQueueBacklog"
    "HighEmbeddingFailureRate"
    "SlowOpenAICalls"
)

for alert in "${ALERTS[@]}"; do
    test_step "Alert '$alert' defined" \
        "curl -sf http://localhost:9090/api/v1/rules | jq -e '.data.groups[].rules[] | select(.name == \"$alert\")'"
done

echo ""
echo "📋 Phase 5: Metric Cardinality Check"
echo "------------------------------------"

# Check that AI metrics don't have unbounded cardinality
test_step "OpenAI metrics have bounded labels" \
    "curl -sf http://localhost:5001/metrics | grep 'skuel_openai' | grep -v -E 'user_uid|task_uid|goal_uid'"

test_step "Embedding metrics have bounded labels" \
    "curl -sf http://localhost:5001/metrics | grep 'skuel_embedding' | grep -v -E 'user_uid|task_uid|goal_uid'"

echo ""
echo "📋 Phase 6: Documentation Exists"
echo "--------------------------------"

test_step "ALERTING.md exists" \
    "test -f .claude/skills/prometheus-grafana/ALERTING.md"

test_step "SKILL.md updated" \
    "grep -q 'AI Services' .claude/skills/prometheus-grafana/SKILL.md"

test_step "Implementation doc exists" \
    "test -f OBSERVABILITY_PHASE1_COMPLETE.md"

test_step "Changes summary exists" \
    "test -f OBSERVABILITY_CHANGES_SUMMARY.md"

test_step "Validation script exists" \
    "test -x scripts/validate_prometheus_config.sh"

echo ""
echo "================================================"
echo "📊 Test Results Summary"
echo "================================================"
echo ""
echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed! Phase 1 implementation is working correctly.${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Monitor alerts for false positives over 1 week"
    echo "  2. Create AI Services Grafana dashboard"
    echo "  3. Tune alert thresholds if needed"
    exit 0
else
    echo -e "${RED}❌ Some tests failed. Please review the errors above.${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  - Ensure Prometheus is running: docker compose ps prometheus"
    echo "  - Ensure SKUEL app is running: curl http://localhost:5001/metrics"
    echo "  - Check Prometheus logs: docker logs skuel-prometheus"
    echo "  - Reload Prometheus config: docker compose restart prometheus"
    exit 1
fi
