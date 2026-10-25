---
title: Testing Patterns
updated: 2026-10-25
category: patterns
related_skills:
- pytest
related_docs:
- /docs/patterns/BACKEND_OPERATIONS_ISP.md
- /docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md
- /docs/patterns/UNIFIED_INGESTION_GUIDE.md
- /docs/patterns/linter_rules.md
---
# Testing Patterns

*Last updated: 2026-03-19*

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
# ❌ FAILS - Entity has OWNS relationship
await tasks_backend.delete("task.test-001")
# Error: "Cannot delete Task 'task.test-001' - has existing relationships"
```

### The Solution

Always use `cascade=True` for test cleanup:

```python
# ✅ WORKS - Deletes entity AND its relationships
await tasks_backend.delete("task.test-001", cascade=True)
```

### Complete Cleanup Pattern

```python
@pytest.mark.asyncio
async def test_some_feature(tasks_backend, ensure_test_users):
    """Test with proper cleanup."""
    # Setup
    task = Task(
        uid="task.test-001",
        user_uid=seed_user_uid("test"),
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
        result = await tasks_backend.delete("task.test-001", cascade=True)
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
| **Tasks** | ✅ Yes | OWNS auto-created |
| **Goals** | ✅ Yes | OWNS auto-created |
| **Habits** | ✅ Yes | OWNS auto-created |
| **Events** | ✅ Yes | OWNS auto-created |
| **Choices** | ✅ Yes | OWNS auto-created |
| **Principles** | ✅ Yes | OWNS auto-created |
| **KU** | ❌ No* | No ownership relationship |
| **PS** | ❌ No* | No ownership relationship |
| **LP** | ❌ No* | No ownership relationship |
| **MOC** | ❌ No* | No ownership relationship |

*Unless the entity has other relationships (REQUIRES, ENABLES, etc.)

---

## Pattern 2: UID Format Consistency

### The Problem

Dot form is the authoring AND stored spelling — authored = stored, verbatim. The colon
spelling was retired 2026-08-14 and its ingestion input alias deleted in the same ruling:

```
Colon input: ku:python-basics  →  REJECTED (prefix validation error, no rewrite)
```

Tests that use the colon spelling for retrieval will fail — the graph never stores colons:

```python
# ❌ FAILS - Database has "ku.simple-test", not "ku:simple-test"
result = await ku_service.get_ku("ku:simple-test")
# Error: "Knowledge unit ku:simple-test not found"
```

### The Solution

Use **dot notation** (the stored format) consistently in tests:

```python
# ✅ WORKS - Matches stored format
result = await ku_service.get_ku("ku.simple-test")
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

# ❌ WRONG - colon spelling is rejected at ingestion (input alias deleted 2026-08-14)
---
uid: ku:simple-test  # Fails prefix validation loudly
title: Simple Test
domain: tech
---
```

### Assertions

Match the stored format in assertions:

```python
# ✅ CORRECT
assert ku_dto.uid == "ku.simple-test"

# ❌ WRONG - won't match
assert ku_dto.uid == "ku:simple-test"
```

### UID Input Reference

| Input | Outcome | Why |
|-------|---------|-----|
| `ku.name` | Stored verbatim | Authored = stored — no rewrite of any kind |
| `ku:name` | Rejected (validation error) | Colon input alias deleted 2026-08-14 |

(There is no normalization step: spaces and case are never touched either — a UID
with spaces is an authoring error the validator reports, not something the
boundary fixes.)

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

SKUEL integration tests use the fixtures in `tests/integration/conftest.py` (the full list:
`.claude/skills/pytest/fixtures-reference.md`). The driver is the shared session one; a backend
the composition root builds comes from `create_all_backends` itself — never a copy of its
arguments (`tests/unit/test_production_backend_census.py` fails one):

```python
@pytest.fixture
def production_backends(neo4j_driver):
    """Every backend the composition root builds, over the shared container."""
    return build_production_backends(neo4j_driver)  # tests/helpers/production_backends.py


@pytest_asyncio.fixture
async def tasks_backend(production_backends):
    return production_backends["tasks_backend"]  # TasksBackend, as production builds it


async def test_create_task(tasks_backend, clean_neo4j, ensure_test_users):
    task = Task(uid="task.test-create", title="Test", user_uid=seed_user_uid("test"))
    assert (await tasks_backend.create(task)).is_ok
```

### Fixture Dependency Chain

```
neo4j_container (session)
    └── neo4j_driver (session)
        ├── clean_neo4j (function: wipes all but :User / :MigrationRecord, before and after)
        └── production_backends (function: create_all_backends over the driver)
            └── tasks_backend, goals_backend, …, ku_backend
                └── tasks_service, goals_service, … (the CORE sub-services)
                    └── test functions
```

`ensure_test_users` (session) seeds every `seed_user_uid(name)` the tier uses; a test that creates
an owned entity depends on it — the `:OWNS` write doors refuse an owner with no `:User` node.

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

### ❌ Don't Seed a UID Outside the Grammar

```python
# BAD - the retired colon spelling; no entity carries it, so this reads nothing
await service.get("ku:topic")
# BAD - an underscore is in no authored segment, and a username is no user uid
Task(uid="task_001", title="t", user_uid="user_alice")

# GOOD - an authored entity uid, a generated user uid
await service.get("ku.topic")
Task(uid="task.001", title="t", user_uid=seed_user_uid("alice"))
```

After each integration test the census reads its graph against the uid grammar
(`tests/integration/_uid_census.py`) and fails the test on a uid it wrote outside it, or
one two nodes hold. A test that writes one on purpose carries
`@pytest.mark.outside_uid_grammar("why")`. What that read cannot see — a uid created and
deleted inside one body, one on a scratch container, one a property names — the static
census (`tests/unit/test_integration_seed_uids.py`) reads from the source, every uid
literal in `tests/integration`; a uid only it sees is marked
`outside_uid_grammar("why", static_only=True)`.

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

## Unit Test Coverage for Pure Helpers

Pure helper functions (no I/O, no database) have dedicated unit tests for fast regression detection:

```
tests/unit/
├── scripts/                          # Script/tool tests
│   ├── test_lint_skuel.py            # the SKUEL lint rules, LintResult, suppression audit
│   └── test_cypher_linter.py         # the CYP rules, query extraction, helpers
├── ui/                               # UI component tests
│   ├── test_enum_helpers.py          # 52 tests — 34 bridge/helper/builder functions
│   ├── test_layout.py               # 18 tests — Size enum, 7 layout components
│   └── test_domain_stats_config.py   # 30 tests — 6 domain stat calculators
└── ...                               # Service/model unit tests
```

**Pattern:** Instantiate the target class or call the target function with synthetic data. No filesystem, database, or network access. Use `types.SimpleNamespace` for mock entities where domain models are too heavyweight.

**When to add:** Any pure function with branching logic (fallbacks, enum conversion, validation) or that processes structured data (linters, converters, formatters).

---

## Test Organization

### Directory Structure

```
tests/
├── unit/                    # Pure logic tests (no I/O)
│   ├── scripts/             # Linter tests
│   ├── ui/                  # UI helper tests
│   └── services/            # Service unit tests (mocked backends)
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
    """Test that creating a task auto-creates the OWNS relationship."""
    pass

def test_cascade_delete_removes_relationships():
    """Test that cascade=True removes entity and all relationships."""
    pass
```

---

## Key Files

| File | Purpose |
|------|---------|
| `tests/conftest.py` | Root pytest configuration |
| `tests/integration/conftest.py` | Integration test fixtures |
| `tests/integration/test_user_entity_tracking.py` | User relationship tests |
| `tests/integration/test_yaml_roundtrip.py` | Ingestion roundtrip tests |
| `tests/unit/scripts/test_lint_skuel.py` | SKUEL linter unit tests |
| `tests/unit/scripts/test_cypher_linter.py` | Cypher linter unit tests |
| `tests/unit/ui/test_enum_helpers.py` | UI enum bridge tests (52 tests) |
| `tests/unit/ui/test_layout.py` | Layout component tests (18 tests) |

---

## Philosophy

These patterns reflect SKUEL's core philosophy:

1. **Tests as Teachers** - Test failures reveal architectural truths
2. **System Design Over Convenience** - Tests should validate design, not work around it
3. **Explicit Over Implicit** - `cascade=True` makes intention clear
4. **One Path Forward** - Use internal formats, not external conveniences

> "Type errors as teachers, showing us where components don't flow together properly. By listening to them, we strengthen the core." 🧘‍♂️
