#!/bin/bash
# Script to add metadata field to domain models

DOMAINS="principle choice lp ls"
FINANCE_DOMAINS="expense"

for domain in $DOMAINS; do
    echo "Processing $domain..."

    # DTO file
    dto_file="/home/mike/skuel/app/core/models/${domain}/${domain}_dto.py"

    # Model file
    model_file="/home/mike/skuel/app/core/models/${domain}/${domain}.py"

    # Check if files exist
    if [ -f "$dto_file" ] && [ -f "$model_file" ]; then
        echo "  Found DTO and Model for $domain"
    else
        echo "  WARNING: Missing files for $domain"
    fi
done

# Handle finance/expense separately
echo "Processing expense..."
dto_file="/home/mike/skuel/app/core/models/finance/expense_dto.py"
model_file="/home/mike/skuel/app/core/models/finance/expense.py"
if [ -f "$dto_file" ] && [ -f "$model_file" ]; then
    echo "  Found DTO and Model for expense"
else
    echo "  WARNING: Missing files for expense"
fi
