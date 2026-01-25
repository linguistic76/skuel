#!/bin/bash
# Master script to apply all improvements to a domain file

set -e  # Exit on error

if [ $# -lt 2 ]; then
    echo "Usage: ./apply_all_improvements.sh <domain> <file_path>"
    echo "Example: ./apply_all_improvements.sh goals goals_ui.py"
    exit 1
fi

DOMAIN=$1
FILE=$2

echo "=========================================="
echo "Applying improvements to ${DOMAIN} domain"
echo "File: ${FILE}"
echo "=========================================="
echo ""

# Backup original file
cp ${FILE} ${FILE}.backup
echo "✓ Created backup: ${FILE}.backup"
echo ""

# Step 1: Add type annotations
echo "Step 1: Adding type annotations..."
python3 add_type_annotations.py ${FILE}
echo ""

# Step 2: Add validation
echo "Step 2: Adding validation function..."
python3 add_validation.py ${DOMAIN} ${FILE}
echo ""

# Step 3: Extract god helper (TODO placeholders)
echo "Step 3: Extracting god helper functions..."
python3 refactor_god_helper.py ${DOMAIN} ${FILE}
echo ""

# Verify syntax
echo "Verifying Python syntax..."
python3 -m py_compile ${FILE}
if [ $? -eq 0 ]; then
    echo "✓ Syntax valid"
else
    echo "✗ Syntax error - restoring backup"
    mv ${FILE}.backup ${FILE}
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ Automated improvements applied!"
echo "=========================================="
echo ""
echo "⚠️  MANUAL STEPS REQUIRED:"
echo ""
echo "1. Implement helper function logic in:"
echo "   - compute_${DOMAIN}_stats()"
echo "   - apply_${DOMAIN}_filters()"
echo "   - apply_${DOMAIN}_sort()"
echo ""
echo "2. Update get_filtered_${DOMAIN}s() to call helpers:"
echo "   - stats = compute_${DOMAIN}_stats(${DOMAIN}s)"
echo "   - filtered = apply_${DOMAIN}_filters(${DOMAIN}s, ...)"
echo "   - sorted = apply_${DOMAIN}_sort(filtered, sort_by)"
echo ""
echo "3. Add validation call in create_${DOMAIN}_from_form():"
echo "   - validation_result = validate_${DOMAIN}_form_data(form_data)"
echo "   - if validation_result.is_error: return validation_result"
echo ""
echo "4. Add Request type hints to helper functions:"
echo "   - parse_filters(request: Request)"
echo "   - parse_calendar_params(request: Request)"
echo ""
echo "Reference: tasks_ui.py for complete examples"
echo ""
