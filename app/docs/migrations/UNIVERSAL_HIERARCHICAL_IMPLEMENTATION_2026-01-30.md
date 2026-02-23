# Universal Hierarchical Architecture Implementation Plan
**Date:** 2026-01-30
**Status:** Approved - Ready for Implementation
**Pattern:** Flat UIDs + Hierarchical Relationships (Option B)

## User Decisions (Confirmed)

1. ✅ **KU UID Format:** Full underscore alignment (`ku_meditation_a1b2c3d4`)
2. ✅ **Migration Timing:** Immediate (breaking change)
3. ✅ **LS Knowledge:** Migrate to relationships
4. ✅ **Pattern:** Flat UIDs with hierarchy in ORGANIZES relationships

**Core Principle:** "All hierarchy is graph relationships, never UID encoding"

---

## Implementation Phases

### Phase 1: KU UID Generator Refactoring

**Goal:** Flatten UID generation, remove hierarchical logic

**File:** `/core/utils/uid_generator.py`

**Changes:**

1. **Simplify `generate_knowledge_uid()` method:**
```python
# BEFORE (lines 68-110):
@classmethod
def generate_knowledge_uid(
    cls, title: str, parent_uid: str | None = None, domain_uid: str | None = None
) -> str:
    slug = cls.slugify(title)
    parts = [cls.KNOWLEDGE_PREFIX]
    if domain_uid:
        domain_part = domain_uid.replace(f"{cls.DOMAIN_PREFIX}.", "")
        parts.append(domain_part)
    if parent_uid:
        parent_parts = parent_uid.split(".")[1:]
        if domain_uid and parent_parts and parent_parts[0] == domain_part:
            parent_parts = parent_parts[1:]
        if parent_parts:
            parts.extend(parent_parts)
    parts.append(slug)
    return ".".join(parts)

# AFTER:
@classmethod
def generate_knowledge_uid(cls, title: str) -> str:
    """
    Generate a flat knowledge unit UID.

    Format: ku_{slug}_{random}

    Args:
        title: Knowledge unit title

    Returns:
        Flat UID with underscore separator

    Examples:
        >>> generate_knowledge_uid("Meditation Basics")
        'ku_meditation-basics_a1b2c3d4'

    Note:
        Hierarchy is stored in ORGANIZES relationships, not in UIDs.
        See: /docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md
    """
    slug = cls.slugify(title)
    random_suffix = uuid.uuid4().hex[:8]
    return f"{cls.KNOWLEDGE_PREFIX}_{slug}_{random_suffix}"
```

2. **Delete parsing methods (no longer needed):**
   - `extract_parts(uid)` - lines 204-238
   - `get_parent_uid(uid)` - lines 241-259
   - `get_domain_from_uid(uid)` - lines 262-280

3. **Update file docstring:**
```python
# Lines 7-19 - Update to reflect new format
"""
UID Generation Utilities
========================

UID generation for SKUEL entities with consistent naming conventions.

UID Format Rules (2026-01-30 Universal Hierarchical Pattern):
- ALL domains: {type}_{identifier}_{random} (underscore separator)
- Hierarchy stored in graph relationships, NEVER in UIDs

Examples:
- task_implement-auth_a1b2c3d4    (Task)
- goal_complete-project_x7y8z9w0  (Goal)
- ku_meditation-basics_def45678   (Knowledge Unit - NOW FLAT!)
- user_mike                        (User - no random suffix)

See: /docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md
See: /docs/migrations/UNIVERSAL_HIERARCHICAL_IMPLEMENTATION_2026-01-30.md
"""
```

---

### Phase 2: KU Service Updates

**Goal:** Remove hierarchical parameters, add relationship methods

**File:** `/core/services/ku/ku_core_service.py`

**Changes:**

1. **Update `create()` method (lines 180-210):**
```python
# BEFORE (line 184-188):
uid = UIDGenerator.generate_knowledge_uid(
    title=title,
    parent_uid=metadata.get("parent_uid"),
    domain_uid=metadata.get("domain_uid"),
)

# AFTER:
uid = UIDGenerator.generate_knowledge_uid(title=title)

# Handle organization relationship if parent specified
parent_uid = metadata.get("parent_uid")
if parent_uid:
    # Create ORGANIZES relationship after KU creation
    # (Will add organize_ku method below)
    pass  # Implemented after node creation
```

2. **Add hierarchical methods (mirroring TasksCoreService):**

```python
async def get_subkus(
    self,
    parent_uid: str,
    depth: int = 1,
    include_metadata: bool = False
) -> Result[list[KnowledgeUnit]]:
    """
    Get all KUs organized under this parent KU (MOC pattern).

    Args:
        parent_uid: Parent KU UID
        depth: How many levels deep (1 = direct children only)
        include_metadata: Include relationship metadata (order, etc.)

    Returns:
        Result containing list of child KUs

    Example:
        # Get all KUs organized under "Yoga Fundamentals" MOC
        result = await ku_service.get_subkus("ku_yoga-fundamentals_abc123")
        if result.is_ok:
            for child_ku in result.value:
                print(f"  - {child_ku.title}")
    """
    query = """
    MATCH (parent:Curriculum {uid: $parent_uid})-[r:ORGANIZES*1..%d]->(child:Curriculum)
    RETURN child, r
    ORDER BY r.order ASC
    """ % depth

    result = await self.backend.driver.execute_query(
        query,
        parent_uid=parent_uid,
        routing_="r"
    )

    # Convert to KnowledgeUnit objects
    kus = [self._record_to_domain(record["child"]) for record in result.records]
    return Result.ok(kus)


async def get_parent_kus(self, ku_uid: str) -> Result[list[KnowledgeUnit]]:
    """
    Get all parent KUs (can have multiple via MOC pattern).

    Args:
        ku_uid: Child KU UID

    Returns:
        Result containing list of parent KUs

    Example:
        # "Machine Learning" might be in multiple MOCs
        result = await ku_service.get_parent_kus("ku_machine-learning_xyz789")
        # Returns: ["AI Fundamentals", "Data Science", "Python Advanced"]
    """
    query = """
    MATCH (parent:Curriculum)-[:ORGANIZES]->(child:Curriculum {uid: $ku_uid})
    RETURN parent
    """

    result = await self.backend.driver.execute_query(
        query,
        ku_uid=ku_uid,
        routing_="r"
    )

    parents = [self._record_to_domain(record["parent"]) for record in result.records]
    return Result.ok(parents)


async def get_ku_hierarchy(self, ku_uid: str) -> Result[dict]:
    """
    Get full hierarchy context for a KU.

    Returns:
        dict with:
        - ancestors: List of ancestor KUs (grandparent, parent, etc.)
        - siblings: Other KUs with same parents
        - children: Direct child KUs
        - depth: How deep in hierarchy (0 = root)

    Example:
        hierarchy = {
            "ancestors": [
                {"uid": "ku_yoga_abc", "title": "Yoga Fundamentals", "level": 1},
                {"uid": "ku_meditation_def", "title": "Meditation", "level": 2}
            ],
            "siblings": [...],
            "children": [...],
            "depth": 3
        }
    """
    # Get ancestors
    ancestors_query = """
    MATCH path = (ancestor:Curriculum)-[:ORGANIZES*]->(ku:Curriculum {uid: $ku_uid})
    RETURN ancestor, length(path) as depth
    ORDER BY depth DESC
    """

    # Get children
    children_query = """
    MATCH (ku:Curriculum {uid: $ku_uid})-[:ORGANIZES]->(child:Curriculum)
    RETURN child
    """

    # Get siblings (KUs with same parents)
    siblings_query = """
    MATCH (parent:Curriculum)-[:ORGANIZES]->(sibling:Curriculum)
    WHERE (parent)-[:ORGANIZES]->(:Curriculum {uid: $ku_uid})
    AND sibling.uid <> $ku_uid
    RETURN DISTINCT sibling
    """

    # Execute queries
    ancestors_result = await self.backend.driver.execute_query(ancestors_query, ku_uid=ku_uid)
    children_result = await self.backend.driver.execute_query(children_query, ku_uid=ku_uid)
    siblings_result = await self.backend.driver.execute_query(siblings_query, ku_uid=ku_uid)

    return Result.ok({
        "ancestors": [
            {"uid": r["ancestor"]["uid"], "title": r["ancestor"]["title"], "level": r["depth"]}
            for r in ancestors_result.records
        ],
        "children": [
            {"uid": r["child"]["uid"], "title": r["child"]["title"]}
            for r in children_result.records
        ],
        "siblings": [
            {"uid": r["sibling"]["uid"], "title": r["sibling"]["title"]}
            for r in siblings_result.records
        ],
        "depth": len(ancestors_result.records)
    })


async def organize_ku(
    self,
    parent_uid: str,
    child_uid: str,
    order: int = 0,
    importance: str = "normal"
) -> Result[bool]:
    """
    Create ORGANIZES relationship between KUs (MOC pattern).

    Args:
        parent_uid: Parent KU UID (the MOC)
        child_uid: Child KU UID
        order: Display order (0 = first)
        importance: "core", "normal", "supplemental"

    Returns:
        Result[bool] - True if created

    Example:
        # Add "Meditation" to "Yoga Fundamentals" MOC
        await ku_service.organize_ku(
            parent_uid="ku_yoga-fundamentals_abc123",
            child_uid="ku_meditation_xyz789",
            order=1,
            importance="core"
        )
    """
    query = """
    MATCH (parent:Curriculum {uid: $parent_uid})
    MATCH (child:Curriculum {uid: $child_uid})
    MERGE (parent)-[r:ORGANIZES]->(child)
    SET r.order = $order,
        r.importance = $importance,
        r.created_at = datetime()
    RETURN r
    """

    result = await self.backend.driver.execute_query(
        query,
        parent_uid=parent_uid,
        child_uid=child_uid,
        order=order,
        importance=importance
    )

    return Result.ok(len(result.records) > 0)


async def unorganize_ku(self, parent_uid: str, child_uid: str) -> Result[bool]:
    """
    Remove ORGANIZES relationship between KUs.

    Args:
        parent_uid: Parent KU UID
        child_uid: Child KU UID

    Returns:
        Result[bool] - True if removed
    """
    query = """
    MATCH (parent:Curriculum {uid: $parent_uid})-[r:ORGANIZES]->(child:Curriculum {uid: $child_uid})
    DELETE r
    RETURN count(r) as deleted
    """

    result = await self.backend.driver.execute_query(
        query,
        parent_uid=parent_uid,
        child_uid=child_uid
    )

    deleted = result.records[0]["deleted"] if result.records else 0
    return Result.ok(deleted > 0)
```

3. **Update create() to handle parent relationship:**

```python
# After line 203 (after await self.backend.create(unit_data)):

# If parent specified, create ORGANIZES relationship
parent_uid = metadata.get("parent_uid")
if parent_uid:
    organize_result = await self.organize_ku(
        parent_uid=parent_uid,
        child_uid=uid,
        order=metadata.get("order", 0)
    )
    if organize_result.is_error:
        self.logger.warning(
            f"Failed to create ORGANIZES relationship: {organize_result.error}"
        )
```

---

### Phase 3: Database Migration

**Goal:** Flatten all existing hierarchical KU UIDs

**File:** `/scripts/migrations/flatten_ku_uids.py` (NEW)

```python
"""
Flatten KU UIDs - Universal Hierarchical Pattern Migration
==========================================================

Migrates KU UIDs from hierarchical (ku.yoga.meditation.basics)
to flat format (ku_meditation-basics_a1b2c3d4).

CRITICAL: Backup database before running!

Usage:
    poetry run python scripts/migrations/flatten_ku_uids.py --dry-run
    poetry run python scripts/migrations/flatten_ku_uids.py --execute

See: /docs/migrations/UNIVERSAL_HIERARCHICAL_IMPLEMENTATION_2026-01-30.md
"""

import asyncio
import uuid
from neo4j import AsyncGraphDatabase
from core.utils.uid_generator import UIDGenerator
from core.utils.logging import get_logger

logger = get_logger("skuel.migrations.flatten_ku_uids")


async def analyze_hierarchical_kus(driver):
    """Find all KUs with hierarchical UIDs."""
    query = """
    MATCH (ku:Curriculum)
    WHERE ku.uid CONTAINS '.'
    AND size(split(ku.uid, '.')) > 2
    RETURN ku.uid as old_uid, ku.title as title, size(split(ku.uid, '.')) as depth
    ORDER BY depth DESC, old_uid ASC
    """

    result = await driver.execute_query(query, routing_="r")
    return result.records


async def generate_new_uid(title: str, existing_uids: set[str]) -> str:
    """Generate flat UID, ensuring uniqueness."""
    max_attempts = 100

    for _ in range(max_attempts):
        new_uid = UIDGenerator.generate_knowledge_uid(title)
        if new_uid not in existing_uids:
            return new_uid

    # Fallback: add extra random suffix
    slug = UIDGenerator.slugify(title)
    random_suffix = uuid.uuid4().hex[:12]
    return f"ku_{slug}_{random_suffix}"


async def flatten_ku_uid(driver, old_uid: str, new_uid: str):
    """Flatten a single KU UID, preserving all relationships."""
    query = """
    MATCH (ku:Curriculum {uid: $old_uid})
    SET ku.uid = $new_uid,
        ku.old_uid = $old_uid,
        ku.migrated_at = datetime()
    RETURN ku.uid as new_uid
    """

    result = await driver.execute_query(
        query,
        old_uid=old_uid,
        new_uid=new_uid
    )

    return result.records[0]["new_uid"] if result.records else None


async def main(dry_run: bool = True):
    """Execute migration."""
    from core.config import settings

    logger.info("=" * 80)
    logger.info("KU UID Flattening Migration")
    logger.info("=" * 80)
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info("")

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password)
    )

    try:
        # Step 1: Analyze
        logger.info("Step 1: Analyzing hierarchical KU UIDs...")
        hierarchical_kus = await analyze_hierarchical_kus(driver)

        if not hierarchical_kus:
            logger.info("✅ No hierarchical KU UIDs found. Migration not needed.")
            return

        logger.info(f"Found {len(hierarchical_kus)} hierarchical KU UIDs")
        logger.info("")

        # Step 2: Plan flattening
        logger.info("Step 2: Planning UID flattening...")
        existing_uids = set()
        migration_plan = []

        for record in hierarchical_kus:
            old_uid = record["old_uid"]
            title = record["title"]
            depth = record["depth"]

            new_uid = await generate_new_uid(title, existing_uids)
            existing_uids.add(new_uid)

            migration_plan.append({
                "old_uid": old_uid,
                "new_uid": new_uid,
                "title": title,
                "depth": depth
            })

            logger.info(f"  {old_uid} → {new_uid} (depth: {depth})")

        logger.info("")
        logger.info(f"Migration plan created for {len(migration_plan)} KUs")

        if dry_run:
            logger.info("")
            logger.info("=" * 80)
            logger.info("DRY RUN COMPLETE - No changes made")
            logger.info("To execute migration, run with --execute flag")
            logger.info("=" * 80)
            return

        # Step 3: Execute migration
        logger.info("")
        logger.info("Step 3: Executing migration...")
        logger.warning("⚠️  EXECUTING MIGRATION - Database will be modified!")

        migrated_count = 0
        for plan in migration_plan:
            result_uid = await flatten_ku_uid(driver, plan["old_uid"], plan["new_uid"])
            if result_uid:
                migrated_count += 1
                logger.info(f"  ✅ {plan['old_uid']} → {result_uid}")
            else:
                logger.error(f"  ❌ Failed: {plan['old_uid']}")

        logger.info("")
        logger.info(f"✅ Migrated {migrated_count}/{len(migration_plan)} KU UIDs")

        # Step 4: Verify
        logger.info("")
        logger.info("Step 4: Verifying migration...")
        remaining = await analyze_hierarchical_kus(driver)

        if not remaining:
            logger.info("✅ SUCCESS: All KU UIDs flattened")
        else:
            logger.warning(f"⚠️  {len(remaining)} hierarchical UIDs remain")
            for record in remaining:
                logger.warning(f"  - {record['old_uid']}")

    finally:
        await driver.close()

    logger.info("")
    logger.info("=" * 80)
    logger.info("Migration complete")
    logger.info("=" * 80)


if __name__ == "__main__":
    import sys

    dry_run = "--execute" not in sys.argv
    asyncio.run(main(dry_run=dry_run))
```

---

### Phase 4: LS Knowledge Relationship Migration

**Goal:** Move from properties to relationships

**4.1: Update LS Model**

**File:** `/core/models/ls/ls.py`

```python
# REMOVE lines 99-100:
# primary_knowledge_uids: tuple[str, ...] = ()
# supporting_knowledge_uids: tuple[str, ...] = ()

# ADD comment explaining relationship pattern:
# GRAPH-NATIVE: Knowledge relationships stored as edges
# Query via: (ls)-[:CONTAINS_KNOWLEDGE {type: "primary|supporting"}]->(ku)
# Use LsCoreService.get_contained_knowledge() to retrieve
```

**4.2: Update LsCoreService**

**File:** `/core/services/ls/ls_core_service.py`

Add methods:

```python
async def add_knowledge_relationship(
    self,
    ls_uid: str,
    ku_uid: str,
    knowledge_type: str = "primary"
) -> Result[bool]:
    """
    Create CONTAINS_KNOWLEDGE relationship between LS and KU.

    Args:
        ls_uid: Learning Step UID
        ku_uid: Knowledge Unit UID
        knowledge_type: "primary" or "supporting"

    Returns:
        Result[bool] - True if created
    """
    if knowledge_type not in ("primary", "supporting"):
        return Result.fail(Errors.validation(
            f"Invalid knowledge_type: {knowledge_type}",
            field="knowledge_type"
        ))

    query = """
    MATCH (ls:Ls {uid: $ls_uid})
    MATCH (ku:Curriculum {uid: $ku_uid})
    MERGE (ls)-[r:CONTAINS_KNOWLEDGE]->(ku)
    SET r.type = $knowledge_type,
        r.created_at = datetime()
    RETURN r
    """

    result = await self.backend.driver.execute_query(
        query,
        ls_uid=ls_uid,
        ku_uid=ku_uid,
        knowledge_type=knowledge_type
    )

    return Result.ok(len(result.records) > 0)


async def get_contained_knowledge(
    self,
    ls_uid: str,
    knowledge_type: str | None = None
) -> Result[list[dict]]:
    """
    Get KUs contained in this Learning Step via relationships.

    Args:
        ls_uid: Learning Step UID
        knowledge_type: Filter by "primary" or "supporting" (None = all)

    Returns:
        Result containing list of KU dicts with type metadata
    """
    if knowledge_type:
        query = """
        MATCH (ls:Ls {uid: $ls_uid})-[r:CONTAINS_KNOWLEDGE {type: $knowledge_type}]->(ku:Curriculum)
        RETURN ku, r.type as type
        ORDER BY ku.title
        """
        params = {"ls_uid": ls_uid, "knowledge_type": knowledge_type}
    else:
        query = """
        MATCH (ls:Ls {uid: $ls_uid})-[r:CONTAINS_KNOWLEDGE]->(ku:Curriculum)
        RETURN ku, r.type as type
        ORDER BY r.type, ku.title
        """
        params = {"ls_uid": ls_uid}

    result = await self.backend.driver.execute_query(query, **params)

    knowledge = [
        {
            "uid": record["ku"]["uid"],
            "title": record["ku"]["title"],
            "type": record["type"]
        }
        for record in result.records
    ]

    return Result.ok(knowledge)
```

**4.3: Migration Script**

**File:** `/scripts/migrations/migrate_ls_knowledge_relationships.py` (NEW)

```python
"""
Migrate LS Knowledge from Properties to Relationships
=====================================================

Migrates Learning Step knowledge storage from properties
(primary_knowledge_uids, supporting_knowledge_uids) to
CONTAINS_KNOWLEDGE relationships.

Usage:
    poetry run python scripts/migrations/migrate_ls_knowledge_relationships.py
"""

import asyncio
from neo4j import AsyncGraphDatabase
from core.utils.logging import get_logger

logger = get_logger("skuel.migrations.ls_knowledge")


async def migrate_ls_knowledge(driver):
    """Migrate all LS knowledge from properties to relationships."""

    # Step 1: Find LS nodes with knowledge properties
    query = """
    MATCH (ls:Ls)
    WHERE ls.primary_knowledge_uids IS NOT NULL
       OR ls.supporting_knowledge_uids IS NOT NULL
    RETURN ls.uid as ls_uid,
           ls.primary_knowledge_uids as primary_uids,
           ls.supporting_knowledge_uids as supporting_uids
    """

    result = await driver.execute_query(query, routing_="r")

    logger.info(f"Found {len(result.records)} LS nodes with knowledge properties")

    migrated = 0

    for record in result.records:
        ls_uid = record["ls_uid"]
        primary_uids = record["primary_uids"] or []
        supporting_uids = record["supporting_uids"] or []

        # Create primary relationships
        for ku_uid in primary_uids:
            await driver.execute_query(
                """
                MATCH (ls:Ls {uid: $ls_uid})
                MATCH (ku:Curriculum {uid: $ku_uid})
                MERGE (ls)-[r:CONTAINS_KNOWLEDGE]->(ku)
                SET r.type = 'primary', r.created_at = datetime()
                """,
                ls_uid=ls_uid,
                ku_uid=ku_uid
            )

        # Create supporting relationships
        for ku_uid in supporting_uids:
            await driver.execute_query(
                """
                MATCH (ls:Ls {uid: $ls_uid})
                MATCH (ku:Curriculum {uid: $ku_uid})
                MERGE (ls)-[r:CONTAINS_KNOWLEDGE]->(ku)
                SET r.type = 'supporting', r.created_at = datetime()
                """,
                ls_uid=ls_uid,
                ku_uid=ku_uid
            )

        # Remove properties
        await driver.execute_query(
            """
            MATCH (ls:Ls {uid: $ls_uid})
            REMOVE ls.primary_knowledge_uids, ls.supporting_knowledge_uids
            """,
            ls_uid=ls_uid
        )

        migrated += 1
        logger.info(f"  ✅ {ls_uid}: {len(primary_uids)} primary, {len(supporting_uids)} supporting")

    logger.info(f"✅ Migrated {migrated} LS nodes")


async def main():
    from core.config import settings

    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password)
    )

    try:
        await migrate_ls_knowledge(driver)
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
```

---

### Phase 5: Documentation Updates

**5.1: Update ADR-013**

**File:** `/docs/decisions/ADR-013-ku-uid-flat-identity.md`

Update implementation section (lines 197-226):

```markdown
## Implementation Details

### Code Location

**Primary files:**
- `/core/utils/uid_generator.py:68` - Flat UID generation (ku_{slug}_{random})
- `/core/services/ku/ku_core_service.py` - Hierarchical relationship methods
- `/core/models/relationship_names.py:273` - ORGANIZES relationship

### UID Generation Code

```python
# uid_generator.py - Flat generation
def generate_knowledge_uid(cls, title: str) -> str:
    slug = cls.slugify(title)
    random_suffix = uuid.uuid4().hex[:8]
    return f"ku_{slug}_{random_suffix}"
```

### Hierarchy via Relationships

```cypher
// MOC Pattern - KU organizing KUs
MATCH (moc:Curriculum {uid: "ku_yoga-fundamentals_abc123"})
MATCH (child:Curriculum {uid: "ku_meditation_xyz789"})
MERGE (moc)-[:ORGANIZES {order: 1}]->(child)
```

### Service Methods

```python
# KuCoreService - Hierarchical methods
await ku_service.organize_ku(parent_uid, child_uid, order)
await ku_service.get_subkus(parent_uid, depth=1)
await ku_service.get_parent_kus(ku_uid)
await ku_service.get_ku_hierarchy(ku_uid)
```

### Migration

See: `/docs/migrations/UNIVERSAL_HIERARCHICAL_IMPLEMENTATION_2026-01-30.md`

Migration completed: 2026-01-30
```

**5.2: Create Universal Pattern Doc**

**File:** `/docs/patterns/UNIVERSAL_HIERARCHICAL_PATTERN.md` (NEW)

```markdown
# Universal Hierarchical Pattern
**Status:** Implemented (2026-01-30)
**Scope:** All Domains (Activity, Curriculum, Infrastructure)

## Core Principle

**"All hierarchy is graph relationships, never UID encoding"**

## Pattern

1. **Flat UIDs** - Identity independent of location
2. **Graph relationships** - Hierarchy via edges with metadata
3. **Display hierarchy** - Generated from graph traversal, not UID parsing
4. **DAG support** - Multiple parents possible

## Implementation Across Domains

### Activity Domains (Tasks, Goals, Habits)

**UIDs:** `task_abc123`, `goal_xyz789`, `habit_def456`

**Relationships:**
```cypher
(parent:Task)-[:HAS_SUBTASK {progress_weight: 0.5, order: 1}]->(child:Task)
(child:Task)-[:SUBTASK_OF]->(parent:Task)  // Bidirectional
```

**Service Methods:**
- `get_subtasks(parent_uid, depth)`
- `get_parent_tasks(task_uid)`
- `get_task_hierarchy(task_uid)`
- `add_subtask(parent_uid, child_uid, ...)`
- `remove_subtask(parent_uid, child_uid)`

### Curriculum Domains (KU, LS, LP)

**KU - Knowledge Units**

**UIDs:** `ku_meditation_a1b2c3d4`

**Relationships:**
```cypher
(moc:Curriculum)-[:ORGANIZES {order: 1, importance: "core"}]->(child:Curriculum)
```

**Service Methods:**
- `organize_ku(parent_uid, child_uid, order, importance)`
- `get_subkus(parent_uid, depth)`
- `get_parent_kus(ku_uid)`
- `get_ku_hierarchy(ku_uid)`

**LS - Learning Steps**

**UIDs:** `ls:abc123def456`

**Relationships:**
```cypher
(lp:Lp)-[:HAS_STEP {order: 1}]->(ls:Ls)
(ls:Ls)-[:REQUIRES_STEP]->(prerequisite:Ls)
(ls:Ls)-[:CONTAINS_KNOWLEDGE {type: "primary"}]->(ku:Curriculum)
```

**LP - Learning Paths**

**UIDs:** `lp:xyz789abc012`

**Relationships:**
```cypher
(lp:Lp)-[:HAS_STEP {order: 1, sequence: 1}]->(ls:Ls)
```

## Benefits

### 1. Reorganization Safety
**Before:** Moving changes UID → breaks references
**After:** Moving updates edge → UID unchanged

### 2. Multiple Parents (DAG)
```cypher
// Machine Learning in multiple MOCs
(ku.ai)-[:ORGANIZES]->(ku.ml)
(ku.data-science)-[:ORGANIZES]->(ku.ml)
(ku.python)-[:ORGANIZES]->(ku.ml)
```

### 3. Relationship Metadata
```cypher
[:ORGANIZES {
    order: 1,
    importance: "core",
    last_reviewed: datetime(),
    user_notes: "Start here"
}]
```

### 4. Query Consistency
```python
# Same pattern everywhere
children = await service.get_related(
    entity_uid,
    relationship_type,
    direction="outgoing"
)
```

## Migration

See: `/docs/migrations/UNIVERSAL_HIERARCHICAL_IMPLEMENTATION_2026-01-30.md`

Completed: 2026-01-30

## Related Documentation

- `/docs/patterns/HIERARCHICAL_RELATIONSHIPS_PATTERN.md` - Activity domain implementation
- `/docs/decisions/ADR-013-ku-uid-flat-identity.md` - KU flat identity decision
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` - KU, LS, LP patterns
```

---

## Execution Checklist

- [ ] Phase 1: UID Generator Refactoring
  - [ ] Flatten `generate_knowledge_uid()`
  - [ ] Delete parsing methods
  - [ ] Update docstring
  - [ ] Run tests: `pytest tests/unit/test_uid_generator.py -v`

- [ ] Phase 2: KU Service Updates
  - [ ] Update `create()` method
  - [ ] Add hierarchical methods (5 methods)
  - [ ] Update parent relationship handling
  - [ ] Run tests: `pytest tests/integration/test_ku_hierarchy.py -v` (create test)

- [ ] Phase 3: Database Migration
  - [ ] Create migration script
  - [ ] Backup database
  - [ ] Run with --dry-run
  - [ ] Review plan
  - [ ] Execute with --execute
  - [ ] Verify results

- [ ] Phase 4: LS Knowledge Migration
  - [ ] Update LS model (remove properties)
  - [ ] Add service methods
  - [ ] Create migration script
  - [ ] Execute migration
  - [ ] Update queries using LS knowledge

- [ ] Phase 5: Documentation
  - [ ] Update ADR-013
  - [ ] Create UNIVERSAL_HIERARCHICAL_PATTERN.md
  - [ ] Update CLAUDE.md (UID format section)
  - [ ] Update CURRICULUM_GROUPING_PATTERNS.md

- [ ] Final Validation
  - [ ] All tests passing
  - [ ] No hierarchical KU UIDs remain
  - [ ] LS knowledge relationships working
  - [ ] MOC functionality intact
  - [ ] Documentation complete

---

## Rollback Plan

If issues arise:

1. **Database Backup:** Restore from pre-migration backup
2. **Code Revert:** `git revert` to previous commit
3. **Selective Rollback:** Restore specific KU UIDs from backup while keeping others

**Backup Location:** `/backups/neo4j/pre-universal-hierarchical-{timestamp}.dump`

---

## Success Criteria

✅ All domains use flat UIDs (no hierarchy encoding)
✅ All hierarchy via graph relationships
✅ Consistent query patterns across domains
✅ Multiple parents possible (DAG support)
✅ Reorganization never changes UIDs
✅ No UID string parsing methods
✅ One mental model documented
✅ All tests passing
✅ Zero hierarchical KU UIDs in database
