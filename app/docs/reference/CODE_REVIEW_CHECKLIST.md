---
title: Code Review Checklist - Phase 7.3
updated: 2025-11-27
status: current
category: reference
tags: [checklist, code, reference, review]
related: []
---

# Code Review Checklist - Phase 7.3
**Date**: 2025-10-03
**Status**: ✅ Mandatory for ALL Pull Requests

---

## Executive Summary

This checklist is **MANDATORY** for all SKUEL code reviews. Every pull request must pass all applicable checks before merging.

**Core Principle:** *"If it's not on the checklist, it doesn't get merged."*

Phase 7.3 establishes enforceable quality gates ensuring SKUEL's semantic-first, pure Cypher architecture is maintained.

---

## 🚨 Critical Checks (MUST PASS)

These checks are **non-negotiable**. Failure means immediate rejection.

### ✅ Phase 5 Compliance (Pure Cypher Architecture)

- [ ] **No APOC path procedures in domain services**
  - ❌ `apoc.path.subgraphNodes()`
  - ❌ `apoc.path.subgraphAll()`
  - ❌ `apoc.path.expandConfig()`
  - ❌ `apoc.path.spanningTree()`
  - ✅ OK in adapters via `ApocQueryBuilder` (infrastructure only)

- [ ] **Uses `SemanticCypherBuilder` for all graph queries**
  - ✅ `build_prerequisite_chain()`
  - ✅ `build_cross_domain_bridges()`
  - ✅ `build_hierarchical_context()`
  - ✅ `build_semantic_filter_query()`
  - ✅ `build_related_concepts_query()`

- [ ] **Pure Cypher benefits from query planner**
  - Query uses parameterized syntax (`$parameter`)
  - Query uses semantic relationship types (indexed)
  - No string concatenation (query cache works)
  - Variable-length patterns instead of APOC traversal

**Verification:**
```bash
# Search for APOC path violations
grep -r "apoc.path" core/services/ --include="*.py"
# Should return ZERO results

# Verify SemanticCypherBuilder usage
grep -r "SemanticCypherBuilder" core/services/ --include="*.py"
# Should show usage in new code
```

---

### ✅ Semantic Relationships (Type Safety)

- [ ] **Semantic types used instead of magic strings**
  - ✅ `SemanticRelationshipType.APPLIES_KNOWLEDGE`
  - ✅ `SemanticRelationshipType.REQUIRES_THEORETICAL_UNDERSTANDING`
  - ❌ `"APPLIES_KNOWLEDGE"` (magic string)
  - ❌ `"requires_knowledge"` (wrong casing)

- [ ] **Rich metadata included on relationships**
  - ✅ `confidence: float` (0.0-1.0)
  - ✅ `source: str` (e.g., "tasks_service_explicit")
  - ✅ `strength: float` (typically = confidence)
  - ✅ `notes: Optional[str]` (human explanation)
  - ✅ `created_at: datetime` (timestamp)

- [ ] **Provenance tracking via source field**
  - Source indicates creator: `"{service}_explicit"` or `"{service}_inferred"`
  - Source is lowercase service name
  - Source is consistent across service

**Example (CORRECT):**
```python
metadata = RelationshipMetadata(
    confidence=0.95,
    source="tasks_service_explicit",  # ✅ Provenance
    strength=0.95,
    notes="Task requires FastAPI knowledge",
    created_at=None  # Backend sets
)

# Create with semantic type enum
semantic_type = SemanticRelationshipType.APPLIES_KNOWLEDGE  # ✅ Type-safe
```

**Example (WRONG):**
```python
# ❌ Magic string, no metadata
query = """
CREATE (t)-[:APPLIES_KNOWLEDGE]->(k)
"""
```

**Verification:**
```bash
# Search for magic string relationship types
grep -r '":' core/services/ --include="*.py" | grep -E "(APPLIES|REQUIRES|HAS_)"
# Review each match - should be in Cypher strings with metadata, not bare

# Verify SemanticRelationshipType imports
grep -r "from core.models.semantic_relationships import" core/services/
```

---

### ✅ Phase 7.1 Compliance (Semantic Service Pattern)

- [ ] **New services implement 3 mandatory patterns**
  - ✅ Pattern 1: `get_entity_with_semantic_context()`
  - ✅ Pattern 2: `create_semantic_relationship()`
  - ✅ Pattern 3: `find_entities_by_semantic_knowledge()`

- [ ] **Service uses protocol-based dependency injection**
  - Constructor accepts protocol interface (not concrete class)
  - Fail-fast: `if not backend: raise ValueError("Backend required")`
  - No graceful degradation

- [ ] **Returns `Result[T]` for all operations**
  - ✅ Success: `Result.ok(value)`
  - ✅ Failure: `Result.fail(error)`
  - ❌ Raises exceptions (should return Result)
  - ❌ Returns None for errors (should return Result.fail)

**Verification:**
```bash
# Check for 3 mandatory patterns in new services
grep -A 5 "get_.*_with_semantic_context" core/services/your_new_service.py
grep -A 5 "create_semantic_relationship" core/services/your_new_service.py
grep -A 5 "find_.*_by_semantic_knowledge" core/services/your_new_service.py
```

---

### ✅ Phase 7.2 Compliance (Query Decision Matrix)

- [ ] **Query method matches decision matrix**
  - Semantic traversal → `SemanticCypherBuilder`
  - Prerequisites → `build_prerequisite_chain()`
  - Simple CRUD → `UniversalNeo4jBackend[T]`
  - Batch ops (1000+) → `ApocQueryBuilder` (adapter only)

- [ ] **Includes confidence thresholds for semantic queries**
  - Default `min_confidence=0.8` for discovery
  - Default `min_confidence=0.7` for suggestions
  - Configurable via parameter

- [ ] **Uses established patterns when available**
  - Check `composable_patterns.py` first
  - Check `SemanticCypherBuilder` methods
  - Only create custom query if no pattern exists

**Verification:**
```bash
# Consult decision matrix
cat docs/QUERY_DECISION_MATRIX.md

# Check for custom queries that should use patterns
grep -r "MATCH.*KnowledgeUnit" core/services/ --include="*.py"
# Review each - should be using SemanticCypherBuilder
```

---

## 📋 Architecture Checks

### ✅ Three-Tier Type System

- [ ] **Pydantic models at external boundary**
  - API routes use `*Request` / `*Response` Pydantic models
  - Validation happens at boundary
  - No Pydantic in service layer

- [ ] **DTOs for data transfer**
  - Services accept/return DTOs
  - Mutable dataclasses
  - No business logic in DTOs

- [ ] **Domain models are frozen**
  - Core logic uses `@dataclass(frozen=True)`
  - Business logic methods on domain models
  - Immutable after creation

**Example:**
```python
# Tier 1: Pydantic (External)
class TaskCreateRequest(BaseModel):
    title: str
    due_date: Optional[date]

# Tier 2: DTO (Transfer)
@dataclass
class TaskDTO:
    uid: str
    title: str
    due_date: Optional[date]

# Tier 3: Domain (Core)
@dataclass(frozen=True)
class Task:
    uid: str
    title: str
    due_date: Optional[date]

    def is_overdue(self) -> bool:
        """Business logic here"""
        return self.due_date and self.due_date < date.today()
```

---

### ✅ Result[T] Error Handling

- [ ] **Services return `Result[T]`**
  - All async methods return `Result[T]`
  - No uncaught exceptions in business logic
  - Errors are values, not exceptions

- [ ] **Routes use `@boundary_handler`**
  - Decorator converts `Result[T]` to HTTP response
  - Automatic status code mapping
  - No manual exception handling

- [ ] **Error messages are user-friendly**
  - `user_message` for end users
  - `message` for developers
  - Includes context (entity UID, field name, etc.)

**Example:**
```python
# Service
async def get_task(self, uid: str) -> Result[Task]:
    if not uid:
        return Result.fail(validation_error(
            "Task UID is required",
            field="uid",
            user_message="Please provide a task ID"
        ))
    # ...
    return Result.ok(task)

# Route
@rt("/api/tasks/{uid}")
@boundary_handler()  # ✅ Auto-converts Result to HTTP
async def get_task_route(request, uid: str):
    return await service.get_task(uid)
```

---

### ✅ Protocol-Based Architecture

- [ ] **Services depend on protocols, not implementations**
  - Constructor accepts protocol type
  - No direct dependency on concrete classes
  - Enables easy testing with mocks

- [ ] **Protocols define clear contracts**
  - Protocol has `async def method(...) -> Result[T]:`
  - Protocol documents behavior in docstring
  - Protocol is in `core/ports/`

**Example:**
```python
# Protocol (interface)
class TaskOperations(Protocol):
    async def get_task(self, uid: str) -> Result[Optional[Task]]:
        """Get task by UID."""
        ...

# Service (depends on protocol)
class TasksService:
    def __init__(self, backend: TaskOperations):
        if not backend:
            raise ValueError("Backend required")
        self.backend = backend
```

---

## 🧪 Testing Checks

### ✅ Test Coverage

- [ ] **New services have canary tests**
  - Test all 3 semantic patterns
  - Test semantic relationship creation
  - Test query methods

- [ ] **Tests use mocks, not real Neo4j**
  - Protocol-based mocking
  - Async test fixtures
  - Fast execution (< 1s per test)

- [ ] **Tests verify semantic types**
  - Assert `SemanticRelationshipType` used
  - Assert metadata included
  - Assert confidence thresholds work

**Example:**
```python
# tests/unit/test_tasks_service.py
async def test_get_task_with_semantic_context():
    """Verify Pattern 1 implementation."""
    mock_backend = MockTaskBackend()
    service = TasksService(backend=mock_backend)

    result = await service.get_task_with_semantic_context(
        task_uid="task.123",
        min_confidence=0.8
    )

    assert result.is_ok
    assert 'knowledge_units' in result.value
    assert 'complexity_score' in result.value
```

---

### ✅ Syntax Verification

- [ ] **Code compiles cleanly**
  ```bash
  poetry run python -m py_compile path/to/file.py
  ```

- [ ] **Type hints are correct**
  ```bash
  poetry run mypy path/to/file.py
  ```

- [ ] **No unused imports**
  ```bash
  poetry run ruff check path/to/file.py
  ```

---

## 📝 Documentation Checks

### ✅ Code Documentation

- [ ] **Docstrings follow Phase 7 pattern**
  - Purpose stated clearly
  - Args documented with types
  - Returns documented with structure
  - Example usage provided

- [ ] **Semantic types documented**
  - List semantic types used in domain
  - Explain why each type chosen
  - Document confidence thresholds

**Example:**
```python
async def get_project_with_semantic_context(
    self,
    project_uid: str,
    min_confidence: float = 0.8,
    depth: int = 2
) -> Result[Dict[str, Any]]:
    """
    Get project with full semantic knowledge context.

    PHASE 7 PATTERN 1: Uses SemanticCypherBuilder for pure Cypher.

    Args:
        project_uid: Project UID
        min_confidence: Minimum confidence for knowledge (0.0-1.0)
        depth: Depth of prerequisite traversal

    Returns:
        Result[Dict] containing:
            - project: Project entity
            - knowledge_units: Required knowledge
            - prerequisites: Prerequisite chains
            - readiness_score: Knowledge readiness (0.0-1.0)
            - knowledge_gaps: UIDs below threshold

    Example:
        result = await service.get_project_with_semantic_context(
            project_uid="project.build_api",
            min_confidence=0.8
        )
    """
```

---

### ✅ Commit Messages

- [ ] **Commit follows pattern**
  - Type: feat/fix/docs/refactor/test/chore
  - Scope: domain/service/docs/config
  - Subject: concise description
  - Body: detailed explanation (if complex)

**Example:**
```
feat(tasks): implement semantic task-knowledge relationships

- Add create_semantic_relationship() method (Phase 7.1 Pattern 2)
- Use SemanticRelationshipType.APPLIES_KNOWLEDGE enum
- Include RelationshipMetadata with provenance tracking
- Add canary tests for relationship creation

Complies with Phase 7.3 code review checklist.
```

---

## 🔴 Red Flags (Immediate Rejection)

If ANY of these are found, **reject the PR immediately**:

1. **APOC path procedures in domain service**
   ```python
   # ❌ REJECT
   query = "CALL apoc.path.subgraphNodes(...)"
   ```

2. **Magic string relationship types**
   ```python
   # ❌ REJECT
   query = "CREATE (a)-[:APPLIES_KNOWLEDGE]->(b)"
   # Should use: SemanticRelationshipType.APPLIES_KNOWLEDGE
   ```

3. **No relationship metadata**
   ```python
   # ❌ REJECT
   query = "CREATE (a)-[r:APPLIES_KNOWLEDGE]->(b)"
   # Missing: confidence, source, notes, created_at
   ```

4. **Service doesn't return Result[T]**
   ```python
   # ❌ REJECT
   async def get_task(self, uid: str) -> Task:
       # Should return: Result[Task]
   ```

5. **New service missing mandatory patterns**
   ```python
   # ❌ REJECT - Missing Pattern 1, 2, or 3
   class NewService:
       # Where are the 3 mandatory semantic patterns?
   ```

6. **Unbounded graph traversal**
   ```python
   # ❌ REJECT
   query = "MATCH path = (a)-[*]->(b)"  # No depth limit!
   ```

7. **No confidence threshold on semantic query**
   ```python
   # ❌ REJECT
   query = "MATCH (a)-[r:REQUIRES_KNOWLEDGE]->(b)"
   # Missing: WHERE r.confidence >= $min_confidence
   ```

---

## ✅ Approval Criteria

PR can be approved when:

1. ✅ All critical checks pass
2. ✅ All architecture checks pass
3. ✅ Tests exist and pass
4. ✅ Documentation is complete
5. ✅ No red flags present
6. ✅ Syntax verification passes
7. ✅ Code review checklist completed

---

## 📊 Reviewer Checklist Template

Copy this template into PR review comments:

```markdown
## Phase 7.3 Code Review Checklist

### Critical Checks
- [ ] No APOC path procedures in domain services
- [ ] Uses SemanticCypherBuilder for graph queries
- [ ] Semantic types (enum) instead of magic strings
- [ ] Rich metadata (confidence, source, notes)
- [ ] Provenance tracking via source field
- [ ] Pure Cypher benefits from query planner

### Architecture
- [ ] Three-tier type system (Pydantic → DTO → Domain)
- [ ] Returns Result[T] for error handling
- [ ] Protocol-based dependency injection
- [ ] Services implement 3 mandatory patterns (if new service)

### Testing
- [ ] Canary tests for semantic patterns
- [ ] Tests use mocks (not real Neo4j)
- [ ] Syntax verification passes

### Documentation
- [ ] Docstrings follow Phase 7 pattern
- [ ] Semantic types documented
- [ ] Commit message follows convention

### Decision Matrix Compliance
- [ ] Query method matches decision matrix
- [ ] Confidence thresholds included
- [ ] Uses established patterns when available

**Red Flags:** None / List any found

**Approval:** ✅ Approved / ❌ Changes Requested

**Notes:**
```

---

## 🚀 Quick Verification Commands

Run these before requesting review:

```bash
# 1. Check for APOC violations
grep -r "apoc.path" core/services/ --include="*.py"
# Expected: No results

# 2. Verify syntax
poetry run python -m py_compile path/to/your/file.py
# Expected: No errors

# 3. Check for magic strings
grep -r '":' core/services/your_service.py | grep -E "(APPLIES|REQUIRES|HAS_)"
# Review: Should be in Cypher with metadata, not bare

# 4. Run tests
poetry run pytest tests/unit/test_your_service.py -v
# Expected: All pass

# 5. Type check
poetry run mypy core/services/your_service.py
# Expected: No errors

# 6. Lint check
poetry run ruff check core/services/your_service.py
# Expected: No violations
```

---

## 📚 References

- **Phase 5**: `/docs/PHASE_5_COMPOSABLE_MIGRATION.md` - Pure Cypher migration
- **Phase 7.1**: `/docs/PHASE_7_SEMANTIC_DEVELOPMENT_PATTERNS.md` - Service template
- **Phase 7.2**: `/docs/QUERY_DECISION_MATRIX.md` - Query guidance
- **Semantic Types**: `/core/models/semantic_relationships.py`
- **Quick Reference**: `/docs/QUERY_QUICK_REFERENCE.md`

---

## 🎯 Summary

**Before merging ANY code, verify:**

1. **No APOC in domain services** (Phase 5 compliance)
2. **SemanticCypherBuilder used** (Query decision matrix)
3. **Semantic type enums** (Type safety)
4. **Rich metadata** (Provenance tracking)
5. **Result[T] pattern** (Error handling)
6. **3 mandatory patterns** (New services only)

**When in doubt:**
- Consult decision matrix
- Check template
- Ask for review
- Follow the checklist

**This checklist is THE gate**. If it's not checked, it doesn't merge.

---

*Last Updated: October 3, 2025*
*Status: Phase 7.3 Complete - Code Review Checklist*
*Mandatory for ALL Pull Requests*
