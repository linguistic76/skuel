---
title: "ADR-013: KU UID Flat Identity Design"
updated: 2026-10-16
status: implemented
category: decisions
tags: [adr, decisions, ku, uid, identity, curriculum]
related: [ENTITY_TYPE_ARCHITECTURE.md, CURRICULUM_GROUPING_PATTERNS.md]
related_skills: [neo4j-cypher-patterns, curriculum-domains]
---

# ADR-013: KU UID Flat Identity Design

**Status:** Implemented (Universal Hierarchical Pattern - 2026-01-30). **Amended 2026-10-16:**
one Ku uid form, authored `ku.{ns}.{slug}`; the generated `ku_{slug}_{random}` form below is
retired, and the never-sniff rule stays — see [§ Amendment (2026-10-16)](#amendment-2026-10-16-one-ku-uid-form).

**Date:** 2025-12-03 (Decision) | 2026-01-30 (Implementation)

**Decision Type:** ☑️ Pattern/Practice  ⬜ Query Architecture  ⬜ Graph Schema  ⬜ Performance Optimization

**Related ADRs:**
- Related to: Entity Type Architecture
- Related to: Curriculum Grouping Patterns (KU, PS, LP, MOC)

---

## Related Skills

For implementation guidance, see:
- [@neo4j-cypher-patterns](../../.claude/skills/neo4j-cypher-patterns/SKILL.md)

## Context

**What is the issue we're facing?**

Knowledge Units (KU) need unique identifiers (UIDs) for storage in Neo4j and retrieval via the docs UI. The question is whether UIDs should encode location (hierarchical) or be independent of location (flat).

**Example scenario:**
```
File: 0vault/stories/machine-learning.md

Option A (Hierarchical): ku.stories.machine-learning
Option B (Flat):         ku.machine-learning
```

**Constraints:**
- UIDs must be unique across all KUs
- UIDs should be human-readable
- UIDs should be stable (not change when content is reorganized)
- Content creators should have minimal friction

**Philosophical question:**
Is knowledge hierarchical (tree) or networked (graph)?

SKUEL is a knowledge GRAPH. A KU about "machine learning" could relate to:
- Stories (case studies)
- Tech (implementation)
- Investment (AI stocks)
- Self-awareness (human vs machine cognition)

Encoding ONE path in the UID implies that's THE primary location, but knowledge is multi-faceted.

---

## Decision

**KU UIDs are FLAT: Identity independent of location**

> **Amended 2026-10-16.** The flat, location-free identity stands. The generated format in
> § UID Format is retired: a Ku is authored only in the content vault (ADR-091 S8), so its uid
> is the authored `ku.{ns}.{slug}`, and nothing in the app mints `ku_{slug}_{random}`. See
> [§ Amendment (2026-10-16)](#amendment-2026-10-16-one-ku-uid-form).

**Universal Hierarchical Pattern (2026-01-30):** KU UIDs use the same flat format as Activity domains (Tasks, Goals, Habits), with hierarchy stored in ORGANIZES relationships.

### UID Format

```
ku_{slug}_{random}
```

Where:
- `{slug}` is a URL-safe version of the title
- `{random}` is an 8-character random suffix for uniqueness

**Examples:**
```
Title: "Meditation Basics"    →  ku_meditation-basics_a1b2c3d4
Title: "Python Functions"     →  ku_python-functions_x7y8z9w0
Title: "Machine Learning 101" →  ku_machine-learning-101_def45678
```

**Authored Format (dot form):**
- Vault ingestion: `ku.{ns}.{slug}` (authored in dot form directly; the colon input alias was deleted 2026-08-14 — colon spellings are rejected loudly)
- Not a transitional legacy — permanently sanctioned alongside the generated form as a
  provenance marker (see Addendum: the two-form reality)

### Override Mechanism

If collision risk exists or a specific UID is desired, use explicit `uid:` in frontmatter:

```yaml
---
uid: ku.ml-stories-intro
title: Machine Learning Introduction (Stories)
domain: tech
---
```

### Collision Handling

Current behavior: **MERGE (upsert)** - last sync wins.

```cypher
MERGE (n:Curriculum {uid: item.uid})
  ON CREATE SET n = item, n.created_at = datetime()
  ON MATCH SET n = item, n.updated_at = datetime()
```

If two files produce the same UID, the second sync overwrites the first. This is acceptable because:
1. Re-syncing the same file should update content (expected)
2. Two different files with same name is a content organization error
3. Override mechanism exists for edge cases

### Separation of Concerns

| Concern | Who Handles It |
|---------|----------------|
| **Identity** | UID (flat: `ku_{slug}_{random}`) |
| **Hierarchy** | ORGANIZES relationships in graph |
| **Human Browsing** | Folder structure in Obsidian vault |
| **Navigation** | MOC (Map of Content) - graph structure |
| **Categorization** | Tags, Domain enum, relationships |

### Hierarchy Storage

**Critical:** Hierarchy is NEVER encoded in UIDs. Instead, it's stored in graph relationships:

```cypher
// Parent-child organization (MOC pattern)
(parent:Curriculum {uid: "ku_yoga-fundamentals_abc123"})
  -[:ORGANIZES {order: 1, importance: "core"}]->
(child:Curriculum {uid: "ku_meditation-basics_xyz789"})
```

**Benefits:**
- KU can have multiple parents (DAG, not tree)
- Reorganization never changes UIDs
- Relationship metadata (order, importance)
- Query consistency across all domains

---

## Alternatives Considered

### Alternative 1: Hierarchical UIDs (Path-Based)

**Description:** Encode folder path in UID: `ku.stories.machine-learning`

**Pros:**
- Self-documenting location
- Natural filesystem mapping
- Parent-child relationships implicit in UID

**Cons:**
- Longer UIDs
- UID changes if content reorganized
- Implies ONE canonical location for multi-faceted knowledge
- Couples organization to identity

**Why rejected:** Knowledge is a graph, not a tree. Location should not be identity.

### Alternative 2: UUID-Based

**Description:** Use random UUIDs: `ku_550e8400-e29b-41d4-a716-446655440000`

**Pros:**
- Guaranteed unique
- No collision possible
- Completely decoupled from content

**Cons:**
- Not human-readable
- No semantic meaning
- Harder to debug and reference
- Breaks "plain English in, working code out" philosophy

**Why rejected:** Violates human-readability requirement. UIDs should be meaningful.

### Alternative 3: Hybrid (Path When Needed)

**Description:** Flat by default, include path only for disambiguation: `ku.python` vs `ku.tech-python`

**Pros:**
- Short UIDs in common case
- Handles collisions

**Cons:**
- Inconsistent format
- Rules for when to include path unclear
- Still couples some UIDs to location

**Why rejected:** Added complexity without clear benefit. Explicit `uid:` override is cleaner.

---

## Consequences

### Positive Consequences
- ✅ Location-free UIDs (`ku.machine-learning`, never `ku.stories.tech.machine-learning` path chains)
- ✅ Identity stable across reorganization
- ✅ Aligns with SKUEL's graph-based knowledge model
- ✅ MOC provides flexible navigation independent of UID
- ✅ Human-readable and memorable

### Negative Consequences
- ⚠️ Content creators must use unique filenames (or explicit uid:)
- ⚠️ Collision results in silent overwrite (no fail-fast currently)
- ⚠️ No automatic namespace isolation per folder

### Neutral Consequences
- ℹ️ Folder structure becomes purely for human browsing, not machine identity
- ℹ️ MOC becomes essential for navigation (not optional)

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Filename collision | Low | Medium | Use explicit `uid:` in frontmatter |
| Silent overwrite of different content | Low | High | Content review process; future: add collision detection |
| Confusion about where content "lives" | Medium | Low | Documentation; MOC provides canonical navigation |

---

## Implementation Details

**Implementation Date:** 2026-01-30 (Universal Hierarchical Pattern)

### Code Location

**Primary files** (function names, not line pins — lines drift):
- `/core/services/ingestion/` — the unified ingestion pipeline: a Ku file's `uid:` is stored
  verbatim; with none, the filename-fallback uid is `ku.{file-stem}` (`preparer.py`); the
  MERGE upsert lives below `adapters/persistence/neo4j/`
- `/adapters/persistence/neo4j/backends/curriculum_backends.py` — `KuBackend`, the ORGANIZES
  Cypher (MOC); read back through `/core/services/ku/ku_intelligence_service.py`
- `/core/models/relationship_names.py` — ORGANIZES relationship
- `/core/services/dsl/activity_dsl_parser.py` — `_parse_ku`: an `@ku()` reference accepts only
  `ku.…`; any other spelling is dropped and reported in the line's `tag_warnings`

No service creates a Ku, and `core/utils/uid_generator.py` mints no Ku uid (amendment
2026-10-16).

### ORGANIZES Relationship

Hierarchy is authored in the vault (`organizes:` or `moc: true` frontmatter) and ingested as:

```cypher
// Cypher pattern
MATCH (parent:Entity {uid: "ku.yoga.fundamentals"})
MATCH (child:Entity {uid: "ku.yoga.meditation"})
MERGE (parent)-[r:ORGANIZES]->(child)
SET r.order = 1
```

---

## Documentation & Communication

### Related Documentation
- `/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md` - KU as "point" topology
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` - KU, PS, LP, MOC relationships
- `/CLAUDE.md` - UID prefix documentation

### CLAUDE.md Update Required

Current CLAUDE.md documents `ku:` (colon notation) but implementation uses `ku.` (dot notation). This ADR establishes `ku.{filename}` as the canonical format. CLAUDE.md should be updated to reflect this.

---

## Future Considerations

### When to Revisit
- If collision rate becomes problematic
- If fail-fast collision detection is needed
- If namespace isolation becomes a requirement

### Evolution Path
- **Phase 1 (Current):** Flat UIDs with MERGE upsert
- **Phase 2 (Optional):** Add collision detection warning
- **Phase 3 (Optional):** Add strict mode that fails on collision

### Technical Debt
- [x] CLAUDE.md documents `ku:` but implementation uses `ku.` - **RESOLVED** via ADR-014
- [ ] No collision detection currently - silent overwrite

### UID Normalization (ADR-014)

As of ADR-014 (Unified Ingestion Service), **dot notation is the spelling of authored UIDs**
(not "the canonical format" — there is no single canonical spelling; see the Addendum):
- Colon notation (`ku:filename`) is REJECTED — the auto-convert input alias was deleted 2026-08-14
- Ingestion's filename-fallback UID is dot form (`ku.{file-stem}`)
- The generated underscore form (`ku_{slug}_{random}`) is retired (amendment 2026-10-16)
- Separator law: `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` § Separator Grammar

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2025-12-03 | Claude | Initial decision (flat UIDs principle) | 1.0 |
| 2025-12-03 | Claude | Added UID normalization note (ADR-014) | 1.1 |
| 2026-01-30 | Claude | Implemented Universal Hierarchical Pattern | 2.0 |
| 2026-01-30 | Claude | Updated with underscore format & ORGANIZES | 2.1 |
| 2026-08-14 | Mike + Claude | Separator grammar ratified (dot = authored provenance, hierarchy in edges); fixed stale citations, "canonical dot format" claim, and the "backward compatibility" framing of the authored form | 2.2 |
| 2026-10-16 | Mike + Claude | Amendment: one Ku uid form, authored `ku.{ns}.{slug}`; the generated `ku_{slug}_{random}` form is retired with its minter, and an `@ku()` reference in another spelling links nothing and is reported. The never-sniff rule stays (ADR-091 S8) | 3.0 |

---

## Appendix

### Content Creator Workflow

**Creating a KU:** a Ku is authored only in the content vault (ADR-091 S8); no service
creates one, and its uid is the authored `ku.{ns}.{slug}`. Placement under a parent is an
`ORGANIZES` edge, authored in the vault through `organizes:` or `moc: true` frontmatter — see
[../patterns/UNIFIED_INGESTION_GUIDE.md](../patterns/UNIFIED_INGESTION_GUIDE.md) § MOC files.

1. Create a markdown file in the content vault:
   ```
   0vault/meditation/meditation-basics.md
   ```

2. Add frontmatter:
   ```yaml
   ---
   type: ku
   uid: ku.wellness.meditation-basics
   title: Meditation Basics
   tags: [meditation, mindfulness]
   ---
   ```

3. Sync the content vault: the admin "Sync content vault" button
   (`POST /api/vault/sync/content`) or `./dev vault-sync`.

4. Result in Neo4j:
   ```
   (:Entity:Ku {uid: "ku.wellness.meditation-basics", title: "Meditation Basics", ...})
   ```

### Hierarchical Organization

A Ku can sit under several parents (a DAG, not a tree), and moving it never changes its uid:
each placement is one `ORGANIZES` edge from a parent file, retracted when the file drops the
target. A `moc: true` file's body links become those edges; a link resolves through the
target's file path to its uid.

```yaml
# 0vault/moc/ai-fundamentals.md
---
type: ku
uid: ku.tech.ai-fundamentals
moc: true
---
- [[machine-learning]]
```

The same `machine-learning.md` Ku can be linked from another MOC as well; every reference to its
uid stays valid.

## Addendum (2026-07-04, Arc F/G12): the two-form reality in today's graph

> **Superseded by the [amendment of 2026-10-16](#amendment-2026-10-16-one-ku-uid-form):** the
> generated form below is retired. Kept as the record of the two-form ruling.

Both UID forms remain sanctioned, but they are provenance, not a migration plan:

- **Authored** (vault): `ku.{ns}.{slug}`, written in dot form directly since 2026-08-14
  (the colon authoring spelling was retired and the vault swept; the `normalize_uid()`
  boundary shim was deleted in the same ruling — authored = stored verbatim, and a
  colon-spelled entity uid fails prefix validation loudly).
- **Generated** (API): `ku_{slug}_{random}`, this ADR's format.

As of 2026-07-04 the live graph holds **only** dotted authored Ku UIDs (89/89);
zero flat generated Kus exist yet, because all curriculum content to date arrived
via vault ingestion. That is expected, not drift — the flat format activates when
KUs are created through the API. No migration between the forms, ever; entity kind
is determined by label/`entity_type`/edge, never by UID spelling (the never-sniff
rule, reaffirmed 2026-07-03).

## Amendment (2026-10-16): one Ku uid form

**Ruled by Mike, 2026-10-16** (on the curriculum sync-only chain, ADR-091 S8).

- **One form.** A Ku uid is the authored `ku.{ns}.{slug}`, written in the content vault. The
  generated `ku_{slug}_{random}` form is retired: curriculum is authored only in the content
  vault, so nothing creates a Ku in the app, and the uid generator's Ku minter is gone.
  The live graph held no generated Ku (0 of 121 on 2026-10-16), so nothing migrates.
- **A reference in another spelling links nothing, visibly.** `@ku(ku_…)` (and the colon
  `@ku(ku:…)`) names no Ku, even if a node with that exact uid existed: the parser drops the
  reference and the line's `tag_warnings` report it in the run summary.
- **The never-sniff rule stays.** It governs every type: entity kind comes from the label,
  `entity_type` or an edge, never from a uid's spelling, and a uid's middle segment stays a
  human grouping hint, never machine meaning (SKUEL034).
- **Flat identity stands.** Hierarchy is still `ORGANIZES` edges, never the uid.
