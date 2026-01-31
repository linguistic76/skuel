#!/bin/bash
# Verification script for Prometheus + Grafana setup
# Usage: ./scripts/verify_monitoring_setup.sh

set -e

echo "🧪 SKUEL Monitoring Setup Verification"
echo "======================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Docker is running
echo "1️⃣  Checking Docker..."
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker is running${NC}"
echo ""

# Check if docker-compose.yml exists
echo "2️⃣  Checking docker-compose.yml..."
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}❌ docker-compose.yml not found${NC}"
    exit 1
fi
echo -e "${GREEN}✅ docker-compose.yml found${NC}"
echo ""

# Check if Prometheus config exists
echo "3️⃣  Checking Prometheus config..."
if [ ! -f "monitoring/prometheus/prometheus.yml" ]; then
    echo -e "${RED}❌ monitoring/prometheus/prometheus.yml not found${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Prometheus config found${NC}"
echo ""

# Check if Grafana provisioning exists
echo "4️⃣  Checking Grafana provisioning..."
if [ ! -f "monitoring/grafana/provisioning/datasources/prometheus.yml" ]; then
    echo -e "${RED}❌ Grafana datasource config not found${NC}"
    exit 1
fi
if [ ! -f "monitoring/grafana/provisioning/dashboards/skuel.yml" ]; then
    echo -e "${RED}❌ Grafana dashboard config not found${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Grafana provisioning configs found${NC}"
echo ""

# Start services (without building app)
echo "5️⃣  Starting Prometheus and Grafana..."
docker compose up -d --no-deps prometheus grafana
echo -e "${GREEN}✅ Services started${NC}"
echo ""

# Wait for services to be ready
echo "6️⃣  Waiting for services to be ready..."
sleep 5

# Check Prometheus health
echo "7️⃣  Checking Prometheus health..."
if curl -sf http://localhost:9090/-/healthy > /dev/null; then
    echo -e "${GREEN}✅ Prometheus is healthy${NC}"
else
    echo -e "${RED}❌ Prometheus is not responding${NC}"
    echo "Logs:"
    docker compose logs prometheus | tail -20
    exit 1
fi
echo ""

# Check Grafana health
echo "8️⃣  Checking Grafana health..."
if curl -sf http://localhost:3000/api/health > /dev/null; then
    echo -e "${GREEN}✅ Grafana is healthy${NC}"
else
    echo -e "${RED}❌ Grafana is not responding${NC}"
    echo "Logs:"
    docker compose logs grafana | tail -20
    exit 1
fi
echo ""

# Check if SKUEL app metrics endpoint is accessible (if app is running)
echo "9️⃣  Checking SKUEL metrics endpoint..."
if curl -sf http://localhost:5001/metrics > /dev/null; then
    echo -e "${GREEN}✅ SKUEL /metrics endpoint is accessible${NC}"

    # Check if Prometheus is scraping
    sleep 10  # Wait for at least one scrape
    echo ""
    echo "🔟 Checking Prometheus target status..."
    TARGET_STATUS=$(curl -s http://localhost:9090/api/v1/targets | grep -o '"health":"[^"]*"' | head -1)
    if echo "$TARGET_STATUS" | grep -q "up"; then
        echo -e "${GREEN}✅ Prometheus is successfully scraping SKUEL app${NC}"
    else
        echo -e "${YELLOW}⚠️  Prometheus target status: $TARGET_STATUS${NC}"
        echo "   This is expected if SKUEL app just started"
    fi
else
    echo -e "${YELLOW}⚠️  SKUEL app is not running (this is OK for setup verification)${NC}"
    echo "   To complete verification, start SKUEL app:"
    echo "   poetry run python main.py"
fi
echo ""

# Summary
echo "📊 Monitoring Stack Status"
echo "=========================="
echo -e "Prometheus UI:     ${GREEN}http://localhost:9090${NC}"
echo -e "Grafana UI:        ${GREEN}http://localhost:3000${NC} (admin/admin)"
echo -e "SKUEL Metrics:     ${GREEN}http://localhost:5001/metrics${NC}"
echo ""

echo -e "${GREEN}✅ Phase 1 setup verification complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Open Grafana: http://localhost:3000"
echo "2. Verify Prometheus datasource (Connections → Data sources)"
echo "3. Open Prometheus: http://localhost:9090"
echo "4. Check targets (Status → Targets)"
echo ""
echo "See monitoring/README.md for detailed usage guide"
