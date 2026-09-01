# Documentation & Skills Evolution

**Expert guide for how SKUEL's documentation and skills evolve in rhythm with the ecosystem.**

## Core Philosophy: Alignment with Ecosystem

**SKUEL doesn't dictate evolution - it responds to and aligns with the evolution of its tech stack.**

### The Fundamental Principle

SKUEL is built on established open-source technologies:
- **FastHTML** - Server-rendered hypermedia framework
- **Neo4j** - Graph database
- **Pydantic** - Data validation
- **Alpine.js** - Client-side reactivity
- **Prometheus** - Metrics collection

**When these libraries evolve, SKUEL adapts.** We don't maintain backward compatibility or create legacy wrappers. We follow the "One Path Forward" philosophy.

### What This Means

| Scenario | SKUEL Response |
|----------|----------------|
| **Library upgrades to new major version** | Update all code to use new API (no wrappers) |
| **Library deprecates a feature** | Remove usage immediately, adopt replacement |
| **Library introduces better pattern** | Evaluate and adopt if superior |
| **Library changes philosophy** | Align with new direction or re-evaluate dependency |

### Historical Context Preservation

When patterns change, **we delete the old code but preserve the context**:

```markdown
## ADR-XXX: Migrated from Pattern A to Pattern B

**Context:**
FastHTML 1.4 introduced automatic form validation (PEP 695 type hints),
deprecating manual validation decorators.

**Decision:**
Remove all @validate decorators, adopt native FastHTML validation.

**Historical Note:**
Prior to FastHTML 1.4, we used manual @validate decorators (see commit abc123).
This pattern was necessary because FastHTML lacked native validation.
When FastHTML added this feature, we immediately migrated to align with
the framework's intended usage.
```

**Key**: ADRs show *why* we changed (external forces), not just *what* changed.

---

## Two Drivers of Doc Evolution

Doc evolution has two equally important triggers:

| Driver | Frequency | Workflow |
|--------|-----------|----------|
| **Library upgrade** | Major versions, deprecations | Part 1 (Library Upgrade) |
| **Internal refactor** | Decompositions, renames, merges | Part 2b (Stale Document Audit) |

**Documentation changes more frequently (70% of evolution):**
- Code patterns evolve → docs updated
- Bug fixes reveal edge cases → docs clarified
- Library minor versions → syntax examples updated
- Performance optimizations → pattern docs evolved
- Internal refactors drift from existing docs → staleness audit

**Skills change less frequently (30% of evolution):**
- Library major version changes core API
- Fundamental pattern shifts across many files
- New cross-cutting concerns emerge
- Internal refactors change file layouts referenced in skills

**Claude Code PostToolUse hook** (`.claude/hooks/post-commit-docs.sh`) detects changed files and prompts doc/skill review. Cross-reference validation (`validate_cross_references.py`) is a manual tool — run it after major changes.

---

## Detailed Workflows

For the full step-by-step workflows — library upgrades, pattern deprecation, stale-document audits, new-feature documentation, the cross-reference system, validation & tooling, the validation checklist, ADR creation, and the fundamentals-vs-adaptive decision framework (Parts 1–8) — see **[reference.md](reference.md)**.

---

## Quick Reference

### File Locations

| Purpose | Location |
|---------|----------|
| Health check scripts | `scripts/health/` — see `docs/tools/HEALTH_CHECKS.md` for the roster (a list here goes stale the moment a check is added) |
| Health check docs | `docs/tools/HEALTH_CHECKS.md` |
| Skills metadata | `.claude/skills/skills_metadata.yaml` |
| Post-commit doc check | `.claude/hooks/post-commit-docs.sh` (Claude Code PostToolUse hook) |
| Post-merge hook | `scripts/hooks/post-merge` |
| Cross-reference validator | `scripts/validate_cross_references.py` |
| Library change detector | `scripts/detect_library_changes.py` |
| Cross-reference index | `docs/CROSS_REFERENCE_INDEX.md` (auto-generated) |
| ADR template | `docs/decisions/ADR-TEMPLATE.md` |

### Key Commands

```bash
# Health checks (run after any refactor/rename)
./dev health              # every check below
./dev health-modules      # orphaned Python modules
./dev health-links        # broken doc links
./dev health-names        # stale identifiers in doc code blocks
./dev health-names --list # print full RENAMED/DELETED tables
./dev health-headings     # repeated headings under one parent

# Cross-reference validation
uv run python scripts/validate_cross_references.py
uv run python scripts/validate_cross_references.py --verbose

# Detect library changes
uv run python scripts/detect_library_changes.py

# Regenerate cross-reference index
uv run python scripts/generate_cross_reference_index.py
```

### Evolution Philosophy Summary

1. **SKUEL aligns with ecosystem** - Library evolution drives SKUEL evolution
2. **One path forward** - No backward compatibility, no legacy wrappers
3. **Preserve context** - ADRs show *why* we changed (external forces)
4. **Documentation focus** - 70% docs evolve, 30% skills evolve
5. **Validate early** - Post-commit detects new docs; post-merge detects library changes; run `validate_cross_references.py` manually after major changes
6. **Fundamentals vs adaptive** - Respect library patterns, adapt SKUEL patterns

---

## Related Documentation

### Core Philosophy
- `/docs/patterns/DOCSTRING_STANDARDS.md` - Three-layer documentation approach
- `/docs/decisions/ADR-TEMPLATE.md` - How to document decisions
- `/CLAUDE.md` - "One Path Forward" philosophy

### Cross-Reference System
- `/docs/CROSS_REFERENCE_INDEX.md` - Auto-generated skill↔doc mapping
- `.claude/skills/skills_metadata.yaml` - Central registry

### Health Check Tooling
- `/docs/tools/HEALTH_CHECKS.md` - Complete reference for the three health scripts
- `scripts/health/stale_names.py` - Maintainable RENAMED/DELETED tables (update on every rename)

### Example ADRs Showing Evolution
- `/docs/decisions/ADR-020.md` - FastHTML route registration
- `/docs/decisions/ADR-035.md` - Pydantic tier selection
- `/docs/decisions/ADR-037.md` - Neo4j lateral relationships

---

**Last Updated:** 2026-03-03
