# Technical Debt - Ruff Linting Errors

**Last Updated:** October 24, 2025
**Total Production Errors:** 136 (down from 241)

## Philosophy

We acknowledge these errors rather than suppress them. This document tracks **intentional** technical debt where fixing would provide minimal value or break working code.

## Priority Levels

- 🔴 **Critical:** Should fix soon (affects correctness)
- 🟡 **Medium:** Should fix eventually (affects maintainability)
- 🟢 **Low:** Acceptable debt (style preferences, protocol patterns)

---

## 🟢 Low Priority - Acceptable Debt (106 errors)

### ARG002: Unused Method Arguments (22 errors)
**Why acceptable:** Protocol methods and interface signatures require consistent parameters even if implementations don't use them all.

**Examples:**
- Protocol methods with unused `user_uid` parameters
- Interface methods matching third-party APIs
- Event handler signatures with unused context parameters

**Action:** None - this is intentional design for interface consistency.

---

### SIM105: Suppressible Exception (10 errors)
**Why acceptable:** Intentional try-except-pass patterns in cleanup/finally blocks.

**Examples:**
- Database connection cleanup
- Resource disposal in error paths
- Logging failures that shouldn't crash the app

**Action:** None - these are defensive programming patterns.

---

### PERF401: Manual List Comprehension (8 errors)
**Why acceptable:** Explicit loops are sometimes more readable than comprehensions.

**Examples:**
- Complex filtering with side effects
- Multi-step transformations
- Loops with early termination logic

**Action:** Convert on a case-by-case basis when refactoring nearby code.

---

### F401: Unused Import (8 errors)
**Why acceptable:** Imports used in TYPE_CHECKING blocks or by dynamic code.

**Action:** Review and remove if truly unused, or add `# noqa: F401` with explanation.

---

### Minor Style Issues (58 errors)
**Categories:**
- ARG001/ARG002/ARG004: Unused arguments (protocol signatures, interface consistency)
- ANN002/ANN003/ANN202: Missing type annotations (low priority in stable code)
- ASYNC230: Blocking calls in async (intentional in some cleanup paths)
- B007: Unused loop control variables (intentional unpacking)
- RUF006: Asyncio dangling tasks (background workers)
- RUF012: Mutable class defaults (class-level constants)
- SIM: Simplification suggestions (readability trade-offs)
- Others: Style preferences

**Action:** Fix incrementally during normal development.

---

## 🟡 Medium Priority - Should Fix Eventually (30 errors)

### F821: Undefined Name (17 errors)
**Why medium:** Could indicate real bugs, but mostly in examples/demos.

**Files affected:**
- Examples and demo files (most errors)
- Some route files with dynamic imports

**Action:**
1. Fix critical production files within 1 month
2. Fix or remove broken examples
3. Add proper imports where missing

**Timeline:** Q1 2026

---

### E402: Module Import Not at Top (12 errors)
**Why medium:** Makes dependencies unclear, violates PEP 8.

**Files affected:**
- Complex bootstrap files with conditional imports
- Files with `__version__` at top
- Circular dependency workarounds

**Action:**
1. Reorganize imports in high-traffic files
2. Use TYPE_CHECKING for type-only imports
3. Consider module restructuring to eliminate circular dependencies

**Timeline:** Q1 2026

---

### I001: Unsorted Imports (1 error)
**Why medium:** Trivial to fix, just needs `--fix` flag.

**Action:** Run `ruff check --fix` on affected file.

**Timeline:** Next sprint

---

## 🔴 Critical Priority - Fix Soon (0 errors)

**All critical errors have been resolved! 🎉**

- ✅ No undefined critical functions (F821 in production core)
- ✅ No import errors blocking execution (E402 in critical paths)
- ✅ No exception handling issues (B904, B025 fixed)
- ✅ No loop variable binding bugs (B023 fixed)
- ✅ No ambiguous variable names (E741 fixed)

---

## Automated Fixes Available

**9 errors can be auto-fixed:**
```bash
poetry run ruff check core/ adapters/ --fix
```

These include:
- F401: Unused imports (8)
- I001: Unsorted imports (1)

**Recommendation:** Run auto-fix monthly as part of maintenance.

---

## Monitoring Strategy

### Monthly Review
- Check if error count is growing
- Fix new high-priority errors immediately
- Review if "acceptable" debt is still acceptable

### Quarterly Cleanup
- Target 10-15 medium-priority fixes
- Re-evaluate priority levels
- Update this document

### Before Major Releases
- Resolve all critical errors
- Consider resolving medium-priority errors
- Document any new accepted debt

---

## Excluded from Linting

These directories/patterns are intentionally excluded (see `pyproject.toml`):

- `examples/` - Demonstration code, not production
- `scripts/demos/` - One-off demo scripts  
- `tests/` - Test code has different standards
- `*.egg-info/` - Generated files

---

## Philosophy Reminder

> "Type errors as teachers, showing us where components don't flow together properly."

We track this debt because:
1. **Transparency** - We acknowledge what we're not fixing
2. **Intentionality** - Each error is evaluated, not ignored
3. **Evolution** - Debt may become important as code evolves
4. **Teaching** - New developers learn why certain patterns exist

This is **managed technical debt**, not swept-under-the-rug problems.

---

## Statistics

**Production Code Health:**
- Total Python Files: ~450
- Total Production Errors: 136
- Error Rate: 0.30 errors per file
- Critical Errors: 0 ✅
- Medium Priority: 30 (22%)
- Low Priority: 106 (78%)

**Improvement Since Oct 24, 2025:**
- Reduced from 241 → 136 errors (44% improvement)
- Removed 30 deprecated test files
- Fixed 105 production errors manually
- Applied 103 automated fixes
- Fixed all critical errors ✅

**Next Milestone:** Reduce to <100 errors by Q1 2026

---

**Last Reviewed:** October 24, 2025  
**Next Review:** November 24, 2025  
**Owner:** Development Team
