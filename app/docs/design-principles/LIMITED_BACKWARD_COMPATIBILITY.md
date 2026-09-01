---
title: "Design Principle: Limited Backward Compatibility"
updated: 2026-04-13
status: current
category: design-principles
tags: [design, principles, migration, compatibility]
related: [ONE_PATH_FORWARD.md]
---

# Limited Backward Compatibility

> No legacy wrappers, no deprecation periods, no historical references.

## Statement

SKUEL does not maintain backward compatibility to historical patterns. When a rename, refactor, or removal happens, it happens completely. No re-exports of old names, no `_deprecated_` prefixes, no "this was previously called X" comments cluttering the codebase.

## Why This Matters

Backward compatibility is expensive. Every alias, wrapper, and compatibility shim is code that must be tested, maintained, and understood by future collaborators. In a codebase built through analog-to-digital partnership, every unnecessary concept is a communication barrier.

Historical references in code comments create confusion: "Was this renamed? Is the old name still valid somewhere? Should I use the new name or the old one?" Removing all traces of the old pattern eliminates these questions entirely.

## In Practice

- **Enum aliases are parsing-only.** `_ENTITY_TYPE_ALIASES` in `EntityType.from_string()` handles old strings from Neo4j data — but the enum itself contains only current values. Deprecated aliases (ARTICLE, SUBMISSION, JOURNAL, SUBMISSION_REPORT) were deleted from the enum.
- **Merges are atomic.** The 2026-04 `Lesson → PathStep` merge updated 200+ files in one pass. `LessonService`, `LessonBackend`, and `lesson_*` routes were shelved the same day — no `Lesson = PathStep` alias was left behind in live code (the narrow `"lesson"` YAML frontmatter alias is a documented content-source exception, not a code alias).
- **Migration scripts handle data.** Neo4j property renames run as one-time scripts, then the script moves to an archive. The codebase never checks for both old and new property names.
- **ADRs are the historical record.** If someone needs to understand why something was renamed, they read the ADR — not a comment in the code.

## Relationship to One Path Forward

This principle is the enforcement arm of [One Path Forward](ONE_PATH_FORWARD.md). One Path Forward says "choose the better pattern." Limited Backward Compatibility says "delete the old one completely."

## Scope

This principle addresses **migration scenarios** — when code is being renamed, refactored, or replaced. It does not apply to unmatured code that was built but never integrated. See [One Path Forward § Unmatured vs. Superseded](ONE_PATH_FORWARD.md) for that distinction.

## Enforcement

- **Code review:** PRs with backward-compatibility wrappers, re-exports, or `# previously known as` comments are rejected
- **Linter rules:** SKUEL016 catches stale references to replaced tools
- **Git history:** The old pattern is preserved in git, not in code comments

## See Also

- [One Path Forward](ONE_PATH_FORWARD.md)
- `CLAUDE.md` § "One Path Forward"
