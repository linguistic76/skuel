# Content Linting (Deferred)

**Status:** Deferred until Ku Phase 6 (atomic Ku entity) is complete
**Created:** 2026-03-06

## Context

ChatGPT contributed a standalone Markdown/YAML content linter concept targeting Obsidian vault files in `/home/mike/0bsidian/skuel/docs/`. This linter would validate content files before ingestion, catching errors that currently surface only at Neo4j write time.

This is **separate from** `scripts/lint_skuel.py` (Python code linter). Content linting targets `.md`/`.yaml` files in the content vault, not Python source.

## Key Ideas to Revisit

- **UID format validation:** Enforce the authored UID shape (`ku:{group}:{slug}`, colon-delimited, normalized to dots) with a valid entity prefix for the declared `type`
- **Edge block completeness:** Validate `type: Edge` YAML files have required fields (source, target, rel_type, evidence properties)
- **Relationship type enforcement:** SCREAMING_SNAKE_CASE for relationship types, validated against `RelationshipName` enum
- **NOUS vocabulary check:** Validate `nous` values against the 11 official topic sections (`stories`, `environment`, … `self-awareness`) — the vocabulary is graph-derived, not enum-enforced at ingestion, so typos pass silently today
- **Orphan detection:** Find content files not referenced by any PS or LP
- **Frontmatter schema validation:** Required fields per entity type (title, description, tags, etc.)

## Why Deferred

- The Ku authoring vocabulary is now settled (`nous` topic sections + `sel_category`; `namespace`/`ku_category`/`source` retired 2026-07-06), so the schema a linter would target is stable
- Content linting is lower priority than bringing the Python linter current

## Dependencies

- Edge ingestion stabilized (evidence properties, relationship types finalized)
