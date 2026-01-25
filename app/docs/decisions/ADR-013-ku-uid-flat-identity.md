---
title: ADR-013: KU UID Flat Identity Design
updated: 2025-12-03
status: accepted
category: decisions
tags: [adr, decisions, ku, uid, identity, curriculum]
related: [FOURTEEN_DOMAIN_ARCHITECTURE.md, CURRICULUM_GROUPING_PATTERNS.md]
---

# ADR-013: KU UID Flat Identity Design

**Status:** Accepted

**Date:** 2025-12-03

**Decision Type:** ☑️ Pattern/Practice  ⬜ Query Architecture  ⬜ Graph Schema  ⬜ Performance Optimization

**Related ADRs:**
- Related to: 14-Domain Architecture
- Related to: Curriculum Grouping Patterns (KU, LS, LP, MOC)

---

## Context

**What is the issue we're facing?**

Knowledge Units (KU) need unique identifiers (UIDs) for storage in Neo4j and retrieval via the docs UI. The question is whether UIDs should encode location (hierarchical) or be independent of location (flat).

**Example scenario:**
```
File: /docs/stories/machine-learning.md

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

**KU UIDs are FLAT: `ku.{filename}`**

Identity is independent of location. Organization is handled separately by MOC, tags, and relationships.

### UID Format

```
ku.{filename}
```

Where `{filename}` is the markdown file's stem (name without extension).

**Examples:**
```
/docs/stories/machine-learning.md  →  ku.machine-learning
/docs/tech/python-basics.md        →  ku.python-basics
/docs/investment/portfolio.md      →  ku.portfolio
```

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
MERGE (n:Ku {uid: item.uid})
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
| **Identity** | UID (flat: `ku.{filename}`) |
| **Human Browsing** | Folder structure in Obsidian vault |
| **Navigation** | MOC (Map of Content) - graph structure |
| **Categorization** | Tags, Domain enum, relationships |

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

**Description:** Use random UUIDs: `ku.550e8400-e29b-41d4-a716-446655440000`

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
- ✅ Short, clean UIDs (`ku.machine-learning`)
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

### Code Location

**Primary files:**
- `/core/services/markdown_sync_service.py:323` - UID generation
- `/adapters/inbound/docs_routes.py:262` - UID query construction

**Related files:**
- `/core/ingestion/bulk_ingestion.py` - MERGE upsert logic
- `/ui/docs/components.py` - ContentPending shows expected UID

### UID Generation Code

```python
# markdown_sync_service.py:323
def _parse_knowledge_unit(self, frontmatter: dict, body: str, file_path: Path):
    # Extract or generate UID
    uid = frontmatter.get("uid") or f"ku.{file_path.stem}"
```

### Query Construction Code

```python
# docs_routes.py:262
# Convention: topic slug maps to KU uid with "ku." prefix (dot notation)
ku_uid = f"ku.{topic_slug}"
```

---

## Documentation & Communication

### Related Documentation
- `/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md` - KU as "point" topology
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` - KU, LS, LP, MOC relationships
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

As of ADR-014 (Unified Ingestion Service), **dot notation is the canonical UID format**:
- All new UIDs generated with dot notation: `ku.filename`
- Colon notation (`ku:filename`) auto-converted to dot notation on ingestion
- UnifiedIngestionService handles normalization transparently

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2025-12-03 | Claude | Initial decision | 1.0 |
| 2025-12-03 | Claude | Added UID normalization note (ADR-014) | 1.1 |

---

## Appendix

### Content Creator Workflow

**Creating a new KU:**

1. Create markdown file in Obsidian vault:
   ```
   /docs/stories/machine-learning.md
   ```

2. Add frontmatter:
   ```yaml
   ---
   title: Machine Learning
   domain: tech
   tags: [ml, ai, basics]
   ---
   ```

3. Sync via MarkdownSyncService:
   ```python
   await markdown_sync.sync_file(path)
   ```

4. Result in Neo4j:
   ```
   (:Ku {uid: "ku.machine-learning", title: "Machine Learning", ...})
   ```

5. Accessible at:
   ```
   /docs/stories/machine-learning
   ```

### Override Example

When two topics might have the same filename:

```yaml
# /docs/stories/python.md
---
uid: ku.python-stories
title: Python in Storytelling
---

# /docs/tech/python.md
---
uid: ku.python-programming
title: Python Programming
---
```
