---
title: Docstring Standards
updated: 2026-01-29
category: patterns
related_skills:
- python
related_docs: []
---

# Docstring Standards

> **Core Principle**: "Docstrings describe implementation, patterns describe approach, architecture describes design"

---
## Related Skills

For implementation guidance, see:
- [@python](../../.claude/skills/python/SKILL.md)


## Three-Layer Documentation Philosophy

SKUEL uses a three-layer approach to documentation, where each layer serves a specific purpose and audience:

| Layer | Tool | Purpose | Audience | Example |
|-------|------|---------|----------|---------|
| **Implementation** | Docstrings | What does THIS function/class do? | Code readers, IDE users | Function parameters, return types |
| **Pattern** | `/docs/patterns/` | HOW do we approach this problem? | Implementers | Service patterns, error handling |
| **Architecture** | `/docs/architecture/` | WHY is the system designed this way? | Architects, new developers | Domain structure, design decisions |

### Why This Matters

**Type errors are teachers.** When you encounter a type error, it's revealing a fundamental design issue. Don't patch it with `# type: ignore` or workarounds. Instead:

1. **Read the docstring** - Understand what THIS function does
2. **Read the pattern doc** - Understand HOW we approach this problem
3. **Read the architecture doc** - Understand WHY it's designed this way
4. **Fix the design** - Make components flow together properly

---

## When to Write Docstrings

### Always Write Docstrings For:

1. **Public APIs** - Any function/class exposed to other modules
2. **Complex Functions** - Non-trivial logic, algorithms, or business rules
3. **Service Classes** - All service classes and their public methods
4. **Protocol Definitions** - All Protocol classes and methods
5. **Data Models** - Domain models, DTOs, Pydantic models

### Skip Docstrings For:

1. **Obvious One-Liners** - `def get_name(self) -> str: return self.name`
2. **Simple Private Helpers** - Clear function name + type hints is enough
3. **Test Functions** - Test names should be self-documenting
4. **Property Getters** - Unless they do more than return a field

---

## Docstring Style Guide

SKUEL uses **Google-style docstrings** with a focus on clarity and IDE integration.

### Function Docstrings

```python
async def calculate_life_path_alignment(
    self, context: UserContext
) -> Result[float]:
    """
    Calculate 0.0-1.0 alignment score across 5 dimensions.

    Dimensions weighted as:
    - Knowledge: 25%
    - Activity: 25%
    - Goals: 20%
    - Principles: 15%
    - Momentum: 15%

    See: /docs/architecture/UNIFIED_USER_ARCHITECTURE.md
    See: /docs/intelligence/USER_CONTEXT_INTELLIGENCE.md

    Args:
        context: Rich user context (requires enrichment via build_rich())

    Returns:
        Result[float]: Alignment score 0.0-1.0, or error if context incomplete

    Raises:
        No exceptions (uses Result[T] pattern)
    """
```

**Key Elements**:
- **Summary line**: One-line description (imperative mood)
- **Details**: Explain algorithm, weights, or business logic
- **Cross-references**: Link to `/docs/` for deep dive
- **Args**: Parameter descriptions with types (already in signature)
- **Returns**: Return type and meaning (especially for Result[T])
- **Raises**: Only if exceptions are raised (prefer Result[T])

### Class Docstrings

```python
class TasksService:
    """
    Facade service for task operations.

    Orchestrates three sub-services:
    - tasks_core: CRUD operations
    - tasks_search: Search and filtering
    - tasks_intelligence: Analytics and recommendations

    See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
    See: /docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md

    Usage:
        service = TasksService(...)
        result = await service.create(dto)
    """
```

**Key Elements**:
- **Purpose**: What is this class responsible for?
- **Structure**: Key components or sub-services
- **Cross-references**: Link to architecture docs
- **Usage**: Simple example if not obvious

### Protocol Docstrings

```python
class TasksOperations(Protocol):
    """
    Protocol for task CRUD operations.

    Defines the contract for task persistence without coupling
    to specific implementations (UniversalNeo4jBackend).

    Methods follow BaseService[Task] pattern.

    See: /docs/patterns/protocol_architecture.md
    """

    async def create(self, dto: TaskDTO) -> Result[Task]:
        """Create a new task."""
        ...

    async def get(self, uid: str) -> Result[Task]:
        """Get task by UID."""
        ...
```

**Key Elements**:
- **Protocol purpose**: Why this abstraction exists
- **Contract definition**: What implementing classes must provide
- **Pattern reference**: Link to protocol architecture docs
- **Method signatures**: Brief one-line descriptions

### Module Docstrings

```python
"""
User Context Intelligence Service

Central cross-domain intelligence hub providing:
- Daily planning recommendations
- Life path alignment calculation
- Schedule-aware task suggestions
- Learning opportunity identification

This service aggregates data from all 14 domains to provide
holistic insights about the user's state and next best actions.

Architecture:
    - Extends BaseAnalyticsService (graph-native analytics)
    - Uses UserContext as primary data source
    - Provides 8 flagship intelligence methods

See: /docs/architecture/UNIFIED_USER_ARCHITECTURE.md
See: /docs/intelligence/USER_CONTEXT_INTELLIGENCE.md
"""
```

**Key Elements**:
- **Module purpose**: What does this module provide?
- **Key features**: Bullet list of main capabilities
- **Architecture notes**: How it fits in the system
- **Cross-references**: Link to comprehensive docs

---

## Cross-Referencing Pattern

Docstrings should **point to detailed documentation** for architectural context, patterns, and design decisions.

### Cross-Reference Format

```python
"""
Brief description of what this does.

See: /docs/patterns/PATTERN_NAME.md
See: /docs/architecture/ARCHITECTURE_NAME.md
See: /.claude/skills/skill-name/SKILL.md
"""
```

### When to Cross-Reference

**Always link to docs for**:
- Complex algorithms or business logic
- Architectural decisions
- Design patterns in use
- Domain-specific concepts

**Example**:
```python
async def get_ready_to_work_on_today(
    self, context: UserContext, limit: int = 10
) -> Result[list[dict[str, Any]]]:
    """
    Get tasks ready to work on today based on schedule and prerequisites.

    THE FLAGSHIP METHOD - combines schedule awareness, prerequisite
    checking, learning alignment, and priority scoring.

    Algorithm:
    1. Filter tasks by status (TODO, IN_PROGRESS)
    2. Check schedule availability (time slots)
    3. Verify prerequisites met
    4. Calculate learning alignment
    5. Score by priority, deadline, momentum
    6. Return top N recommendations

    See: /docs/intelligence/USER_CONTEXT_INTELLIGENCE.md (full algorithm)
    See: /docs/patterns/INTENT_BASED_TRAVERSAL.md (graph patterns)

    Args:
        context: Rich user context with enriched schedule/tasks/knowledge
        limit: Maximum number of tasks to return

    Returns:
        Result[list[dict]]: Ranked task recommendations with scores
    """
```

---

## Docstring Anti-Patterns

### ❌ Anti-Pattern 1: Redundant Docstrings

**Problem**: Docstring repeats what's obvious from name and type hints

```python
# BAD
def get_user_uid(self) -> UserUID:
    """Get the user UID."""
    return self.user_uid
```

**Solution**: Skip the docstring if it adds no value

```python
# GOOD
def get_user_uid(self) -> UserUID:
    return self.user_uid
```

---

### ❌ Anti-Pattern 2: Documenting Implementation Details

**Problem**: Docstring describes HOW instead of WHAT

```python
# BAD
async def search_tasks(self, query: str) -> Result[list[Task]]:
    """
    Uses UnifiedQueryBuilder to construct a Cypher query,
    executes it via backend.driver.execute_query(), then
    converts records to Task objects using from_dict().
    """
```

**Solution**: Focus on WHAT it does, link to pattern docs for HOW

```python
# GOOD
async def search_tasks(self, query: str) -> Result[list[Task]]:
    """
    Search tasks by keyword across title, description, and tags.

    See: /docs/patterns/query_architecture.md (query construction)
    See: /docs/architecture/SEARCH_ARCHITECTURE.md (search patterns)

    Args:
        query: Search keyword or phrase

    Returns:
        Result[list[Task]]: Matching tasks ranked by relevance
    """
```

---

### ❌ Anti-Pattern 3: Documenting Patterns in Docstrings

**Problem**: Trying to explain an architectural pattern in a docstring

```python
# BAD
class TasksService:
    """
    Facade service. A facade is a structural design pattern that
    provides a simplified interface to a complex subsystem. It
    orchestrates multiple sub-services (core, search, intelligence)
    by delegating calls to the appropriate service based on the
    operation type. This reduces coupling between...
    """
```

**Solution**: Brief description + link to pattern doc

```python
# GOOD
class TasksService:
    """
    Facade service for task operations.

    Orchestrates three sub-services: core, search, intelligence.

    See: /docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md
    """
```

---

## IDE Integration

Docstrings are your **primary interface** for IDE users. Write them with IDE hover tooltips in mind.

### What IDEs Show

**VS Code, PyCharm, etc. display**:
- First line (summary) in autocomplete
- Full docstring on hover
- Args/Returns in signature help

**Best Practices**:
1. **Front-load information** - Put the most important info first
2. **Be concise** - IDEs show limited space
3. **Use formatting** - Markdown works in most IDEs
4. **Link to docs** - Absolute paths work in most IDEs

---

## Examples from SKUEL

### Example 1: Service Method

```python
async def verify_ownership(
    self, uid: str, user_uid: UserUID
) -> Result[Task]:
    """
    Verify user owns this task and return it.

    Returns NotFound error if task doesn't exist OR user doesn't
    own it (security: don't leak existence of other users' tasks).

    See: /docs/patterns/OWNERSHIP_VERIFICATION.md

    Args:
        uid: Task UID (e.g., "task.daily-standup")
        user_uid: User UID (e.g., "user.john")

    Returns:
        Result[Task]: Task if owned, NotFound error otherwise
    """
```

---

### Example 2: Analytics Method

```python
async def get_completion_rate(
    self, user_uid: UserUID, time_window: str = "7d"
) -> Result[float]:
    """
    Calculate task completion rate over time window.

    Completion rate = completed / (completed + incomplete)
    Only includes tasks with due dates in the time window.

    See: /docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md

    Args:
        user_uid: User to calculate for
        time_window: "7d", "30d", "90d", or "all"

    Returns:
        Result[float]: Completion rate 0.0-1.0
    """
```

---

### Example 3: Protocol Method

```python
async def find_by(self, **filters) -> Result[list[T]]:
    """
    Find entities matching filter criteria.

    Filters use field__operator syntax (Django-style):
    - field__eq: equals
    - field__gte: greater than or equal
    - field__contains: substring match

    See: /docs/patterns/query_architecture.md

    Args:
        **filters: Field filters (e.g., status__eq="TODO")

    Returns:
        Result[list[T]]: Matching entities
    """
```

---

## Relationship with Other Docs

### Docstrings → Patterns

**When docstring says**: "Uses Result[T] pattern"
**User reads**: `/docs/patterns/ERROR_HANDLING.md`

**When docstring says**: "Follows BaseService pattern"
**User reads**: `/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md`

### Docstrings → Architecture

**When docstring says**: "Part of 14-domain architecture"
**User reads**: `/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md`

**When docstring says**: "Orchestrates sub-services"
**User reads**: `/docs/architecture/ROUTING_ARCHITECTURE.md`

### Docstrings → Skills

**When docstring says**: "Uses frozen dataclass"
**User reads**: `/.claude/skills/python/SKILL.md`

**When docstring says**: "Pydantic validation"
**User reads**: `/.claude/skills/pydantic/SKILL.md`

---

## Docstring Checklist

Before committing code, verify:

- [ ] Public APIs have docstrings
- [ ] Complex functions have docstrings
- [ ] Service classes have docstrings
- [ ] Docstrings are concise (summary + details)
- [ ] Cross-references point to `/docs/` for depth
- [ ] Args and Returns are documented
- [ ] No redundant docstrings (obvious getters/setters)
- [ ] IDE tooltips will be helpful

---

## Quick Reference

### Minimum Docstring (Simple Function)

```python
async def get_user_tasks(self, user_uid: UserUID) -> Result[list[Task]]:
    """Get all tasks for a user."""
```

### Standard Docstring (Public API)

```python
async def create_task(self, dto: TaskDTO, user_uid: UserUID) -> Result[Task]:
    """
    Create a new task for the user.

    Args:
        dto: Task data (validated)
        user_uid: Owner of the task

    Returns:
        Result[Task]: Created task or validation error
    """
```

### Detailed Docstring (Complex Logic)

```python
async def calculate_priority_score(
    self, task: Task, context: UserContext
) -> Result[float]:
    """
    Calculate dynamic priority score (0.0-1.0) based on multiple factors.

    Scoring algorithm:
    - Base priority: 0.3 (HIGH), 0.2 (MEDIUM), 0.1 (LOW)
    - Deadline urgency: +0.3 if due within 24h, +0.2 if within 48h
    - Learning alignment: +0.2 if task applies knowledge user has
    - Momentum: +0.2 if user completed similar tasks recently

    See: /docs/intelligence/TASK_PRIORITY_ALGORITHM.md

    Args:
        task: Task to score
        context: Rich user context with schedule/knowledge

    Returns:
        Result[float]: Priority score 0.0-1.0
    """
```

---

## Related Documentation

### Patterns
- [Error Handling](/docs/patterns/ERROR_HANDLING.md) - Result[T] pattern usage
- [Service Consolidation](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md) - Service architecture
- [Protocol Architecture](/docs/patterns/protocol_architecture.md) - Protocol-based design

### Skills
- [Python](/.claude/skills/python/SKILL.md) - Python patterns in SKUEL
- [Pydantic](/.claude/skills/pydantic/SKILL.md) - Validation models

---

**Last Updated**: 2026-01-29
**Status**: Current
