#!/bin/bash
#
# Install Git hooks for SKUEL
#
# This script installs pre-commit hooks that validate cross-references
# before allowing commits.
#
# Usage:
#   ./scripts/install_git_hooks.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

echo "Installing SKUEL Git hooks..."

# Create pre-commit hook
cat > "$HOOKS_DIR/pre-commit" << 'EOF'
#!/bin/bash
#
# SKUEL Pre-Commit Hook - Cross-Reference Validation
#
# This hook validates cross-references in staged documentation files.
# It will BLOCK commits with:
# - Broken skill references (@skill-name doesn't exist)
# - Broken doc links (/docs/... file doesn't exist)
# - Missing frontmatter in pattern docs
#
# It will WARN (but not block) for:
# - Missing reverse links (doc→skill exists but skill→doc missing)

set -e

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo "🔍 Validating cross-references in staged files..."

# Get staged .md files
STAGED_DOCS=$(git diff --cached --name-only --diff-filter=ACM | grep '\.md$' || true)

if [ -z "$STAGED_DOCS" ]; then
    echo "✓ No documentation files staged, skipping validation"
    exit 0
fi

echo "Checking $(echo "$STAGED_DOCS" | wc -l) staged document(s)..."

# Run validation in errors-only mode
if uv run python scripts/validate_cross_references.py --errors-only; then
    echo -e "${GREEN}✅ Cross-reference validation passed${NC}"
    exit 0
else
    echo -e "${RED}❌ Cross-reference validation failed${NC}"
    echo ""
    echo "Your commit contains broken cross-references that must be fixed."
    echo ""
    echo "To see details:"
    echo "  uv run python scripts/validate_cross_references.py"
    echo ""
    echo "To bypass this check (not recommended):"
    echo "  git commit --no-verify"
    echo ""
    exit 1
fi
EOF

# Make hook executable
chmod +x "$HOOKS_DIR/pre-commit"

echo "✅ Pre-commit hook installed successfully!"
echo ""
echo "The hook will run automatically before each commit to validate:"
echo "  - Broken skill references (@skill-name)"
echo "  - Broken doc links (/docs/...)"
echo "  - Missing frontmatter in pattern docs"
echo ""
echo "To bypass the hook (not recommended):"
echo "  git commit --no-verify"
