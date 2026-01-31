# Git Hooks

This directory contains git hooks that can be installed for the SKUEL project.

## Available Hooks

### post-commit

Automatically checks if documentation needs updating after each commit.

**Install:**
```bash
# From repository root (/home/mike/skuel)
ln -sf ../../app/scripts/hooks/post-commit .git/hooks/post-commit
chmod +x .git/hooks/post-commit
```

**Or use the dev command:**
```bash
./dev install-hooks  # (if implemented)
```

**Disable:**
```bash
git config skuel.docs-check false
```

**Re-enable:**
```bash
git config skuel.docs-check true
```

## Hook Details

See `/docs/tools/AUTOMATIC_DOCS_CHECK.md` for complete documentation.
