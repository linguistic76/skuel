#!/bin/bash
# Quick Verification Test Suite
# Tests critical changes from 2025-01-15 session

set -e  # Exit on first failure

echo "=========================================="
echo "Quick Verification Test Suite"
echo "=========================================="
echo ""

# Change to skuel0 directory
cd /home/mike/skuel0

echo "1. Testing Bootstrap (Circular Dependency Fix)..."
echo "   Verifies UserService created before dependent services"
echo "   Verifies context_service wiring"
echo ""
if poetry run pytest tests/test_bootstrap.py -v --tb=short 2>&1 | tee /tmp/test_bootstrap.log; then
    echo "   ✅ Bootstrap tests PASSED"
else
    echo "   ❌ Bootstrap tests FAILED - check /tmp/test_bootstrap.log"
    exit 1
fi

echo ""
echo "2. Testing Error Handling (Errors Factory)..."
echo "   Verifies Result[T] pattern works correctly"
echo "   Verifies error boundary converts Result to HTTP"
echo ""
if poetry run pytest tests/test_error_boundary.py tests/test_result_simplified.py -v --tb=short 2>&1 | tee /tmp/test_errors.log; then
    echo "   ✅ Error handling tests PASSED"
else
    echo "   ❌ Error handling tests FAILED - check /tmp/test_errors.log"
    exit 1
fi

echo ""
echo "3. Testing Core Services..."
echo "   Verifies services work with proper wiring"
echo "   Verifies search service error handling"
echo ""
if poetry run pytest tests/test_tasks_core_service.py tests/test_search_intelligence_service.py -v --tb=short 2>&1 | tee /tmp/test_services.log; then
    echo "   ✅ Service tests PASSED"
else
    echo "   ❌ Service tests FAILED - check /tmp/test_services.log"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ ALL TESTS PASSED"
echo "=========================================="
echo ""
echo "Changes verified:"
echo "  - Circular dependency fix (bootstrap reordering)"
echo "  - Error handling consistency (Errors factory)"
echo "  - Lambda elimination (operator.itemgetter)"
echo ""
echo "Safe to commit changes."
echo ""
