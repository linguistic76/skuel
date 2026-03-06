# Content Linting (Deferred)

**Status:** Deferred until Ku Phase 6 (atomic Ku entity) is complete
**Created:** 2026-03-06

## Context

ChatGPT contributed a standalone Markdown/YAML content linter concept targeting Obsidian vault files in `/home/mike/0bsidian/skuel/docs/`. This linter would validate content files before ingestion, catching errors that currently surface only at Neo4j write time.

This is **separate from** `scripts/lint_skuel.py` (Python code linter). Content linting targets `.md`/`.yaml` files in the content vault, not Python source.

## Key Ideas to Revisit

- **UID format validation:** Enforce `ku_<namespace>-<slug>_<rand>` (or `a_<slug>_<rand>` for Articles) in frontmatter
- **Edge block completeness:** Validate `type: Edge` YAML files have required fields (source, target, rel_type, evidence properties)
- **Relationship type enforcement:** SCREAMING_SNAKE_CASE for relationship types, validated against `RelationshipName` enum
- **Namespace registry:** Validate `ku_category` values against known namespaces (attention, emotion, cognition, etc.)
- **Orphan detection:** Find content files not referenced by any LS or LP
- **Frontmatter schema validation:** Required fields per entity type (title, description, tags, etc.)

## Why Deferred

- Ku Phase 6 (atomic Ku entity extending Entity directly) will settle namespace conventions and `KuCategory` enum values
- UID format conventions are still evolving (`a_` prefix for Articles is new as of March 2026)
- Content linting is lower priority than bringing the Python linter current

## Dependencies

- Ku Phase 6 complete (KuCategory enum, namespace conventions settled)
- Edge ingestion stabilized (evidence properties, relationship types finalized)
