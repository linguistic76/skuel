---
title: "Content Linting — the two survivors"
updated: 2026-09-05
status: "deferred"
registered: 2026-08-21
trigger: "content authoring volume makes silent nous typos or orphan drift a lived problem"
check: "ride-along on core/services/ingestion/validator.py"
---

# Content Linting — the two survivors

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Extracted from the deleted `CONTENT_LINTING.md` (premise largely absorbed by
`core/services/ingestion/validator.py`, which already validates UID shape, edge-block
completeness, relationship types, and required fields pre-persist). Two ideas remain
genuinely uncovered:

1. **NOUS vocabulary check** — nous section names are free-typed; a typo passes silently
   (verified 2026-08-21: no `NousSection` vocabulary exists in `core/` or `scripts/`).
2. **Orphan detection** — flag authored content nothing links to, at lint time rather than
   via the knowledge-health gauge's after-the-fact orphan count.

**Enable when**: content authoring volume makes silent nous typos or orphan drift a lived
problem — likely alongside a vault-audit pass, as a ride-along on `validator.py`.
