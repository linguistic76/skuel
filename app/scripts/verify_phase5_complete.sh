#!/bin/bash
# Phase 5 Verification Script
# Checks all integration points are complete

# Don't exit on error - we want to see all results
set +e

echo "🔍 Phase 5: Lateral Relationships - Verification Script"
echo "=========================================================="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Success/Failure counters
SUCCESS=0
FAILED=0

# Helper function for checks
check() {
    local description=$1
    local command=$2

    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✅${NC} $description"
        ((SUCCESS++))
    else
        echo -e "${RED}❌${NC} $description"
        ((FAILED++))
    fi
}

# 1. Service Layer
echo "1️⃣  Service Layer"
echo "-------------------"
check "LateralRelationshipService exists" \
    "grep -q 'class LateralRelationshipService' /home/mike/skuel/app/core/services/lateral_relationships/lateral_relationship_service.py"
check "get_blocking_chain method exists" \
    "grep -q 'async def get_blocking_chain' /home/mike/skuel/app/core/services/lateral_relationships/lateral_relationship_service.py"
check "get_alternatives_with_comparison method exists" \
    "grep -q 'async def get_alternatives_with_comparison' /home/mike/skuel/app/core/services/lateral_relationships/lateral_relationship_service.py"
check "get_relationship_graph method exists" \
    "grep -q 'async def get_relationship_graph' /home/mike/skuel/app/core/services/lateral_relationships/lateral_relationship_service.py"
echo ""

# 2. API Layer
echo "2️⃣  API Layer"
echo "-------------------"
check "LateralRouteFactory exists" \
    "grep -q 'class LateralRouteFactory' /home/mike/skuel/app/core/infrastructure/routes/lateral_route_factory.py"
check "chain route exists" \
    "grep -q '_create_chain_route' /home/mike/skuel/app/core/infrastructure/routes/lateral_route_factory.py"
check "alternatives/compare route exists" \
    "grep -q '_create_comparison_route' /home/mike/skuel/app/core/infrastructure/routes/lateral_route_factory.py"
check "graph route exists" \
    "grep -q '_create_graph_route' /home/mike/skuel/app/core/infrastructure/routes/lateral_route_factory.py"
check "lateral_routes.py exists" \
    "test -f /home/mike/skuel/app/adapters/inbound/lateral_routes.py"
check "lateral routes registered in bootstrap" \
    "grep -q 'create_lateral_routes' /home/mike/skuel/app/scripts/dev/bootstrap.py"
echo ""

# 3. UI Components
echo "3️⃣  UI Components"
echo "-------------------"
check "EntityRelationshipsSection exists" \
    "grep -q 'def EntityRelationshipsSection' /home/mike/skuel/app/ui/patterns/relationships/relationship_section.py"
check "BlockingChainView exists" \
    "grep -q 'def BlockingChainView' /home/mike/skuel/app/ui/patterns/relationships/blocking_chain.py"
check "AlternativesComparisonGrid exists" \
    "grep -q 'def AlternativesComparisonGrid' /home/mike/skuel/app/ui/patterns/relationships/alternatives_grid.py"
check "RelationshipGraphView exists" \
    "grep -q 'def RelationshipGraphView' /home/mike/skuel/app/ui/patterns/relationships/relationship_graph.py"
echo ""

# 4. Domain Integration (9 domains)
echo "4️⃣  Domain Integration (9 domains)"
echo "-----------------------------------"
check "Tasks integration" \
    "grep -q 'EntityRelationshipsSection' /home/mike/skuel/app/adapters/inbound/tasks_ui.py"
check "Goals integration" \
    "grep -q 'EntityRelationshipsSection' /home/mike/skuel/app/adapters/inbound/goals_ui.py"
check "Habits integration" \
    "grep -q 'EntityRelationshipsSection' /home/mike/skuel/app/adapters/inbound/habits_ui.py"
check "Events integration" \
    "grep -q 'EntityRelationshipsSection' /home/mike/skuel/app/adapters/inbound/events_ui.py"
check "Choices integration" \
    "grep -q 'EntityRelationshipsSection' /home/mike/skuel/app/adapters/inbound/choice_ui.py"
check "Principles integration" \
    "grep -q 'EntityRelationshipsSection' /home/mike/skuel/app/components/principles_views.py"
check "KU integration in learning_ui.py" \
    "grep -q 'entity_type=\"ku\"' /home/mike/skuel/app/adapters/inbound/learning_ui.py"
check "LS integration in learning_ui.py" \
    "grep -q 'entity_type=\"ls\"' /home/mike/skuel/app/adapters/inbound/learning_ui.py"
check "LP integration in learning_ui.py" \
    "grep -q 'entity_type=\"lp\"' /home/mike/skuel/app/adapters/inbound/learning_ui.py"
echo ""

# 5. Vis.js Integration
echo "5️⃣  Vis.js Integration"
echo "------------------------"
check "vis-network.min.js exists" \
    "test -f /home/mike/skuel/app/static/vendor/vis-network/vis-network.min.js"
check "vis-network.min.css exists" \
    "test -f /home/mike/skuel/app/static/vendor/vis-network/vis-network.min.css"
check "Vis.js included in base_page.py" \
    "grep -q 'vis-network' /home/mike/skuel/app/ui/layouts/base_page.py"
check "relationshipGraph Alpine component exists" \
    "grep -q 'relationshipGraph' /home/mike/skuel/app/static/js/skuel.js"
echo ""

# 6. Tests
echo "6️⃣  Unit Tests"
echo "----------------"
check "Lateral graph queries test file exists" \
    "test -f /home/mike/skuel/app/tests/unit/test_lateral_graph_queries.py"
check "TestGetBlockingChain exists" \
    "grep -q 'class TestGetBlockingChain' /home/mike/skuel/app/tests/unit/test_lateral_graph_queries.py"
check "TestGetAlternativesWithComparison exists" \
    "grep -q 'class TestGetAlternativesWithComparison' /home/mike/skuel/app/tests/unit/test_lateral_graph_queries.py"
check "TestGetRelationshipGraph exists" \
    "grep -q 'class TestGetRelationshipGraph' /home/mike/skuel/app/tests/unit/test_lateral_graph_queries.py"
echo ""

# Summary
echo "=========================================================="
echo -e "✅ Passed: ${GREEN}${SUCCESS}${NC}"
echo -e "❌ Failed: ${RED}${FAILED}${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}🎉 Phase 5 Integration: COMPLETE${NC}"
    echo ""
    echo "Next steps (manual testing):"
    echo "1. Start server: poetry run python main.py"
    echo "2. Test API endpoints: curl http://localhost:5001/api/tasks/{uid}/lateral/chain"
    echo "3. Test UI: Navigate to /tasks/{uid} and verify Relationships section"
    exit 0
else
    echo -e "${RED}⚠️  Phase 5 Integration: INCOMPLETE${NC}"
    echo "Please review failed checks above"
    exit 1
fi
