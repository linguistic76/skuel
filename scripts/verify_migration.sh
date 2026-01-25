#!/bin/bash

echo "========================================="
echo "Route Migration Verification Suite"
echo "========================================="
echo ""

PASS=0
FAIL=0

# Tier 1: Static Analysis
echo "=== Tier 1: Static Analysis ==="

# 1.1 response_helpers deleted
if [ ! -f app/adapters/inbound/response_helpers.py ]; then
    echo "✅ response_helpers.py deleted"
    ((PASS++))
else
    echo "❌ response_helpers.py still exists"
    ((FAIL++))
fi

# 1.1 No imports
if ! grep -r "response_helpers" app/adapters/inbound/ 2>/dev/null | grep -v ".pyc" | grep -v "coverage.xml" | grep -q .; then
    echo "✅ Zero response_helpers imports"
    ((PASS++))
else
    echo "❌ Found response_helpers imports"
    ((FAIL++))
fi

# 1.2 Files in correct location
FILES=(
    "app/adapters/inbound/orchestration_routes.py"
    "app/adapters/inbound/advanced_routes.py"
    "app/adapters/inbound/report_routes.py"
    "app/adapters/inbound/finance_api.py"
    "app/adapters/inbound/assignments_api.py"
    "app/adapters/inbound/journals_api.py"
)

ALL_EXIST=true
for file in "${FILES[@]}"; do
    if [ ! -f "$file" ]; then
        ALL_EXIST=false
        echo "❌ Missing: $file"
    fi
done

if $ALL_EXIST; then
    echo "✅ All 6 route files in /adapters/inbound/"
    ((PASS++))
else
    ((FAIL++))
fi

# 1.3 @boundary_handler count
FINANCE_COUNT=$(grep -c "@boundary_handler" app/adapters/inbound/finance_api.py 2>/dev/null || echo 0)
ASSIGNMENTS_COUNT=$(grep -c "@boundary_handler" app/adapters/inbound/assignments_api.py 2>/dev/null || echo 0)
JOURNALS_COUNT=$(grep -c "@boundary_handler" app/adapters/inbound/journals_api.py 2>/dev/null || echo 0)

# Actual counts after migration: finance(12) assignments(6) journals(21)
if [ $FINANCE_COUNT -ge 12 ] && [ $ASSIGNMENTS_COUNT -ge 6 ] && [ $JOURNALS_COUNT -ge 21 ]; then
    echo "✅ @boundary_handler counts: finance($FINANCE_COUNT) assignments($ASSIGNMENTS_COUNT) journals($JOURNALS_COUNT)"
    ((PASS++))
else
    echo "❌ @boundary_handler counts incorrect: finance($FINANCE_COUNT) assignments($ASSIGNMENTS_COUNT) journals($JOURNALS_COUNT)"
    ((FAIL++))
fi

# 1.4 Result[Any] return types
RESULT_COUNT=$(grep -r "Result\[" app/adapters/inbound/finance_api.py app/adapters/inbound/assignments_api.py app/adapters/inbound/journals_api.py 2>/dev/null | wc -l)

# Should have Result[Any] return types on all migrated routes (39 total: 12+6+21)
if [ $RESULT_COUNT -ge 39 ]; then
    echo "✅ Result[Any] return types: $RESULT_COUNT"
    ((PASS++))
else
    echo "❌ Result[Any] return types: $RESULT_COUNT (expected 39+)"
    ((FAIL++))
fi

# 1.5 Temp file cleanup
if grep -q "def cleanup_temp_file" app/adapters/inbound/assignments_api.py && \
   grep -q "background=BackgroundTask" app/adapters/inbound/assignments_api.py; then
    echo "✅ Temp file cleanup implemented"
    ((PASS++))
else
    echo "❌ Temp file cleanup missing"
    ((FAIL++))
fi

# 1.6 File upload validation
if grep -q "100_000_000" app/adapters/inbound/assignments_api.py; then
    echo "✅ 100MB file size validation"
    ((PASS++))
else
    echo "❌ File size validation missing"
    ((FAIL++))
fi

# 1.7 Journal route paths
OLD_PATHS=$(grep '@rt("/api/assignments/' app/adapters/inbound/journals_api.py 2>/dev/null | wc -l)
NEW_PATHS=$(grep '@rt("/api/journals/' app/adapters/inbound/journals_api.py 2>/dev/null | wc -l)

if [ "$OLD_PATHS" -eq 0 ] && [ "$NEW_PATHS" -ge 20 ]; then
    echo "✅ Journal routes migrated to /api/journals/* ($NEW_PATHS routes)"
    ((PASS++))
else
    echo "❌ Journal route paths incorrect (old:$OLD_PATHS new:$NEW_PATHS)"
    ((FAIL++))
fi

echo ""
echo "=== Tier 2: Import Verification ==="

# 2.1 Import all route modules
if (cd app && poetry run python -c "
from adapters.inbound.orchestration_routes import create_orchestration_routes
from adapters.inbound.advanced_routes import create_advanced_routes
from adapters.inbound.report_routes import create_report_routes
from adapters.inbound.finance_api import create_finance_api_routes
from adapters.inbound.assignments_api import create_assignments_api_routes
from adapters.inbound.journals_api import create_journals_api_routes
") 2>/dev/null; then
    echo "✅ All route modules import successfully"
    ((PASS++))
else
    echo "❌ Route import errors"
    ((FAIL++))
fi

# 2.2 Bootstrap imports
if grep -q "from adapters.inbound.orchestration_routes" app/scripts/dev/bootstrap.py && \
   ! grep -q "from routes.api" app/scripts/dev/bootstrap.py; then
    echo "✅ bootstrap.py uses correct imports"
    ((PASS++))
else
    echo "❌ bootstrap.py imports incorrect"
    ((FAIL++))
fi

echo ""
echo "=== Tier 4: Metrics & Compliance ==="

# 4.1 Zero response_helpers usage
HELPER_USAGE=$(grep -r "response_helpers" app/adapters/inbound/ 2>/dev/null | grep -v ".pyc" | grep -v "coverage.xml" | wc -l)
if [ $HELPER_USAGE -eq 0 ]; then
    echo "✅ Zero response_helpers usage"
    ((PASS++))
else
    echo "❌ Found $HELPER_USAGE response_helpers references"
    ((FAIL++))
fi

# 4.2 Old routes directory cleanup
if [ ! -d app/routes/api/ ] || [ -z "$(ls -A app/routes/api/ 2>/dev/null | grep -v __pycache__)" ]; then
    echo "✅ /routes/api/ cleaned up"
    ((PASS++))
else
    echo "❌ /routes/api/ still contains files"
    ((FAIL++))
fi

# 4.3 Total @boundary_handler count
TOTAL_BOUNDARY=$(grep -r "@boundary_handler" app/adapters/inbound/ 2>/dev/null | grep -v ".pyc" | wc -l)
if [ $TOTAL_BOUNDARY -ge 30 ]; then
    echo "✅ Total @boundary_handler decorators: $TOTAL_BOUNDARY"
    ((PASS++))
else
    echo "❌ Total @boundary_handler decorators: $TOTAL_BOUNDARY (expected 30+)"
    ((FAIL++))
fi

# 4.4 Zero legacy response calls (in migrated files only)
LEGACY_CALLS=$(grep -E "(error_response|success_response)\(" \
    app/adapters/inbound/finance_api.py \
    app/adapters/inbound/assignments_api.py \
    app/adapters/inbound/journals_api.py \
    app/adapters/inbound/orchestration_routes.py \
    app/adapters/inbound/advanced_routes.py \
    app/adapters/inbound/report_routes.py \
    2>/dev/null | wc -l)
if [ $LEGACY_CALLS -eq 0 ]; then
    echo "✅ Zero legacy response calls in migrated files"
    ((PASS++))
else
    echo "❌ Found $LEGACY_CALLS legacy response calls in migrated files"
    ((FAIL++))
fi

# 4.5 Verify critical files don't exist
DELETED_FILES=(
    "app/adapters/inbound/response_helpers.py"
    "app/routes/api/orchestration_routes.py"
    "app/routes/api/advanced_routes.py"
    "app/routes/api/report_routes.py"
    "app/adapters/inbound/assignments_content_api.py"
)

ALL_DELETED=true
for file in "${DELETED_FILES[@]}"; do
    if [ -f "$file" ]; then
        ALL_DELETED=false
        echo "❌ File should be deleted: $file"
    fi
done

if $ALL_DELETED; then
    echo "✅ All legacy files properly deleted"
    ((PASS++))
else
    ((FAIL++))
fi

# 4.6 Function renames
if grep -q "def create_journals_api_routes" app/adapters/inbound/journals_api.py && \
   ! grep -q "def create_assignments_content_api_routes" app/adapters/inbound/journals_api.py; then
    echo "✅ Journal routes function properly renamed"
    ((PASS++))
else
    echo "❌ Journal routes function rename incomplete"
    ((FAIL++))
fi

echo ""
echo "========================================="
echo "Results: $PASS passed, $FAIL failed"
echo "========================================="

if [ $FAIL -eq 0 ]; then
    echo "✅ ALL CHECKS PASSED - Migration verified successfully!"
    exit 0
else
    echo "❌ SOME CHECKS FAILED - Review output above"
    exit 1
fi
