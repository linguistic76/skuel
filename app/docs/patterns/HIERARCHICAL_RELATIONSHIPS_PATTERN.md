---
title: Hierarchical Relationships Pattern
updated: '2026-02-02'
category: patterns
related_skills:
- neo4j-cypher-patterns
related_docs: []
---
# Hierarchical Relationships Pattern

**Date:** 2026-01-30
**Status:** Active
**Applies To:** Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles)

## Core Principle: "Flat Identity, Rich Structure"

Activity domains use **flat UIDs** for identity and **graph relationships** for hierarchy. This gives maximum flexibility while maintaining clear structure.

## Design Philosophy

### The Insight: Hierarchy IS a Relationship

```
Storage:
  task_abc123 (flat UID - identity)
  task_xyz789 (flat UID - identity)
  (task_abc123)-[:HAS_SUBTASK]->(task_xyz789)  (relationship - structure)

Display:
  "Implement Auth Feature"
    └─ "Setup JWT Library"  (visual hierarchy)
```

### Why Flat UIDs + Graph Relationships?

| Benefit | Explanation | Example |
|---------|-------------|---------|
| **Flexibility** | Same entity can belong to multiple hierarchies | Subtask shared by multiple parents |
| **Stability** | Relationships change without changing identity | Move subtask to new parent without breaking references |
| **Metadata** | Relationships carry progress weights, ordering | `{progress_weight: 0.5, order: 1}` |
| **Graph-Native** | Leverages Neo4j's relationship properties and traversal | Cypher queries naturally express hierarchy |
| **DAG Support** | Directed Acyclic Graph (not just tree) | Multiple parents allowed |

### Why NOT Hierarchical UIDs?

**Hierarchical UIDs (dot notation) are reserved for curriculum only:**

```python
# BAD: Hierarchical UID for Activity domain
task.project.phase1.subtask  # Too rigid!

# Problems:
# 1. Can't have multiple parents (tree only, not DAG)
# 2. Moving subtask requires UID change (breaks references)
# 3. No metadata on relationship (no progress weighting)
# 4. Harder to query siblings, cousins, etc.

# GOOD: Flat UID + Relationship
task_subtask  # Identity stable
(task_project)-[:HAS_SUBTASK {weight: 0.5}]->(task_subtask)  # Structure flexible
```

## Parent-Child vs Prerequisites

Two orthogonal relationship types:

| Relationship Type | Meaning | Completion Rule | Use Case |
|-------------------|---------|-----------------|----------|
| **Parent-Child** (`HAS_SUBTASK`) | "Composed of" (decomposition) | All children done → parent done | Breaking big task into smaller pieces |
| **Prerequisite** (`REQUIRES_TASK`) | "Must happen before" (sequencing) | Can't start until prerequisite done | Enforcing order within subtasks |

**Both can coexist!**

```cypher
// Task with subtasks (decomposition)
(plan_project:Task {uid: 'task_abc123'})
(plan_project)-[:HAS_SUBTASK]->(research:Task {uid: 'task_xyz789'})
(plan_project)-[:HAS_SUBTASK]->(timeline:Task {uid: 'task_def456'})
(plan_project)-[:HAS_SUBTASK]->(budget:Task {uid: 'task_ghi789'})

// Subtasks with prerequisites (sequencing)
(timeline)-[:REQUIRES_TASK]->(research)  // Can't timeline until research done
(budget)-[:REQUIRES_TASK]->(timeline)    // Can't budget until timeline done

// Result:
// - Must do research → timeline → budget (sequential)
// - When all three done, plan_project auto-completes (composition)
```

## User Workflow: "Pen and Paper" Flexibility

### Typical Flow

```
1. User identifies high-level activity
   "Implement Authentication Feature" → task_abc123

2. User decomposes into subtasks
   "Setup JWT library" → task_xyz789 (parent: task_abc123)
   "Create login endpoint" → task_def456 (parent: task_abc123)
   "Add auth middleware" → task_ghi789 (parent: task_abc123)

3. User adds prerequisites (if needed)
   task_def456 REQUIRES task_xyz789  // Need JWT before endpoint
   task_ghi789 REQUIRES task_def456   // Need endpoint before middleware

4. User completes bottom-up
   Complete task_xyz789 ✓
   Complete task_def456 ✓
   Complete task_ghi789 ✓
   → task_abc123 auto-completes ✓

5. User can restructure without breaking
   Move subtask to different parent: just update relationship
   Add subtask to multiple parents: create multiple HAS_SUBTASK edges
   Reorder prerequisites: update REQUIRES_TASK relationships
```

## Relationship Types

### Parent-Child Composition

| Relationship | Direction | Meaning | Properties |
|--------------|-----------|---------|-----------|
| `HAS_SUBTASK` | Parent → Child | "Composed of" | `progress_weight`, `order`, `created_at` |
| `SUBTASK_OF` | Child → Parent | "Part of" | `created_at` |
| `HAS_SUBGOAL` | Parent → Child | "Milestone of" | `progress_weight`, `order`, `created_at` |
| `SUBGOAL_OF` | Child → Parent | "Contributes to" | `created_at` |

**Note:** Both directions exist for efficient bidirectional queries.

### Progress Weighting

Subtasks/subgoals can have different weights:

```python
# Parent goal: "Career Growth 2026"
(parent)-[:HAS_SUBGOAL {progress_weight: 0.40}]->(q1_goal)  # Foundation (40%)
(parent)-[:HAS_SUBGOAL {progress_weight: 0.30}]->(q2_goal)  # Projects (30%)
(parent)-[:HAS_SUBGOAL {progress_weight: 0.20}]->(q3_goal)  # Certification (20%)
(parent)-[:HAS_SUBGOAL {progress_weight: 0.10}]->(q4_goal)  # Interview prep (10%)

# Parent progress calculation:
parent.progress = sum(child.progress * edge.progress_weight)
                = (q1.progress * 0.40) + (q2.progress * 0.30) + ...
```

### Prerequisites (Orthogonal)

```python
# Sequential dependencies (separate from parent-child)
REQUIRES_TASK   # Task → Task (must complete before)
ENABLES_TASK    # Task → Task (unlocks when done)
REQUIRES_GOAL   # Goal → Goal
ENABLES_GOAL    # Goal → Goal
```

## Implementation Patterns

### Creating Subtasks

```python
# Create parent task (flat UID)
parent = await tasks_service.create_task(
    TaskRequest(title="Implement Auth Feature"),
    user_uid="user_mike"
)
# Result: task_abc123

# Create subtasks with parent reference
subtask1 = await tasks_service.create_task(
    TaskRequest(
        title="Setup JWT Library",
        parent_task_uid=parent.uid,      # Link to parent
        progress_weight=0.30              # Contributes 30% to parent
    ),
    user_uid="user_mike"
)
# Result: task_xyz789
# Relationship: (task_abc123)-[:HAS_SUBTASK {progress_weight: 0.30}]->(task_xyz789)

subtask2 = await tasks_service.create_task(
    TaskRequest(
        title="Create Login Endpoint",
        parent_task_uid=parent.uid,
        progress_weight=0.50              # Contributes 50%
    ),
    user_uid="user_mike"
)

subtask3 = await tasks_service.create_task(
    TaskRequest(
        title="Add Auth Middleware",
        parent_task_uid=parent.uid,
        progress_weight=0.20              # Contributes 20%
    ),
    user_uid="user_mike"
)
```

### Querying Hierarchy

```python
# Get all subtasks (direct children)
subtasks = await tasks_service.get_subtasks(parent.uid)
# Returns: [task_xyz789, task_def456, task_ghi789]

# Get full hierarchy (any depth)
hierarchy = await tasks_service.get_task_hierarchy(task.uid)
# Returns: {
#   "ancestors": [root, parent, grandparent],
#   "current": task,
#   "siblings": [sibling1, sibling2],
#   "children": [child1, child2],
#   "depth": 3
# }

# Get parent (if any)
parent = await tasks_service.get_parent_task(subtask.uid)
# Returns: task_abc123 or None
```

### Completion Propagation

```python
# Complete subtask
await tasks_service.complete_task(subtask1.uid)

# System checks: Are all siblings complete?
# If yes → auto-complete parent
# If parent completes → check grandparent recursively

# Example with 3 subtasks:
await complete_task(task_xyz789)  # 1/3 complete
await complete_task(task_def456)  # 2/3 complete
await complete_task(task_ghi789)  # 3/3 complete → task_abc123 auto-completes!
```

## Query Patterns (Cypher)

### Get Direct Children

```cypher
MATCH (parent:Task {uid: $parent_uid})
MATCH (parent)-[:HAS_SUBTASK]->(child:Task)
RETURN child
ORDER BY child.created_at
```

### Get All Descendants (Any Depth)

```cypher
MATCH (parent:Task {uid: $parent_uid})
MATCH (parent)-[:HAS_SUBTASK*]->(descendant:Task)
RETURN descendant
```

### Get Ancestor Path

```cypher
MATCH path = (root:Task)-[:HAS_SUBTASK*]->(current:Task {uid: $task_uid})
WHERE NOT (root)-[:SUBTASK_OF]->()  // Root has no parent
RETURN nodes(path) as ancestors
```

### Check Completion Status

```cypher
MATCH (parent:Task {uid: $parent_uid})
MATCH (parent)-[:HAS_SUBTASK]->(child:Task)
WITH parent,
     count(child) as total_children,
     count(CASE WHEN child.status = 'completed' THEN 1 END) as completed_children,
     sum(
       CASE WHEN child.status = 'completed'
       THEN [(parent)-[r:HAS_SUBTASK]->(child) | r.progress_weight][0]
       ELSE 0
       END
     ) as weighted_progress
RETURN
  parent.uid,
  total_children,
  completed_children,
  (total_children = completed_children) as all_complete,
  weighted_progress
```

### Get Siblings

```cypher
MATCH (current:Task {uid: $task_uid})
MATCH (parent:Task)-[:HAS_SUBTASK]->(current)
MATCH (parent)-[:HAS_SUBTASK]->(sibling:Task)
WHERE sibling.uid <> $task_uid
RETURN sibling
```

## Visual Display Patterns

### Hierarchical Tree View

```
Storage (flat UIDs + relationships):
  task_abc123 -[:HAS_SUBTASK]-> task_xyz789
  task_abc123 -[:HAS_SUBTASK]-> task_def456
  task_abc123 -[:HAS_SUBTASK]-> task_ghi789

Display (generated tree):
  └─ Implement Auth Feature (task_abc123) [Progress: 66%]
     ├─ ✓ Setup JWT Library (task_xyz789) [30% weight]
     ├─ ✓ Create Login Endpoint (task_def456) [50% weight]
     └─ Add Auth Middleware (task_ghi789) [20% weight]
```

### Breadcrumb Navigation

```python
def generate_breadcrumb(task: Task, ancestors: list[Task]) -> str:
    """
    Generate visual hierarchical path (not stored, computed).

    Storage: flat UIDs with relationships
    Display: hierarchical path
    """
    titles = [ancestor.title for ancestor in ancestors] + [task.title]
    return " → ".join(titles)

# Example:
# "Projects → Q1 Goals → Learn Python → Complete Tutorial"
```

### Indented List (UI)

```python
def render_task_tree(task: Task, depth: int = 0) -> str:
    """Render task with indentation showing hierarchy."""
    indent = "  " * depth
    icon = "✓" if task.status == "completed" else "○"

    output = f"{indent}{icon} {task.title} ({task.uid})\n"

    # Recursively render children
    for subtask in task.get_subtasks():
        output += render_task_tree(subtask, depth + 1)

    return output

# Example output:
# ○ Implement Auth Feature (task_abc123)
#   ✓ Setup JWT Library (task_xyz789)
#   ✓ Create Login Endpoint (task_def456)
#   ○ Add Auth Middleware (task_ghi789)
```

## Edge Cases & Rules

### Multiple Parents (DAG)

**Allowed:** A subtask can have multiple parents.

```cypher
// Subtask shared by two parents
(project_a)-[:HAS_SUBTASK]->(shared_research)
(project_b)-[:HAS_SUBTASK]->(shared_research)

// When shared_research completes:
// - Check project_a (might auto-complete)
// - Check project_b (might auto-complete)
```

### Cycles (Prevented)

**Rule:** Cannot create cycles (would cause infinite completion loops).

```python
# Validation before creating relationship
async def validate_no_cycle(parent_uid: str, child_uid: str) -> bool:
    """Ensure adding this relationship won't create a cycle."""
    query = """
    MATCH (child:Task {uid: $child_uid})
    MATCH path = (child)-[:HAS_SUBTASK*]->(parent:Task {uid: $parent_uid})
    RETURN count(path) > 0 as would_create_cycle
    """
    # If path exists from child to parent, adding parent->child creates cycle
    # Return False if cycle detected
```

### Orphan Prevention

**Rule:** Deleting a parent doesn't delete children (they become root-level).

```cypher
// Delete parent but preserve children
MATCH (parent:Task {uid: $parent_uid})
MATCH (parent)-[r:HAS_SUBTASK]->(child)
DELETE r  // Delete relationship only
DELETE parent

// Children remain as independent tasks
// (Could optionally promote them or require user decision)
```

### Progress Weighting Rules

1. **Weights can be any positive number** (don't need to sum to 1.0)
2. **Default weight:** 1.0 (equal contribution)
3. **Completion calculation:**
   ```python
   # Weighted completion percentage
   total_weight = sum(edge.progress_weight for all children)
   completed_weight = sum(edge.progress_weight for completed children)
   parent.progress = completed_weight / total_weight

   # Binary completion (for auto-complete)
   all_complete = (completed_count == total_count)
   ```

## Benefits Over Hierarchical UIDs

| Feature | Flat UID + Relationships | Hierarchical UID |
|---------|-------------------------|------------------|
| Multiple parents | ✅ Yes (DAG) | ❌ No (tree only) |
| Move subtask | ✅ Update relationship | ❌ Change UID (breaks refs) |
| Relationship metadata | ✅ Progress weight, order | ❌ No metadata |
| Flexible restructuring | ✅ Easy | ❌ Requires UID changes |
| Sibling queries | ✅ Natural graph traversal | ❌ String parsing |
| Progress tracking | ✅ Weighted sums | ❌ Manual calculation |

## Related Patterns

- **Prerequisites Pattern:** `/docs/patterns/PREREQUISITES_PATTERN.md` (sequencing, not decomposition)
- **UID Convention:** `/docs/migrations/UID_STANDARDIZATION_MIGRATION_2026-01-30.md` (why flat UIDs)
- **BaseService Mixins:** `/docs/reference/BASESERVICE_METHOD_INDEX.md` (hierarchy methods)

## Implementation Checklist

- [x] Add relationship types to `RelationshipName` enum
- [x] Add `parent_task_uid` to `TaskRequest` / `GoalRequest`
- [x] Implement `get_subtasks()` method
- [x] Implement `get_parent_task()` method
- [x] Implement `get_task_hierarchy()` method
- [x] Implement completion propagation
- [x] Add cycle detection validation
- [x] Add UI components for hierarchy display
- [ ] Add tests for hierarchy operations
- [ ] Add UI for creating subtasks
- [ ] Add UI for visualizing hierarchy

## Examples

### Example 1: Project with Sequential Subtasks

```python
# User creates project
project = create_task("Launch Product")

# Decompose into phases
research = create_task("Market Research", parent=project, weight=0.20)
build = create_task("Build MVP", parent=project, weight=0.40)
test = create_task("User Testing", parent=project, weight=0.20)
launch = create_task("Go Live", parent=project, weight=0.20)

# Add sequential prerequisites
add_prerequisite(build, requires=research)
add_prerequisite(test, requires=build)
add_prerequisite(launch, requires=test)

# Result:
# - Must complete in order: research → build → test → launch
# - Progress: project.progress = sum of weighted completions
# - When all 4 done → project auto-completes
```

### Example 2: Goal with Parallel Subgoals

```python
# Annual goal
year_goal = create_goal("Career Growth 2026")

# Quarterly milestones (parallel, not sequential)
q1 = create_goal("Q1: Foundation", parent=year_goal, weight=0.25)
q2 = create_goal("Q2: Projects", parent=year_goal, weight=0.25)
q3 = create_goal("Q3: Certification", parent=year_goal, weight=0.25)
q4 = create_goal("Q4: Job Search", parent=year_goal, weight=0.25)

# No prerequisites - can work on all in parallel
# Progress tracked independently
# When all 4 complete → year_goal completes
```

### Example 3: Shared Subtask

```python
# Two projects need same research
project_a = create_task("Project A")
project_b = create_task("Project B")

# Shared research task
research = create_task("Technology Research")

# Link to both parents
add_subtask_relationship(project_a, research, weight=0.30)
add_subtask_relationship(project_b, research, weight=0.50)

# When research completes:
# - project_a progress += 30%
# - project_b progress += 50%
# - Both might auto-complete if all other subtasks done
```

## Future Extensions

### Automatic Decomposition (AI-Assisted)

```python
# User creates high-level task
task = create_task("Implement Authentication")

# AI suggests decomposition
suggestions = await ai_service.suggest_subtasks(task)
# Returns: ["Setup JWT", "Create login endpoint", "Add middleware", ...]

# User approves and creates subtasks automatically
for suggestion in suggestions:
    create_task(suggestion.title, parent=task, weight=suggestion.weight)
```

### Templates

```python
# Save hierarchy as template
template = save_as_template(project_task)

# Instantiate template for new project
new_project = instantiate_template(template, title="New Project")
# Creates parent + all subtasks + relationships
```

### Dependency Visualization

```
Graph view showing:
- Parent-child relationships (vertical)
- Prerequisite relationships (horizontal arrows)
- Completion status (colors)
- Progress bars
```

---

**Status:** Ready for implementation
**Next Steps:** Implement relationship methods in core services
