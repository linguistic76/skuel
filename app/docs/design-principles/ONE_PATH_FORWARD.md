---
title: "Design Principle: One Path Forward"
updated: 2026-04-13
status: current
category: design-principles
tags: [design, principles, migration, backward-compatibility]
related: [LIMITED_BACKWARD_COMPATIBILITY.md, docs/decisions/ADR-029-graphnative-service-removal.md]
---

# One Path Forward

> When a better pattern emerges, the old pattern is removed entirely.

## Statement

SKUEL does NOT maintain backward compatibility. No legacy wrappers, no deprecation periods, no alternative paths. When a pattern is superseded, all call sites are updated immediately. Dead code is deleted, not archived.

## Why This Matters

Every parallel path doubles the cognitive load, testing surface, and maintenance burden. For a project built through analog-to-digital partnership (plain English in, working code out), minimizing the number of active patterns is critical — the human collaborator cannot hold two competing patterns in mind simultaneously.

## In Practice

- **Renames are total.** The 2026-04 `Lesson → PathStep` merge touched 200+ files in one pass — every service, backend, route, UI component, and doc referencing Lesson was updated or shelved.
- **Deprecated enum values are deleted.** `_ENTITY_TYPE_ALIASES` handles historical string parsing; the enum itself contains only current values.
- **Migration scripts exist for data.** Neo4j property renames (`ku_type → entity_type`) run once, then the script is archived.
- **ADRs record the decision.** The old pattern lives in the ADR as history, not in the code as an alternative.

## Enforcement

- **SKUEL linter rules:** SKUEL016 catches stale Poetry references (example of enforcing one path after uv migration)
- **Code review:** Any PR introducing a wrapper, adapter, or "temporary" compatibility layer is rejected
- **MyPy:** Type errors from incomplete migrations are not suppressed — they guide completion

## Unmatured vs. Superseded

This principle applies when pattern A is **replaced** by pattern B. It does not apply to code that was built but never integrated.

Before removing code, distinguish:

- **Superseded** — a better pattern replaced it. One Path Forward applies: remove the old pattern entirely.
- **Unmatured** — built but never found its place. The question isn't "remove it" but "does it provide value, and where does it belong?"

Unused code with no consumers may be a pattern waiting for integration, not dead code waiting for deletion. Assess its potential value and natural home before treating it as waste.

## Exceptions

None. If a migration is too large to complete atomically, it is planned in phases — but each phase removes the old pattern from its scope. There is no "we'll clean it up later."

## See Also

- [Limited Backward Compatibility](LIMITED_BACKWARD_COMPATIBILITY.md)
- `/docs/decisions/ADR-029-graphnative-service-removal.md` — example of removing an entire subsystem
- `CLAUDE.md` § "One Path Forward"
