---
title: ADR-030: UserContext File Consolidation
updated: 2026-01-20
status: current
category: decisions
tags: [adr, decisions, usercontext, cleanup]
related: [ADR-016, ADR-021, ADR-029]
---

# ADR-030: UserContext File Consolidation

**Status:** Accepted

**Date:** 2026-01-20

**Decision Type:** Pattern/Practice

**Related ADRs:**
- Related to: ADR-016 (Context Builder Decomposition)
- Related to: ADR-021 (User Context Intelligence Modularization)
- Related to: ADR-029 (GraphNative Service Removal)

---

## Context

**What is the issue we're facing?**

During the November 2025 UserContext refactoring (ADR-016), the canonical UserContext was relocated from the models layer to the services layer:
- OLD: `/core/models/user/user_context.py`
- NEW: `/core/services/user/unified_user_context.py`

However, the old file was not deleted. It remained as a stale 968-line duplicate with:
- Outdated `context_version: str = "2.0"` (canonical is "3.0")
- Missing fields (no MOC support, no January 2026 principle fields)
- Cascade update methods (`mark_task_complete`, etc.) that no longer exist in canonical
- Export via `core.models.user.__init__.py` creating a confusion hazard

**Evidence of staleness:**
- Zero code imports from `core.models.user import UserContext` (verified via grep)
- All 28+ UserContext imports use canonical path: `core.services.user`

---

## Decision

**Delete the stale duplicate and consolidate exports.**

1. **Delete** `/core/models/user/user_context.py` (968 lines removed)

2. **Update** `/core/models/user/__init__.py` to re-export UserContext from services:
   ```python
   # UserContext relocated to services layer (November 2025)
   from core.services.user import UserContext
   ```

3. **Remove** `UserContextBuilder` and `UserContextCache` from models layer exports
   - These are service-layer components
   - Import directly from `core.services.user` when needed

This follows SKUEL's "One Path Forward" philosophy: no legacy wrappers, no deprecation periods.

---

## Alternatives Considered

### Alternative 1: Keep Both Files with Sync
**Description:** Maintain both files, keeping them synchronized.

**Why rejected:** Violates "One Path Forward" - creates maintenance burden and confusion. The old file was already out of sync (version 2.0 vs 3.0).

### Alternative 2: Deprecation Period
**Description:** Mark old file as deprecated, remove after 3 months.

**Why rejected:** SKUEL explicitly does NOT use deprecation periods. Since zero code imports from old location, immediate deletion is safe.

---

## Consequences

### Positive Consequences
- Single source of truth for UserContext
- No confusion about which file is canonical
- 968 lines of stale code removed
- Cleaner module structure

### Negative Consequences
- None identified (zero imports from old location)

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Hidden imports not caught by grep | Very Low | Low | Re-export from models layer maintains backward compatibility |

---

## Implementation Details

### Code Location
- **Deleted:** `/core/models/user/user_context.py`
- **Canonical:** `/core/services/user/unified_user_context.py`
- **Updated:** `/core/models/user/__init__.py`

### Testing Strategy
- Run `./dev quality` to verify no import errors
- Run `pytest` to verify no regressions
- `grep -r "from core.models.user import.*UserContext"` returns nothing

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-01-20 | Claude | Initial implementation | 1.0 |
