# Git Hooks

This directory contains git hooks that can be installed for the SKUEL project.

## Available Hooks

### post-merge

Detects library version changes after `git pull` / merge and reports affected skills.

**Install:**
```bash
# From repository root (/home/mike/skuel)
ln -sf ../../app/scripts/hooks/post-merge .git/hooks/post-merge
chmod +x .git/hooks/post-merge
```

**See:** `/docs/development/GIT_HOOKS.md` for complete documentation.

## Historical Note

The `post-commit` hook was removed (2026-03-30). Post-commit documentation checking
is now handled by the Claude Code PostToolUse hook at `.claude/hooks/post-commit-docs.sh`.
