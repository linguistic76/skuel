#!/bin/bash
# GraphQL Implementation Test Script
# ====================================
# Tests all GraphQL features including authentication, DataLoader, and read-only design

set -e  # Exit on error

BASE_URL="http://localhost:8000"
GRAPHQL_ENDPOINT="$BASE_URL/graphql"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "GraphQL Implementation Test Suite"
echo "=========================================="
echo ""

# Test 1: Test Authentication Requirement
echo -e "${YELLOW}Test 1: Authentication Requirement${NC}"
echo "Testing unauthenticated request (should fail with 401)..."
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "query { tasks { uid } }"}')

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "401" ]; then
    echo -e "${GREEN}✅ PASS: Unauthenticated request rejected (401)${NC}"
    echo "Response: $BODY"
else
    echo -e "${RED}❌ FAIL: Expected 401, got $HTTP_CODE${NC}"
    echo "Response: $BODY"
fi
echo ""

# Test 2: Test Read-Only Design (Mutations Disabled)
echo -e "${YELLOW}Test 2: Read-Only Design (Mutations Disabled)${NC}"
echo "Testing mutation placeholder..."
RESPONSE=$(curl -s -X POST "$GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "mutation { placeholder }"}')

if echo "$RESPONSE" | grep -q "Use REST API for mutations"; then
    echo -e "${GREEN}✅ PASS: Mutation returns REST API message${NC}"
    echo "Response: $RESPONSE"
else
    echo -e "${RED}❌ FAIL: Expected mutation placeholder message${NC}"
    echo "Response: $RESPONSE"
fi
echo ""

# Test 3: Test Public Queries (no auth required)
echo -e "${YELLOW}Test 3: Public Queries (Knowledge Units)${NC}"
echo "Testing knowledge units query (public, no auth required)..."
RESPONSE=$(curl -s -X POST "$GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "query { knowledgeUnits(limit: 3) { uid title domain } }"}')

if echo "$RESPONSE" | grep -q '"data"'; then
    echo -e "${GREEN}✅ PASS: Knowledge units query succeeded${NC}"
    echo "Response: $RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
else
    echo -e "${RED}❌ FAIL: Expected data field in response${NC}"
    echo "Response: $RESPONSE"
fi
echo ""

# Test 4: Test Learning Paths with all_paths flag
echo -e "${YELLOW}Test 4: Learning Paths Discovery (all_paths=true)${NC}"
echo "Testing learning paths discovery query (public)..."
RESPONSE=$(curl -s -X POST "$GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "query { learningPaths(allPaths: true, limit: 3) { uid name goal } }"}')

if echo "$RESPONSE" | grep -q '"data"'; then
    echo -e "${GREEN}✅ PASS: Learning paths discovery query succeeded${NC}"
    echo "Response: $RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
else
    echo -e "${RED}❌ FAIL: Expected data field in response${NC}"
    echo "Response: $RESPONSE"
fi
echo ""

# Test 5: Test GraphiQL Playground
echo -e "${YELLOW}Test 5: GraphiQL Playground${NC}"
echo "Testing GraphiQL HTML interface (GET request)..."
RESPONSE=$(curl -s "$GRAPHQL_ENDPOINT")

if echo "$RESPONSE" | grep -q "GraphiQL"; then
    echo -e "${GREEN}✅ PASS: GraphiQL playground accessible${NC}"
    echo "GraphiQL is available at: $GRAPHQL_ENDPOINT"
else
    echo -e "${RED}❌ FAIL: GraphiQL not accessible${NC}"
fi
echo ""

# Test 6: Test Nested Queries (DataLoader)
echo -e "${YELLOW}Test 6: Nested Queries (DataLoader Batching)${NC}"
echo "Testing nested knowledge units with prerequisites..."
RESPONSE=$(curl -s -X POST "$GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "query { knowledgeUnits(limit: 2) { uid title prerequisites { uid title } } }"}')

if echo "$RESPONSE" | grep -q '"prerequisites"'; then
    echo -e "${GREEN}✅ PASS: Nested query with DataLoader succeeded${NC}"
    echo "Response: $RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
    echo ""
    echo "💡 Check server logs for DataLoader metrics:"
    echo "   Look for: 📊 DataLoader batching X knowledge units"
    echo "   Look for: ✅ Batch loaded X knowledge units in 1 query"
else
    echo -e "${RED}❌ FAIL: Expected nested prerequisites data${NC}"
    echo "Response: $RESPONSE"
fi
echo ""

# Test 7: Test Search Query
echo -e "${YELLOW}Test 7: Semantic Search${NC}"
echo "Testing semantic search query..."
RESPONSE=$(curl -s -X POST "$GRAPHQL_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"query": "query { searchKnowledge(input: { query: \"learning\", limit: 3 }) { knowledge { uid title } relevance } }"}')

if echo "$RESPONSE" | grep -q '"data"'; then
    echo -e "${GREEN}✅ PASS: Semantic search query succeeded${NC}"
    echo "Response: $RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
else
    echo -e "${RED}❌ FAIL: Expected data field in response${NC}"
    echo "Response: $RESPONSE"
fi
echo ""

# Summary
echo "=========================================="
echo "Test Suite Complete!"
echo "=========================================="
echo ""
echo "To test authenticated queries, first log in via the web UI:"
echo "1. Visit: $BASE_URL/login"
echo "2. Log in as a user"
echo "3. Get your session cookie from browser dev tools"
echo "4. Test authenticated query:"
echo ""
echo "   curl -X POST $GRAPHQL_ENDPOINT \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -H 'Cookie: session=YOUR_SESSION_COOKIE' \\"
echo "     -d '{\"query\": \"query { tasks { uid title status } }\"}'"
echo ""
echo "=========================================="
echo "DataLoader Metrics Check:"
echo "=========================================="
echo "Check your server logs for DataLoader batching metrics:"
echo "  📊 DataLoader batching N entities"
echo "  ✅ Batch loaded N entities in 1 query"
echo ""
echo "These metrics prove GraphQL is preventing N+1 queries!"
echo "=========================================="
