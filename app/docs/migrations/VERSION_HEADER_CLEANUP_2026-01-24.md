# Version Header Cleanup - Remove Unused `__version__`

**Date:** 2026-01-24
**Issue:** `__version__` strings in route files were never used
**Resolution:** Removed from all 20 route files

---

## Background

Route files contained `__version__ = "X.X"` declarations that were:
- ❌ Never imported
- ❌ Never logged
- ❌ Never used in debugging
- ❌ Never checked at runtime

This was **documentation noise masquerading as code**.

---

## Analysis

### Evidence of Non-Use

```bash
# Found in 20 route files
grep -r "__version__" adapters/inbound/*_routes.py

# Never imported anywhere
grep -r "from.*_routes import __version__" .  # 0 results
grep -r "routes.__version__" .                 # 0 results
```

### Why Remove Instead of Use?

Better alternatives already exist:
1. **Git history** - Shows when files were migrated
2. **File structure** - DomainRouteConfig files vs manual files
3. **Migration docs** - `/docs/migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-01-24.md`
4. **ADRs** - For architectural decisions

### SKUEL Principles Applied

**"Remove, don't archive"**
> "Dead code is deleted from the codebase"

**"Avoid over-engineering"**
> "Don't create helpers, utilities, or abstractions for one-time operations"

---

## Changes Made

### Files Modified (20)

**Route Files:**
```
adapters/inbound/askesis_routes.py
adapters/inbound/calendar_routes.py
adapters/inbound/choices_routes.py
adapters/inbound/context_routes.py
adapters/inbound/events_routes.py
adapters/inbound/finance_routes.py
adapters/inbound/goals_routes.py
adapters/inbound/habits_routes.py
adapters/inbound/ingestion_routes.py
adapters/inbound/journals_routes.py
adapters/inbound/ku_routes.py
adapters/inbound/learning_routes.py
adapters/inbound/nous_routes.py
adapters/inbound/principles_routes.py
adapters/inbound/reports_routes.py
adapters/inbound/sel_routes.py
adapters/inbound/system_routes.py
adapters/inbound/tasks_routes.py
adapters/inbound/timeline_routes.py
adapters/inbound/visualization_routes.py
```

**Change Applied:**
```diff
  """
  {Domain} Routes - Configuration-Driven Registration
  ...
  """

- __version__ = "2.0"
-
  from adapters.inbound...
```

### Documentation Updated

**Pattern Documentation:**
- `/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md`
  - Removed `__version__ = "2.0"` from canonical template
  - Removed "Version Header" section entirely

**CLAUDE.md:**
- No changes needed (didn't reference `__version__`)

---

## Before/After Example

### Before
```python
"""
Tasks Routes - Clean Architecture Factory
=========================================

Minimal factory that wires API and UI routes using DomainRouteConfig.
"""

__version__ = "2.0"

from adapters.inbound.tasks_api import create_tasks_api_routes
...
```

### After
```python
"""
Tasks Routes - Clean Architecture Factory
=========================================

Minimal factory that wires API and UI routes using DomainRouteConfig.
"""

from adapters.inbound.tasks_api import create_tasks_api_routes
...
```

**Saved:** 1 blank line + 1 line of unused code per file = 40 lines total

---

## Verification

### Syntax Validation
```bash
poetry run python -m py_compile adapters/inbound/tasks_routes.py
# ✓ Syntax check passed
```

### Application Startup
```bash
poetry run python main.py
# ✓ Server starts successfully
# ✓ All routes register correctly
```

### No Regressions
- All 20 route files compile without errors
- Application starts and runs
- No functionality lost (nothing depended on `__version__`)

---

## Impact

**Code Quality:**
- 20 lines of dead code removed
- 20 blank lines removed
- Pattern documentation simplified

**Maintainability:**
- One less thing to update when changing patterns
- Cleaner, more focused route files
- No confusion about whether version should be updated

**Clarity:**
- Removes "documentation in code" anti-pattern
- Git history and migration docs are the source of truth
- Pattern identity clear from file structure

---

## Related Documentation

- **Pattern docs:** `/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md`
- **Migration summary:** `/docs/migrations/DOMAIN_ROUTE_CONFIG_MIGRATION_2026-01-24.md`
- **SKUEL principles:** `/CLAUDE.md` (section: "One Path Forward")

---

## Lessons Learned

### When Code Metadata Becomes Noise

Code-level metadata (like `__version__`) should only exist if:
1. **Actually used** - Imported, logged, or checked at runtime
2. **Required by tooling** - Package managers, build systems
3. **Part of public API** - Library version exported to users

If none of these apply: **delete it**.

### Better Alternatives

For tracking changes and versions:
- **Git tags/commits** - Source of truth for history
- **Documentation** - ADRs and migration docs
- **File structure** - Pattern adherence visible from code organization
- **Comments** - Explain *why*, not *when* (git has when)

---

## Future Considerations

If we ever need versioning in route files:
1. **Define the use case first** - What will read/use the version?
2. **Use it immediately** - Don't create it "just in case"
3. **Make it meaningful** - Log it, check it, or export it

Until then: keep it simple.
