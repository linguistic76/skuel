#!/bin/bash
# Validate Prometheus Configuration and Alerting Rules
# ======================================================
# Uses promtool (bundled with Prometheus) to validate configuration before deployment.
#
# Usage:
#   ./scripts/validate_prometheus_config.sh
#
# Exit codes:
#   0 - All validation passed
#   1 - Validation failed

set -e

echo "🔍 Validating Prometheus configuration..."
echo ""

# Check if running inside Prometheus container or locally
if command -v promtool &> /dev/null; then
    PROMTOOL_CONFIG="promtool check config"
    PROMTOOL_RULES="promtool check rules"
    CONFIG_PATH="monitoring/prometheus"
else
    # Use Docker to run promtool (with correct entrypoint)
    PROMTOOL_CONFIG="docker run --rm -v $(pwd)/monitoring/prometheus:/etc/prometheus --entrypoint promtool prom/prometheus:v2.50.0 check config"
    PROMTOOL_RULES="docker run --rm -v $(pwd)/monitoring/prometheus:/etc/prometheus --entrypoint promtool prom/prometheus:v2.50.0 check rules"
    CONFIG_PATH="/etc/prometheus"
fi

# Validate main prometheus.yml
echo "📋 Checking prometheus.yml..."
$PROMTOOL_CONFIG $CONFIG_PATH/prometheus.yml
if [ $? -eq 0 ]; then
    echo "✅ prometheus.yml is valid"
else
    echo "❌ prometheus.yml validation failed"
    exit 1
fi

echo ""

# Validate prometheus.dev.yml
echo "📋 Checking prometheus.dev.yml..."
$PROMTOOL_CONFIG $CONFIG_PATH/prometheus.dev.yml
if [ $? -eq 0 ]; then
    echo "✅ prometheus.dev.yml is valid"
else
    echo "❌ prometheus.dev.yml validation failed"
    exit 1
fi

echo ""

# Validate alerting rules
echo "📋 Checking alerts.yml..."
$PROMTOOL_RULES $CONFIG_PATH/alerts.yml
if [ $? -eq 0 ]; then
    echo "✅ alerts.yml is valid"
else
    echo "❌ alerts.yml validation failed"
    exit 1
fi

echo ""
echo "🎉 All Prometheus configuration files are valid!"
echo ""
echo "Next steps:"
echo "  1. Restart Prometheus: docker compose restart prometheus"
echo "  2. Check rules loaded: curl http://localhost:9090/api/v1/rules"
echo "  3. View alerts in UI: http://localhost:9090/alerts"
