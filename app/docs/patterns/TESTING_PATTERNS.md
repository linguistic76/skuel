---
title: Integration Testing Patterns
updated: 2026-01-07
category: patterns
related_skills:
- pytest
related_docs:
- /docs/patterns/BACKEND_OPERATIONS_ISP.md
- /docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md
- /docs/patterns/UNIFIED_INGESTION_GUIDE.md
---

# Integration Testing Patterns

*Last updated: 2026-01-07*

**Core Principle:** "Tests should respect and validate system design, not work around it"

This document captures critical patterns for writing integration tests in SKUEL. These patterns emerged from real test failures that revealed the system's design - the failures were teachers, showing us where tests didn't align with architectural commitments.

---
## Related Skills

For implementation guidance, see:
- [@pytest](../../.claude/skills/pytest/SKILL.md)


## Pattern 1: Cascade Deletion for Entity Cleanup

### The Problem

Activity Domain entities have auto-created user relationships. Without `cascade=True`, cleanup fails:

```python
# ❌ FAILS - Entity has HAS_TASK relationship
await tasks_backend.delete("task_test_001")
# Error: "Cannot delete Task 'task_test_001' - has existing relationships"
```

### The Solution

Always use `cascade=True` for test cleanup:

```python
# ✅ WORKS - Deletes entity AND its relationships
await tasks_backend.delete("task_test_001", cascade=True)
```

### Complete Cleanup Pattern

```python
@pytest.mark.asyncio
async def test_some_feature(tasks_backend, test_user_uid, create_test_users):
    """Test with proper cleanup."""
    # Setup
    task = Task(
        uid="task_test_001",
        user_uid=test_user_uid,
        title="Test Task",
        status=EntityStatus.DRAFT,
        priority=Priority.MEDIUM,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    create_result = await tasks_backend.create(task)
    assert create_result.is_ok, "Setup failed"

    try:
        # Test logic here
        ...

        # Assertions
        assert result.is_ok
    finally:
        # Cleanup (cascade=True for auto-created relationships)
        result = await tasks_backend.delete("task_test_001", cascade=True)
        assert result.is_ok, "Cleanup failed"
```

### Batch Cleanup Pattern

```python
# Cleanup multiple entities in loop
for uid in entity_uids:
    result = await backend.delete(uid, cascade=True)
    assert result.is_ok, f"Cleanup failed: {uid}"
```

### Which Domains Require cascade=True?

| Domain | cascade=True Required | Reason |
|--------|----------------------|--------|
| **Tasks** | ✅ Yes | HAS_TASK auto-created |
| **Goals** | ✅ Yes | HAS_GOAL auto-created |
| **Habits** | ✅ Yes | HAS_HABIT auto-created |
| **Events** | ✅ Yes | HAS_EVENT auto-created |
| **Choices** | ✅ Yes | HAS_CHOICE auto-created |
| **Principles** | ✅ Yes | HAS_PRINCIPLE auto-created |
| **KU** | ❌ No* | No ownership relationship |
| **LS** | ❌ No* | No ownership relationship |
| **LP** | ❌ No* | No ownership relationship |
| **MOC** | ❌ No* | No ownership relationship |

*Unless the entity has other relationships (REQUIRES, ENABLES, etc.)

---

## Pattern 2: UID Format Consistency

### The Problem

SKUEL normalizes UIDs during ingestion - colons become dots:

```
External format: ku:python-basics  →  Internal format: ku.python-basics
```

Tests that use colon notation for retrieval will fail:

```python
# ❌ FAILS - Database has "ku.simple-test", not "ku:simple-test"
result = await ku_service.get("ku:simple-test")
# Error: "Knowledge unit ku:simple-test not found"
```

### The Solution

Use **dot notation** (internal format) consistently in tests:

```python
# ✅ WORKS - Matches internal format
result = await ku_service.get("ku.simple-test")
```

### YAML Test Files

When writing YAML test fixtures, use dot notation:

```yaml
# ✅ CORRECT - dot notation
---
uid: ku.simple-test
title: Simple Test
domain: tech
---

# ❌ WRONG - colon notation will be normalized
---
uid: ku:simple-test  # Stored as ku.simple-test
title: Simple Test
domain: tech
---
```

### Assertions

Match the internal format in assertions:

```python
# ✅ CORRECT
assert ku_dto.uid == "ku.simple-test"

# ❌ WRONG - won't match
assert ku_dto.uid == "ku:simple-test"
```

### UID Normalization Reference

| Input | Normalized | Used Where |
|-------|------------|------------|
| `ku:name` | `ku.name` | Ingestion, storage, retrieval |
| `ku.name` | `ku.name` | (No change) |
| `ku name` | `ku-name` | Space handling |

**Key Insight:** Tests are integration tests - they should use the **internal format** to validate the system correctly stores and retrieves data.

---

## Pattern 3: Mock Method Naming

### The Problem

Mock setups must exactly match actual method signatures:

```python
# ❌ FAILS - Method is called update_assignment_status, not update_status
service.update_status.return_value = Result.ok(assignment)

# Later assertion fails
status_calls = mock_service.update_status.call_args_list  # Empty!
```

### The Solution

Always verify actual method names before mocking:

```python
# ✅ CORRECT - Matches actual method signature
service.update_assignment_status.return_value = Result.ok(assignment)

# Assertion works
status_calls = mock_service.update_assignment_status.call_args_list
```

### Best Practices

1. **Check the service interface** before writing mock setup
2. **Use IDE autocompletion** to verify method names
3. **Grep for actual usage** in production code if unsure:
   ```bash
   grep -r "assignment_service\." core/services/
   ```

---

## Pattern 4: Fixture-Based Test Setup

### Standard Fixtures

SKUEL integration tests use pytest fixtures for common setup:

```python
@pytest.fixture
async def test_user_uid():
    """Standard test user UID."""
    return "user.test"

@pytest.fixture
async def create_test_users(user_backend, test_user_uid):
    """Ensure test users exist in database."""
    user = User(uid=test_user_uid, ...)
    await user_backend.create(user)
    yield
    await user_backend.delete(test_user_uid, cascade=True)

@pytest.fixture
async def tasks_backend(neo4j_container):
    """Backend with connection to test Neo4j."""
    driver = AsyncGraphDatabase.driver(neo4j_container.get_connection_url())
    backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
    yield backend
    await driver.close()
```

### Fixture Dependency Chain

```
neo4j_container
    └── driver
        └── backends (tasks_backend, goals_backend, etc.)
            └── services (tasks_service, goals_service, etc.)
                └── test functions
```

### Clean Database Fixture

```python
@pytest.fixture
async def clean_neo4j(neo4j_container):
    """Start each test with empty database."""
    driver = AsyncGraphDatabase.driver(neo4j_container.get_connection_url())
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    yield driver
    await driver.close()
```

---

## Pattern 5: Asserting Result Types

### Standard Assertion Pattern

```python
result = await service.create(entity)

# Always check .is_ok FIRST
assert result.is_ok, f"Operation failed: {result.error}"

# Then access .value
entity = result.value
assert entity.uid == expected_uid
```

### Error Case Testing

```python
result = await service.get("nonexistent")

# Check error case
assert result.is_error
assert "not found" in str(result.error).lower()
```

### Pagination Result Pattern

```python
result = await backend.get_user_entities(user_uid=test_user_uid)
assert result.is_ok

# Unpack pagination tuple
entities, total_count = result.value
assert len(entities) == expected_count
```

---

## Anti-Patterns to Avoid

### ❌ Don't Skip Cleanup

```python
# BAD - Leaves test data in database
async def test_bad():
    await backend.create(entity)
    assert result.is_ok
    # No cleanup - pollutes database
```

### ❌ Don't Use Colon UIDs for Internal Operations

```python
# BAD - Uses external format internally
await service.get("ku:topic")  # Will fail
```

### ❌ Don't Assume Mock Methods

```python
# BAD - Assumes method name without verification
mock.some_method.return_value = ...
```

### ❌ Don't Forget cascade=True

```python
# BAD - Will fail for user-owned entities
await backend.delete(uid)  # Missing cascade=True
```

---

## Test Organization

### Directory Structure

```
tests/
├── unit/                    # Pure logic tests (no I/O)
│   └── test_domain_models.py
├── integration/             # Tests with real Neo4j
│   ├── test_user_entity_tracking.py
│   ├── test_yaml_roundtrip.py
│   └── conftest.py         # Shared fixtures
└── conftest.py             # Root fixtures
```

### Naming Conventions

```python
# Test function naming
def test_<feature>_<scenario>():
    """Test <what> when <condition>."""
    pass

# Examples
def test_task_creation_with_user_relationship():
    """Test that creating a task auto-creates HAS_TASK relationship."""
    pass

def test_cascade_delete_removes_relationships():
    """Test that cascade=True removes entity and all relationships."""
    pass
```

---

## Key Files

| File | Purpose |
|------|---------|
| `tests/integration/conftest.py` | Integration test fixtures |
| `tests/integration/test_user_entity_tracking.py` | User relationship tests |
| `tests/integration/test_yaml_roundtrip.py` | Ingestion roundtrip tests |
| `tests/conftest.py` | Root pytest configuration |

---

## Philosophy

These patterns reflect SKUEL's core philosophy:

1. **Tests as Teachers** - Test failures reveal architectural truths
2. **System Design Over Convenience** - Tests should validate design, not work around it
3. **Explicit Over Implicit** - `cascade=True` makes intention clear
4. **One Path Forward** - Use internal formats, not external conveniences

> "Type errors as teachers, showing us where components don't flow together properly. By listening to them, we strengthen the core." 🧘‍♂️
