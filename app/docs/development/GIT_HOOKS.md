# Git Hooks for SKUEL

**Purpose:** Automated validation of code quality and documentation consistency before commits.

## Installation

```bash
./scripts/install_git_hooks.sh
```

This installs all SKUEL git hooks to `.git/hooks/`.

---

## Pre-Commit Hook: Cross-Reference Validation

**File:** `.git/hooks/pre-commit`

**Purpose:** Prevents commits with broken cross-references between skills and documentation.

### What It Validates

The hook runs automatically before each commit and checks:

✅ **Blocks commits with errors:**
- Broken skill references in metadata (skill doesn't exist)
- Broken doc links (file doesn't exist)
- Missing frontmatter in pattern docs

⚠️ **Warns (but doesn't block):**
- Missing reverse links (one-way references)

### How It Works

1. Detects staged `.md` files
2. Runs validation script in `--errors-only` mode
3. Blocks commit if errors found (exit code 1)
4. Allows commit if only warnings

### Usage

**Normal workflow:**
```bash
git add docs/patterns/NEW_PATTERN.md
git commit -m "Add new pattern"
# Hook runs automatically and validates
```

**If validation fails:**
```bash
❌ Cross-reference validation failed

Your commit contains broken cross-references that must be fixed.

To see details:
  poetry run python scripts/validate_cross_references.py

To bypass this check (not recommended):
  git commit --no-verify
```

**Bypass hook (not recommended):**
```bash
git commit --no-verify -m "Skip validation"
```

### Performance

- **Fast:** Only validates when .md files are staged
- **Efficient:** Uses `--errors-only` mode for speed
- **Non-intrusive:** Skips validation if no docs staged

---

## Manual Validation

Run validation manually at any time:

```bash
# Full report
poetry run python scripts/validate_cross_references.py

# Errors only (same as pre-commit)
poetry run python scripts/validate_cross_references.py --errors-only

# Verbose (all warnings)
poetry run python scripts/validate_cross_references.py --verbose
```

---

## Troubleshooting

### Hook not running

Check if hook is executable:
```bash
ls -la .git/hooks/pre-commit
```

Should show `-rwxr-xr-x` permissions. If not:
```bash
chmod +x .git/hooks/pre-commit
```

### Hook always passes

The hook only validates STAGED files. Check what's staged:
```bash
git diff --cached --name-only | grep '\.md$'
```

### Re-install hooks

If hooks are corrupted or outdated:
```bash
./scripts/install_git_hooks.sh
```

---

## Future Enhancements

Potential additions to pre-commit validation:

- [ ] Validate skill references in frontmatter
- [ ] Check for duplicate skill references
- [ ] Validate ADR number format
- [ ] Check for broken internal links
- [ ] Validate YAML frontmatter syntax
- [ ] Run linter on modified Python files

---

## Related Files

- `.git/hooks/pre-commit` - The actual hook (not tracked)
- `scripts/install_git_hooks.sh` - Installation script (tracked)
- `scripts/validate_cross_references.py` - Validation logic
- `docs/development/GIT_HOOKS.md` - This documentation

---

## Maintenance

**After pulling changes:**

If hooks are updated in the repository, re-run installation:
```bash
./scripts/install_git_hooks.sh
```

**Note:** Git hooks are NOT tracked by git (they're in `.git/hooks/`), so each developer must install them locally.
