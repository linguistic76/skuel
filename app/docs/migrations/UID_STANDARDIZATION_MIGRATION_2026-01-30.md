# UID Standardization Migration - Underscore Convention

**Date:** 2026-01-30
**Status:** Planning
**Author:** Claude Code
**Related:** ADR-036 (to be created)

## Executive Summary

SKUEL currently uses three different UID separators (`.`, `_`, `:`) inconsistently across the codebase. This migration standardizes all non-hierarchical entity UIDs to use underscore (`_`) notation, reserving dot (`.`) notation exclusively for hierarchical curriculum entities.

**Impact:** Breaking change for existing data. Requires database migration.

## Problem Statement

### Current Inconsistent State

| Entity Type | Current Format | Factory/Method | Consistency |
|-------------|---------------|----------------|-------------|
| User | `user_{username}` | `create_user()` | ✅ Underscore |
| Task (core) | `task.{random}` | `generate_random_uid()` | ❌ Dot |
| Task (scheduling) | `task:{timestamp}` | Hardcoded | ❌ Colon |
| Goal | `goal.{random}` | `generate_random_uid()` | ❌ Dot |
| Habit | `habit.{random}` | `generate_random_uid()` | ❌ Dot |
| Event | `event_{slug}_{random}` | `generate_uid()` | ✅ Underscore |
| Choice | `choice.{random}` | `generate_random_uid()` | ❌ Dot |
| Principle | `principle_{label}_{ts}` | Hardcoded | ✅ Underscore |
| KU | `ku.domain.topic` | `generate_knowledge_uid()` | ✅ Dot (hierarchical) |
| Domain | `dom.technology` | `generate_domain_uid()` | ✅ Dot (hierarchical) |
| Learning Path | `path.level.subject` | `generate_path_uid()` | ✅ Dot (hierarchical) |
| Askesis | `askesis.{random}` | `generate_random_uid()` | ❌ Dot |
| Report | `report_{random}` | `generate_uid()` | ✅ Underscore |

### Critical Bugs Found

1. **Session.py Default User Mismatch:**
   - Code expects: `"user.mike"` (dot)
   - Factory creates: `user_mike` (underscore)
   - Result: Session fails to find user

2. **Task UID Duality:**
   - Core service creates: `task.{random}`
   - Scheduling service creates: `task:{timestamp}`
   - Result: Inconsistent query patterns

## Target State

### UID Convention Rules

**Rule 1: Underscore for Non-Hierarchical Entities**
All entities without parent-child hierarchy use underscore (`_`):
- Activity Domains: Task, Goal, Habit, Event, Choice, Principle
- Infrastructure: User, Askesis, Report, Session
- Format: `{entity_type}_{identifier}`

**Rule 2: Dot for Hierarchical Curriculum Entities**
Only curriculum entities with parent-child relationships use dot (`.`):
- Knowledge Units: `ku.domain.topic.subtopic`
- Domains: `dom.parent.child`
- Learning Paths: `path.level.subject`
- Learning Steps: `ls.parent.step` (if hierarchical)
- Format: `{prefix}.{hierarchy}.{leaf}`

**Rule 3: No Colons**
Colon notation is deprecated. All uses must be migrated to underscore.

### Target UID Formats

| Entity Type | Target Format | Example |
|-------------|--------------|---------|
| User | `user_{username}` | `user_mike` |
| Task | `task_{random}` | `task_a1b2c3d4` |
| Goal | `goal_{random}` | `goal_x7y8z9w0` |
| Habit | `habit_{random}` | `habit_p9q8r7s6` |
| Event | `event_{random}` | `event_m5n4o3p2` |
| Choice | `choice_{random}` | `choice_k1l2m3n4` |
| Principle | `principle_{random}` | `principle_a9b8c7d6` |
| Askesis | `askesis_{random}` | `askesis_f5g6h7i8` |
| Report | `report_{random}` | `report_j3k4l5m6` |
| Option | `option_{random}` | `option_n7o8p9q0` |
| KU | `ku.{hierarchy}` | `ku.yoga.meditation` (NO CHANGE) |
| Domain | `dom.{hierarchy}` | `dom.technology.ai` (NO CHANGE) |
| Path | `path.{hierarchy}` | `path.beginner.python` (NO CHANGE) |
| LS | `ls.{hierarchy}` | `ls.parent.step` (NO CHANGE) |

## Migration Phases

### Phase 1: Code Changes (Breaking - Prepare) ✅ SAFE TO DEPLOY

**No data migration required. New entities use new format.**

#### 1.1 Update UIDGenerator Core (HIGH PRIORITY)

**File:** `/core/utils/uid_generator.py`

```python
@classmethod
def generate_random_uid(cls, prefix: str = "ku") -> str:
    """
    Generate a random UID for non-hierarchical entities.

    Args:
        prefix: Entity type prefix (task, goal, habit, etc.)

    Returns:
        Random UID with underscore separator: {prefix}_{random}

    Examples:
        - generate_random_uid("task") -> "task_a1b2c3d4"
        - generate_random_uid("goal") -> "goal_x7y8z9w0"

    Note: Curriculum entities (ku, dom, path) should use their
          specialized generators (generate_knowledge_uid, etc.)
    """
    random_part = uuid.uuid4().hex[:8]
    return f"{prefix}_{random_part}"  # CHANGED: . -> _
```

**Docstring Updates:**
- Update all examples in UIDGenerator class docstring
- Update method docstrings to reflect underscore convention
- Add warning that dot notation is reserved for curriculum

#### 1.2 Fix Critical Session Bug (HIGH PRIORITY)

**File:** `/core/auth/session.py` line 51

```python
# BEFORE:
DEFAULT_DEV_USER = os.getenv("SKUEL_DEFAULT_DEV_USER", "user.mike")

# AFTER:
DEFAULT_DEV_USER = os.getenv("SKUEL_DEFAULT_DEV_USER", "user_mike")
```

**File:** `/core/auth/session.py` line 50 (comment)

```python
# BEFORE:
# If SKUEL_DEFAULT_DEV_USER is not set, defaults to "user.mike" for backwards compatibility

# AFTER:
# If SKUEL_DEFAULT_DEV_USER is not set, defaults to "user_mike" (underscore convention)
```

#### 1.3 Fix Hardcoded Patterns (MEDIUM PRIORITY)

**File:** `/core/services/tasks/tasks_scheduling_service.py` line 479

```python
# BEFORE:
uid=f"task:{self._generate_uid()}",

# AFTER:
uid=UIDGenerator.generate_random_uid("task"),
```

Remove the `_generate_uid()` helper method (lines 500-502).

**File:** `/core/services/principles/principles_core_service.py`

```python
# BEFORE (line ~180):
uid=f"principle_{label.lower().replace(' ', '_')}_{datetime.now().timestamp()}",

# AFTER:
uid=UIDGenerator.generate_random_uid("principle"),
```

#### 1.4 Fix Docstring Examples (LOW PRIORITY)

Update all docstring examples that reference UIDs:

**Files to update:**
- `/core/services/protocols/query_types.py` - Change `"user.mike"` to `"user_mike"`
- `/core/services/user/debounced_invalidator.py` - Update examples
- `/core/services/habits/habits_intelligence_service.py` - Update examples
- `/core/services/tasks/tasks_intelligence_service.py` - Update examples
- `/core/services/goals/goals_intelligence_service.py` - Update examples
- `/core/services/principles/principles_core_service.py` - Update examples
- `/adapters/inbound/route_factories/query_route_factory.py` - Update examples

Search pattern: `grep -r '"user\.` and `"task\.` and `"goal\.` in docstrings

#### 1.5 Update Tests (CRITICAL)

**Test files expecting old format:**
```bash
# Find all tests that hardcode dot notation
grep -r "task\." tests/ --include="*.py" | grep -v ".pyc"
grep -r "goal\." tests/ --include="*.py" | grep -v ".pyc"
grep -r "user\." tests/ --include="*.py" | grep -v ".pyc"
```

Update assertions to expect underscore format:
- `assert uid.startswith("task.")` → `assert uid.startswith("task_")`
- `"task.123"` → `"task_123"`
- etc.

### Phase 2: Data Migration (Breaking - Execute) ⚠️ REQUIRES DOWNTIME

**Migrates existing UIDs in database.**

#### 2.1 Pre-Migration Validation

**Script:** `/scripts/migrations/validate_uid_migration.py`

```python
"""
Pre-migration validation script.

Checks:
1. Count entities with dot notation (activity domains)
2. Count entities with colon notation
3. Verify no curriculum entities will be affected
4. Estimate migration time
5. Generate rollback script
"""

async def validate_migration():
    # Count entities by UID pattern
    activity_domains = ["Task", "Goal", "Habit", "Event", "Choice", "Principle"]

    for label in activity_domains:
        # Count dot notation
        dot_count = await driver.execute_query(
            f"MATCH (n:{label}) WHERE n.uid CONTAINS '.' RETURN count(n)"
        )

        # Count colon notation
        colon_count = await driver.execute_query(
            f"MATCH (n:{label}) WHERE n.uid CONTAINS ':' RETURN count(n)"
        )

        print(f"{label}: {dot_count} dots, {colon_count} colons")

    # Verify curriculum entities NOT affected
    curriculum_count = await driver.execute_query(
        "MATCH (n) WHERE n.uid STARTS WITH 'ku.' OR n.uid STARTS WITH 'dom.' "
        "OR n.uid STARTS WITH 'path.' RETURN count(n)"
    )
    print(f"Curriculum entities (should NOT migrate): {curriculum_count}")
```

#### 2.2 Backup Database

```bash
# Create backup before migration
neo4j-admin database dump neo4j --to-path=/backups/pre-uid-migration-2026-01-30
```

#### 2.3 Migration Script

**Script:** `/scripts/migrations/migrate_uids_to_underscore.py`

```python
"""
UID Migration Script - Dot/Colon to Underscore

Migrates all activity domain and infrastructure entity UIDs
from dot (.) or colon (:) notation to underscore (_) notation.

DOES NOT TOUCH curriculum entities (ku., dom., path., ls.)
"""

import asyncio
from neo4j import AsyncGraphDatabase

# Entity types to migrate (non-hierarchical)
ACTIVITY_DOMAINS = ["Task", "Goal", "Habit", "Event", "Choice", "Principle"]
INFRASTRUCTURE = ["Askesis", "Report", "Option", "Session"]

async def migrate_entity_uids(driver, label: str):
    """
    Migrate UIDs for a specific entity label.

    Changes:
    - task.abc123 -> task_abc123
    - task:abc123 -> task_abc123
    - goal.xyz789 -> goal_xyz789
    """

    # Step 1: Find entities with old format
    query = f"""
    MATCH (n:{label})
    WHERE n.uid CONTAINS '.' OR n.uid CONTAINS ':'
    AND NOT n.uid STARTS WITH 'ku.'
    AND NOT n.uid STARTS WITH 'dom.'
    AND NOT n.uid STARTS WITH 'path.'
    AND NOT n.uid STARTS WITH 'ls.'
    RETURN n.uid as old_uid
    """

    result = await driver.execute_query(query)
    entities_to_migrate = [record["old_uid"] for record in result.records]

    print(f"{label}: Found {len(entities_to_migrate)} entities to migrate")

    # Step 2: Migrate each entity
    for old_uid in entities_to_migrate:
        # Convert . or : to _
        new_uid = old_uid.replace('.', '_').replace(':', '_')

        # Update entity UID
        update_query = f"""
        MATCH (n:{label} {{uid: $old_uid}})
        SET n.uid = $new_uid
        RETURN n.uid as new_uid
        """

        await driver.execute_query(update_query, old_uid=old_uid, new_uid=new_uid)
        print(f"  Migrated: {old_uid} -> {new_uid}")

async def main():
    driver = AsyncGraphDatabase.driver(
        "neo4j+s://...",
        auth=("neo4j", "...")
    )

    print("Starting UID migration...")
    print("=" * 60)

    # Migrate activity domains
    for label in ACTIVITY_DOMAINS:
        await migrate_entity_uids(driver, label)

    # Migrate infrastructure
    for label in INFRASTRUCTURE:
        await migrate_entity_uids(driver, label)

    print("=" * 60)
    print("Migration complete!")

    await driver.close()

if __name__ == "__main__":
    asyncio.run(main())
```

#### 2.4 Relationship Updates

Some relationships may store UIDs as properties. Check and update:

```cypher
// Find relationships with UID properties
MATCH ()-[r]->()
WHERE r.source_uid IS NOT NULL OR r.target_uid IS NOT NULL
RETURN type(r), count(r)

// Update relationship properties if needed
MATCH ()-[r]->()
WHERE r.source_uid CONTAINS '.' OR r.source_uid CONTAINS ':'
SET r.source_uid = replace(replace(r.source_uid, '.', '_'), ':', '_')
```

#### 2.5 Post-Migration Validation

**Script:** `/scripts/migrations/validate_uid_migration_complete.py`

```python
"""
Post-migration validation.

Verifies:
1. No activity/infrastructure entities have dot/colon UIDs
2. All curriculum entities still have dot UIDs (unchanged)
3. All relationships reference valid UIDs
4. No orphaned entities
"""

async def validate_complete():
    # Check no dots/colons in activity domains
    activity_domains = ["Task", "Goal", "Habit", "Event", "Choice", "Principle"]

    for label in activity_domains:
        invalid_count = await driver.execute_query(
            f"MATCH (n:{label}) "
            f"WHERE n.uid CONTAINS '.' OR n.uid CONTAINS ':' "
            f"RETURN count(n)"
        )

        if invalid_count > 0:
            raise ValueError(f"{label} still has {invalid_count} entities with old format!")

    # Verify curriculum unchanged
    curriculum_count = await driver.execute_query(
        "MATCH (n) WHERE n.uid STARTS WITH 'ku.' RETURN count(n)"
    )
    print(f"✅ Curriculum entities preserved: {curriculum_count}")

    # Check for orphaned relationships
    orphaned = await driver.execute_query(
        "MATCH (n)-[r]->(m) WHERE n.uid IS NULL OR m.uid IS NULL RETURN count(r)"
    )

    if orphaned > 0:
        raise ValueError(f"Found {orphaned} orphaned relationships!")

    print("✅ All validations passed!")
```

### Phase 3: Deployment & Rollback (Breaking - Deploy) 🚀

#### 3.1 Deployment Steps

1. **Announce Downtime** (estimate 5-15 minutes for typical database)
2. **Stop Application**
   ```bash
   systemctl stop skuel
   ```

3. **Backup Database**
   ```bash
   neo4j-admin database dump neo4j --to-path=/backups/pre-uid-migration
   ```

4. **Run Migration Script**
   ```bash
   poetry run python scripts/migrations/migrate_uids_to_underscore.py
   ```

5. **Validate Migration**
   ```bash
   poetry run python scripts/migrations/validate_uid_migration_complete.py
   ```

6. **Deploy New Code** (Phase 1 changes)
   ```bash
   git pull origin main
   poetry install
   ```

7. **Start Application**
   ```bash
   systemctl start skuel
   ```

8. **Smoke Tests**
   - Create new task (verify `task_` UID)
   - Login as user (verify `user_` lookup works)
   - Run integration tests

#### 3.2 Rollback Plan

If migration fails or issues arise:

1. **Stop Application**
   ```bash
   systemctl stop skuel
   ```

2. **Restore Database**
   ```bash
   neo4j-admin database load neo4j --from-path=/backups/pre-uid-migration --overwrite-destination=true
   ```

3. **Revert Code**
   ```bash
   git checkout <previous-commit>
   poetry install
   ```

4. **Start Application**
   ```bash
   systemctl start skuel
   ```

#### 3.3 Post-Deployment Monitoring

Monitor for 24 hours:
- UID format in logs (should see `task_`, not `task.`)
- User lookup errors (session.py bug fix)
- Entity creation errors
- Search/query performance

### Phase 4: Cleanup & Documentation (Non-Breaking) 📚

#### 4.1 Create ADR

**File:** `/docs/decisions/ADR-036-uid-underscore-standardization.md`

Document:
- Context: Mixed UID formats causing bugs
- Decision: Standardize on underscore for non-hierarchical
- Consequences: Breaking change, requires migration
- Alternatives considered: Keep mixed, use only dots
- Rationale: Underscore already used for Users, clearer parsing

#### 4.2 Update CLAUDE.md

**File:** `/docs/CLAUDE.md`

Add section:
```markdown
## UID Naming Conventions

**Core Principle:** "Underscores for entities, dots for hierarchy"

| Pattern | Use Case | Example |
|---------|----------|---------|
| `{type}_{identifier}` | Activity domains, users, infrastructure | `task_a1b2c3d4`, `user_mike` |
| `{prefix}.{hierarchy}` | Curriculum entities with parent-child | `ku.yoga.meditation`, `dom.tech.ai` |

**NEVER use:**
- Dot (`.`) for non-hierarchical entities
- Colon (`:`) for any entity
- Mixed separators in same entity type

**See:** `/docs/decisions/ADR-036-uid-underscore-standardization.md`
```

#### 4.3 Update Type Definitions

**File:** `/core/types/uid_types.py` (create if needed)

```python
"""
UID type definitions and validation.

UID Format Rules:
- Activity domains: {type}_{random8}
- Users: user_{username}
- Curriculum: {prefix}.{hierarchy}
"""

import re
from typing import Literal

# UID type hints
UserUID = str  # Format: user_{username}
TaskUID = str  # Format: task_{random8}
GoalUID = str  # Format: goal_{random8}
# ... etc

def validate_uid_format(uid: str, entity_type: Literal["activity", "curriculum"]) -> bool:
    """Validate UID matches expected format."""
    if entity_type == "activity":
        # Must use underscore, no dots except curriculum prefixes
        if uid.startswith(("ku.", "dom.", "path.", "ls.")):
            return False
        return "_" in uid and "." not in uid and ":" not in uid

    elif entity_type == "curriculum":
        # Must use dot notation
        return "." in uid and uid.split(".")[0] in ["ku", "dom", "path", "ls"]

    return False
```

#### 4.4 Add Runtime Validation (Optional)

**File:** `/core/utils/uid_generator.py`

Add validation to backends:

```python
def _validate_uid_format(self, uid: str):
    """Warn if UID uses deprecated format."""
    if self.label not in ["Ku", "Domain", "LearningPath", "LearningStep"]:
        # Non-curriculum entity
        if "." in uid or ":" in uid:
            logger.warning(
                f"Entity {self.label} has deprecated UID format: {uid}. "
                f"Expected underscore notation. Run migration script."
            )
```

## Testing Strategy

### Unit Tests

**File:** `/tests/unit/test_uid_generator.py`

```python
def test_generate_random_uid_uses_underscore():
    """Verify generate_random_uid returns underscore format."""
    uid = UIDGenerator.generate_random_uid("task")
    assert uid.startswith("task_")
    assert "." not in uid
    assert ":" not in uid
    assert len(uid.split("_")[1]) == 8

def test_generate_knowledge_uid_uses_dot():
    """Verify curriculum UIDs still use dot notation."""
    uid = UIDGenerator.generate_knowledge_uid("meditation", domain_uid="dom.yoga")
    assert uid.startswith("ku.")
    assert "ku.yoga.meditation" in uid

def test_deprecated_formats_rejected():
    """Verify old formats are not generated."""
    uid = UIDGenerator.generate_random_uid("goal")
    assert not uid.startswith("goal.")
    assert not uid.startswith("goal:")
```

### Integration Tests

**File:** `/tests/integration/test_uid_migration.py`

```python
async def test_task_creation_uses_underscore(tasks_service):
    """Verify newly created tasks use underscore UIDs."""
    result = await tasks_service.create_task(
        TaskRequest(title="Test", description="Test")
    )
    assert result.is_ok
    task = result.value
    assert task.uid.startswith("task_")

async def test_user_lookup_works_with_underscore(user_service):
    """Verify user lookup works with underscore UIDs."""
    result = await user_service.get_user("user_mike")
    assert result.is_ok
    assert result.value is not None

async def test_curriculum_unchanged(ku_service):
    """Verify curriculum entities still use dot notation."""
    result = await ku_service.create_ku(
        KuRequest(title="Test KU", domain="yoga")
    )
    assert result.is_ok
    ku = result.value
    assert ku.uid.startswith("ku.")
```

### Manual Testing Checklist

- [ ] Create new task - verify UID is `task_` format
- [ ] Create new goal - verify UID is `goal_` format
- [ ] Create new user - verify UID is `user_` format
- [ ] Login as user - verify session lookup works
- [ ] Create KU - verify UID is still `ku.` format
- [ ] Search for tasks - verify results returned
- [ ] View relationships - verify UIDs displayed correctly
- [ ] Run full test suite - all tests pass

## Risk Assessment

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Data corruption | CRITICAL | LOW | Full backup before migration |
| User lockout | HIGH | MEDIUM | Fix session.py bug in Phase 1 |
| Orphaned relationships | MEDIUM | LOW | Validation scripts catch issues |
| Performance degradation | LOW | LOW | UIDs are indexed, format doesn't affect perf |
| Rollback required | MEDIUM | LOW | Comprehensive rollback plan |

## Timeline Estimate

| Phase | Effort | Duration |
|-------|--------|----------|
| Phase 1: Code changes | 4 hours | 1 day |
| Phase 2: Migration prep | 2 hours | 1 day |
| Phase 3: Execute & deploy | 1 hour | 1 day (includes testing) |
| Phase 4: Documentation | 2 hours | 1 day |
| **Total** | **9 hours** | **4 days** |

Note: Duration includes testing, review, and buffer time.

## Success Criteria

- [ ] All new entities use underscore notation
- [ ] No entities (except curriculum) have dot/colon UIDs
- [ ] Session bug fixed - users can login
- [ ] All tests pass
- [ ] No performance degradation
- [ ] Documentation updated
- [ ] ADR created

## References

- UIDGenerator: `/core/utils/uid_generator.py`
- Session bug: `/core/auth/session.py:51`
- Audit document: Created 2026-01-30
- Related issue: Mixed UID formats causing lookup failures
