---
title: Documentation Naming Convention
created: 2026-01-03
updated: 2026-01-03
status: active
category: reference
tags: [documentation, naming, convention]
---

# Documentation Naming Convention

**Core Principle:** "Uppercase signals architecture, lowercase signals implementation"

## Naming Rules

### UPPERCASE.md (Architecture & Reference)

Use UPPERCASE for:
- **Cross-domain architecture** - Affects multiple domains/systems
- **System-wide patterns** - Used throughout the codebase
- **Reference catalogs** - Complete listings (protocols, enums, etc.)
- **Migrations** - Affect multiple systems

**Examples:**
- `ENTITY_TYPE_ARCHITECTURE.md` - Cross-domain architecture
- `PROTOCOL_REFERENCE.md` - Complete protocol catalog
- `ERROR_HANDLING.md` - System-wide pattern
- `SEARCH_ARCHITECTURE.md` - Multi-domain system

### lowercase_with_underscores.md (Implementation & Guides)

Use lowercase for:
- **Single-domain patterns** - Domain-specific implementation
- **Implementation guides** - How to use specific tools/mixins
- **Tool documentation** - Specific utilities

**Examples:**
- `constants_usage_guide.md` - Tool usage guide
- `event_driven_architecture.md` - Implementation pattern
- `search_service_pattern.md` - Single-pattern documentation
- `metadata_manager_mixin.md` - Specific mixin documentation

### ADR-###-kebab-case.md (Decision Records)

All Architecture Decision Records use:
- Prefix: `ADR-###-` (three-digit number)
- Body: `kebab-case` (lowercase with hyphens)

**Examples:**
- `ADR-018-user-roles-four-tier-system.md`
- `ADR-020-fasthtml-route-registration-pattern.md`

## Decision Tree

```
When naming a new document:

1. Is it an ADR?
   → ADR-###-kebab-case.md

2. Multi-domain or system-wide?
   → UPPERCASE.md

3. Complete reference catalog?
   → UPPERCASE.md

4. Migration affecting multiple systems?
   → UPPERCASE.md

5. Single domain pattern?
   → lowercase_with_underscores.md

6. Specific tool/mixin?
   → lowercase_with_underscores.md
```

## Directory Structure

| Directory | Purpose | Typical Naming |
|-----------|---------|----------------|
| `/docs/architecture/` | System architecture | UPPERCASE |
| `/docs/patterns/` | Implementation patterns | lowercase or UPPERCASE (depends on scope) |
| `/docs/guides/` | How-to guides | UPPERCASE (guides are reference material) |
| `/docs/reference/` | Complete catalogs | UPPERCASE |
| `/docs/decisions/` | ADRs | ADR-###-kebab-case |
| `/docs/domains/` | Domain-specific docs | lowercase |
| `/docs/migrations/` | Migration guides | UPPERCASE |

## Migration Notes

Some files may not follow this convention due to historical reasons. When updating any file, consider renaming to match the convention using `git mv` to preserve history.

**Files to Consider Renaming:**
- Mixed-case files (e.g., `assignments_PIPELINE.md`) → Choose uppercase or lowercase consistently
- Single-domain patterns using UPPERCASE → Consider lowercase if truly single-domain

## Examples from Current Codebase

### Correct Naming

| File | Reason |
|------|--------|
| `ENTITY_TYPE_ARCHITECTURE.md` | Cross-domain architecture |
| `protocol_architecture.md` | Implementation pattern |
| `ADR-018-user-roles-four-tier-system.md` | ADR format |
| `search_service_pattern.md` | Single-pattern guide |

### Exceptions

Some files use UPPERCASE for emphasis even if technically single-domain:
- `ERROR_HANDLING.md` - System-wide critical pattern
- `SEARCH_ARCHITECTURE.md` - Complex multi-component system

This is acceptable when the pattern is fundamental to the architecture.

---

**Status:** Active - Canonical reference for documentation naming
