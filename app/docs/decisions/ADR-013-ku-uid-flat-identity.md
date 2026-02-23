---
title: ADR-013: KU UID Flat Identity Design
updated: 2026-01-30
status: implemented
category: decisions
tags: [adr, decisions, ku, uid, identity, curriculum, universal-hierarchical-pattern]
related: [FOURTEEN_DOMAIN_ARCHITECTURE.md, CURRICULUM_GROUPING_PATTERNS.md, UNIVERSAL_HIERARCHICAL_PATTERN.md]
---

# ADR-013: KU UID Flat Identity Design

**Status:** Implemented (Universal Hierarchical Pattern - 2026-01-30)

**Date:** 2025-12-03 (Decision) | 2026-01-30 (Implementation)

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

**KU UIDs are FLAT: Identity independent of location**

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

**Previous Format (Pre-2026-01-30):**
- Markdown ingestion: `ku.{filename}` (e.g., `ku.meditation-basics`)
- Still supported for backward compatibility during transition

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
| **Identity** | UID (flat: `ku_{slug}_{random}`) |
| **Hierarchy** | ORGANIZES relationships in graph |
| **Human Browsing** | Folder structure in Obsidian vault |
| **Navigation** | MOC (Map of Content) - graph structure |
| **Categorization** | Tags, Domain enum, relationships |

### Hierarchy Storage

**Critical:** Hierarchy is NEVER encoded in UIDs. Instead, it's stored in graph relationships:

```cypher
// Parent-child organization (MOC pattern)
(parent:Ku {uid: "ku_yoga-fundamentals_abc123"})
  -[:ORGANIZES {order: 1, importance: "core"}]->
(child:Ku {uid: "ku_meditation-basics_xyz789"})
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

**Implementation Date:** 2026-01-30 (Universal Hierarchical Pattern)

### Code Location

**Primary files:**
- `/core/utils/uid_generator.py:67-92` - Flat UID generation
- `/core/services/ku/ku_core_service.py:183-218` - KU creation with ORGANIZES support
- `/core/services/ku/ku_core_service.py:750-1013` - Hierarchical methods
- `/core/models/relationship_names.py:273` - ORGANIZES relationship

**Related files:**
- `/core/services/markdown_sync_service.py` - Markdown ingestion (legacy dot format)
- `/core/ingestion/bulk_ingestion.py` - MERGE upsert logic

### UID Generation Code (2026-01-30)

```python
# core/utils/uid_generator.py:67-92
@classmethod
def generate_knowledge_uid(cls, title: str) -> str:
    """
    Generate a flat knowledge unit UID.

    Format: ku_{slug}_{random}
    Hierarchy stored in ORGANIZES relationships.
    """
    slug = cls.slugify(title)
    random_suffix = uuid.uuid4().hex[:8]
    return f"{cls.KNOWLEDGE_PREFIX}_{slug}_{random_suffix}"
```

### KU Creation with Hierarchy

```python
# core/services/ku/ku_core_service.py
async def create(self, title: str, body: str, **metadata) -> Result[CurriculumDTO]:
    # Generate flat UID
    uid = UIDGenerator.generate_knowledge_uid(title=title)

    # Store KU node
    await self.backend.create(unit_data)

    # Handle parent organization if specified
    parent_uid = metadata.get("parent_uid")
    if parent_uid:
        await self.organize_ku(
            parent_uid=parent_uid,
            child_uid=uid,
            order=metadata.get("order", 0),
            importance=metadata.get("importance", "normal")
        )
```

### Hierarchical Service Methods

```python
# Added 2026-01-30
await ku_service.get_subkus(parent_uid, depth=1)  # Get children
await ku_service.get_parent_kus(ku_uid)           # Get parents (can be multiple!)
await ku_service.get_ku_hierarchy(ku_uid)         # Full context
await ku_service.organize_ku(parent, child, ...)  # Create relationship
await ku_service.unorganize_ku(parent, child)     # Remove relationship
```

### ORGANIZES Relationship

```cypher
// Cypher pattern
MATCH (parent:Ku {uid: "ku_yoga_abc"})
MATCH (child:Ku {uid: "ku_meditation_xyz"})
MERGE (parent)-[r:ORGANIZES]->(child)
SET r.order = 1,
    r.importance = 'core',
    r.created_at = datetime()
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
| 2025-12-03 | Claude | Initial decision (flat UIDs principle) | 1.0 |
| 2025-12-03 | Claude | Added UID normalization note (ADR-014) | 1.1 |
| 2026-01-30 | Claude | Implemented Universal Hierarchical Pattern | 2.0 |
| 2026-01-30 | Claude | Updated with underscore format & ORGANIZES | 2.1 |

---

## Appendix

### Content Creator Workflow

**Creating a new KU via Service (Primary):**

```python
# Create KU with flat UID
result = await ku_service.create(
    title="Meditation Basics",
    body=content,
    tags=["meditation", "mindfulness"],
    parent_uid="ku_yoga-fundamentals_abc123",  # Optional: create ORGANIZES
    order=1,
    importance="core"
)

# Result: ku_meditation-basics_a1b2c3d4
# Relationship: (yoga)-[:ORGANIZES {order: 1}]->(meditation)
```

**Creating a KU via Markdown (Legacy Support):**

1. Create markdown file in Obsidian vault:
   ```
   /docs/meditation/meditation-basics.md
   ```

2. Add frontmatter:
   ```yaml
   ---
   title: Meditation Basics
   domain: wellness
   tags: [meditation, mindfulness]
   ---
   ```

3. Sync via MarkdownSyncService:
   ```python
   await markdown_sync.sync_file(path)
   ```

4. Result in Neo4j (legacy dot format):
   ```
   (:Ku {uid: "ku.meditation-basics", title: "Meditation Basics", ...})
   ```

**Note:** Markdown ingestion still uses `ku.{filename}` format for backward compatibility. New service-created KUs use `ku_{slug}_{random}` format.

### Hierarchical Organization Example

**Before (2026-01-30 - Hierarchical UIDs):**
```python
# Parent encoded in UID - WRONG!
uid = generate_knowledge_uid(
    title="Meditation",
    parent_uid="ku.yoga",
    domain_uid="dom.wellness"
)
# Result: "ku.yoga.meditation" - hierarchy in UID string
```

**After (2026-01-30 - Universal Hierarchical Pattern):**
```python
# Flat UID + relationship - CORRECT!
uid = generate_knowledge_uid(title="Meditation")
# Result: "ku_meditation_a1b2c3d4" - flat, stable

# Hierarchy via ORGANIZES
await ku_service.organize_ku(
    parent_uid="ku_yoga-fundamentals_abc123",
    child_uid="ku_meditation_a1b2c3d4",
    order=1,
    importance="core"
)
# Creates: (parent)-[:ORGANIZES {order: 1, importance: "core"}]->(child)
```

**Multiple Parents (DAG):**
```python
# Same KU can be in multiple MOCs
await ku_service.organize_ku("ku_ai-fundamentals_xyz", "ku_ml_abc", order=1)
await ku_service.organize_ku("ku_data-science_def", "ku_ml_abc", order=2)
await ku_service.organize_ku("ku_python-advanced_ghi", "ku_ml_abc", order=3)

# Machine Learning appears in 3 different organizational contexts!
```

**Reorganization Safety:**
```python
# Moving KU to different parent - UID unchanged!
await ku_service.unorganize_ku(old_parent_uid, ku_uid)
await ku_service.organize_ku(new_parent_uid, ku_uid, order=1)
# All references to ku_uid remain valid
```
