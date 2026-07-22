# Neo4j Cypher Query Examples

Comprehensive query examples for each SKUEL domain.

**Conventions used throughout** (see SKILL.md for the rules behind them):
- Ownership is the universal `(:User)-[:OWNS]->(:Entity)` edge — never `HAS_TASK`-style variants.
- Knowledge units are `:Ku` nodes (there is no `:Curriculum` Neo4j label — `Curriculum` is a Python model class).
- Status literals are `EntityStatus` values (`draft`, `scheduled`, `active`, `blocked`, `completed`, ...). In Python, always bind `$statuses` from the enum (SKUEL014); literals here are for readability.
- Temporal fields written by DTOs are ISO **strings** — coerce with `date()`/`datetime()` before comparing (SKILL.md § 8).

## Tasks Domain

### Get User's Active Tasks
```cypher
MATCH (u:User {uid: $user_uid})-[:OWNS]->(t:Task)
WHERE t.status IN ['draft', 'scheduled', 'active', 'blocked']
RETURN t
ORDER BY t.priority DESC, t.due_date ASC
```

### Get Overdue Tasks
```cypher
MATCH (u:User {uid: $user_uid})-[:OWNS]->(t:Task)
WHERE t.status IN ['draft', 'scheduled', 'active', 'blocked']
  AND t.due_date IS NOT NULL
  AND date(left(toString(t.due_date), 10)) < date()  -- prefix guard: tolerates a mis-stored datetime (#766)
RETURN t
ORDER BY t.due_date ASC
```

### Get Task with Full Context (MEGA-QUERY Pattern)
```cypher
MATCH (t:Task {uid: $uid})

// Get subtasks
OPTIONAL MATCH (t)-[:HAS_SUBTASK]->(subtask:Task)
WITH t, collect(DISTINCT {
    uid: subtask.uid,
    title: subtask.title,
    status: subtask.status
}) as subtasks

// Get dependencies
OPTIONAL MATCH (t)-[dep_rel:DEPENDS_ON]->(dependency:Task)
WHERE coalesce(dep_rel.confidence, 1.0) >= 0.7
WITH t, subtasks, collect(DISTINCT {
    uid: dependency.uid,
    title: dependency.title,
    confidence: dep_rel.confidence
}) as dependencies

// Get applied knowledge
OPTIONAL MATCH (t)-[app_rel:APPLIES_KNOWLEDGE]->(ku:Ku)
WHERE coalesce(app_rel.confidence, 1.0) >= 0.7
WITH t, subtasks, dependencies, collect(DISTINCT {
    uid: ku.uid,
    title: ku.title,
    confidence: app_rel.confidence
}) as applied_knowledge

// Get goal context
OPTIONAL MATCH (t)-[:FULFILLS_GOAL]->(goal:Goal)
RETURN t as task,
       {
           subtasks: subtasks,
           dependencies: dependencies,
           applied_knowledge: applied_knowledge,
           goal_context: CASE WHEN goal IS NOT NULL
               THEN {uid: goal.uid, title: goal.title, progress: goal.progress}
               ELSE null END
       } as graph_context
```

### Find Blocking Dependencies
```cypher
MATCH (t:Task {uid: $uid})
MATCH path = (t)-[:DEPENDS_ON*1..5]->(blocker:Task)
WHERE blocker.status NOT IN ['completed', 'cancelled']
RETURN DISTINCT blocker,
       length(path) as depth
ORDER BY depth ASC
```

## Goals Domain

### Get User's Active Goals with Progress
```cypher
MATCH (u:User {uid: $user_uid})-[:OWNS]->(g:Goal)
WHERE g.status IN ['active', 'scheduled']
RETURN g,
       coalesce(g.progress, 0.0) as progress
ORDER BY g.priority DESC
```

### Get Goal with Contributing Tasks
```cypher
MATCH (g:Goal {uid: $uid})
OPTIONAL MATCH (task:Task)-[:FULFILLS_GOAL]->(g)
WITH g, collect({
    uid: task.uid,
    title: task.title,
    status: task.status
}) as contributing_tasks
OPTIONAL MATCH (g)-[:HAS_SUBGOAL]->(subgoal:Goal)
WITH g, contributing_tasks, collect({
    uid: subgoal.uid,
    title: subgoal.title,
    progress: subgoal.progress
}) as subgoals
RETURN g as goal,
       contributing_tasks,
       subgoals
```

### Get Goal Achievement Path
```cypher
MATCH (g:Goal {uid: $uid})

// Required knowledge
OPTIONAL MATCH (g)-[req:REQUIRES_KNOWLEDGE]->(ku:Ku)
WITH g, collect({
    uid: ku.uid,
    title: ku.title
}) as required_knowledge

// Guiding principles
OPTIONAL MATCH (g)-[:GUIDED_BY_PRINCIPLE]->(p:Principle)
WITH g, required_knowledge, collect({
    uid: p.uid,
    title: p.title
}) as guiding_principles

// Supporting habits
OPTIONAL MATCH (h:Habit)-[:SUPPORTS_GOAL]->(g)
WITH g, required_knowledge, guiding_principles, collect({
    uid: h.uid,
    title: h.title,
    streak: h.current_streak
}) as supporting_habits

RETURN g as goal,
       required_knowledge,
       guiding_principles,
       supporting_habits
```

## Knowledge Domain (Ku)

### Get Knowledge Unit with Prerequisites
```cypher
MATCH (ku:Ku {uid: $uid})

// Direct prerequisites
OPTIONAL MATCH (ku)-[prereq:REQUIRES_KNOWLEDGE]->(p:Ku)
WHERE coalesce(prereq.confidence, 1.0) >= 0.7
WITH ku, collect(DISTINCT {
    uid: p.uid,
    title: p.title,
    confidence: prereq.confidence
}) as prerequisites

// What this enables
OPTIONAL MATCH (ku)-[:ENABLES_KNOWLEDGE]->(enabled:Ku)
WITH ku, prerequisites, collect(DISTINCT {
    uid: enabled.uid,
    title: enabled.title
}) as enables

// Related knowledge
OPTIONAL MATCH (ku)-[:RELATED_TO]-(related:Ku)
WITH ku, prerequisites, enables, collect(DISTINCT {
    uid: related.uid,
    title: related.title
}) as related

RETURN ku,
       prerequisites,
       enables,
       related
```

### Get User's Knowledge Mastery State
```cypher
MATCH (u:User {uid: $user_uid})-[r:MASTERED|IN_PROGRESS|VIEWED]->(ku:Ku)
RETURN ku.uid as uid,
       ku.title as title,
       type(r) as status,
       coalesce(r.mastery_score,
           CASE type(r)
               WHEN 'MASTERED' THEN 1.0
               WHEN 'IN_PROGRESS' THEN 0.5
               ELSE 0.1
           END
       ) as mastery_score,
       r.mastered_at as mastered_at
ORDER BY mastery_score DESC
```

### Find Ready-to-Learn Knowledge
```cypher
// Knowledge where all prerequisites are mastered
MATCH (u:User {uid: $user_uid})
MATCH (ku:Ku)
WHERE NOT (u)-[:MASTERED]->(ku)  // Not already mastered

// Check prerequisites
OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Ku)
WITH u, ku, collect(prereq) as prereqs

// All prerequisites must be mastered
WHERE ALL(p IN prereqs WHERE (u)-[:MASTERED]->(p))

RETURN ku
ORDER BY ku.title
LIMIT 10
```

### PathStep Composition (USES_KU)
```cypher
// The Kus a PathStep composes into learning content
MATCH (ps:PathStep {uid: $ps_uid})-[u:USES_KU]->(ku:Ku)
RETURN ku.uid as uid, ku.title as title
ORDER BY coalesce(u.order, 999)

// All PathSteps that teach a given Ku
MATCH (ps:PathStep)-[:USES_KU]->(ku:Ku {uid: $ku_uid})
RETURN ps.uid, ps.title
```

### MOC Organization (emergent hierarchy)
```cypher
// Children a MOC organizes, in order. MOC is not a label —
// it's any Entity with outgoing ORGANIZES edges.
MATCH (moc:Entity {uid: $uid})-[r:ORGANIZES]->(child:Entity)
RETURN child.uid, child.title, child.entity_type, r.order
ORDER BY r.order ASC
```

## Habits Domain

### Get Active Habits with Streaks
```cypher
MATCH (u:User {uid: $user_uid})-[:OWNS]->(h:Habit)
WHERE h.status = 'active'
RETURN h,
       coalesce(h.current_streak, 0) as streak,
       coalesce(h.completion_rate, 0.0) as completion_rate
ORDER BY h.current_streak DESC
```

### Get Habit with Goal Connections
```cypher
MATCH (h:Habit {uid: $uid})

// Linked goals
OPTIONAL MATCH (h)-[:SUPPORTS_GOAL|FULFILLS_GOAL]->(goal:Goal)
WITH h, collect({
    uid: goal.uid,
    title: goal.title,
    status: goal.status
}) as linked_goals

// Reinforced knowledge
OPTIONAL MATCH (h)-[:REINFORCES_KNOWLEDGE]->(ku:Ku)
WITH h, linked_goals, collect({
    uid: ku.uid,
    title: ku.title
}) as reinforced_knowledge

// Embodied principles
OPTIONAL MATCH (h)-[:EMBODIES_PRINCIPLE]->(p:Principle)
RETURN h as habit,
       linked_goals,
       reinforced_knowledge,
       collect({uid: p.uid, title: p.title}) as embodied_principles
```

## Principles Domain

### Get Principle with Full Embodiment
```cypher
MATCH (p:Principle {uid: $uid})

// Goals guided by this principle
OPTIONAL MATCH (p)-[:GUIDES_GOAL]->(goal:Goal)
WITH p, collect({
    uid: goal.uid,
    title: goal.title,
    status: goal.status
}) as guided_goals

// Choices aligned with this principle
OPTIONAL MATCH (choice:Choice)-[:ALIGNED_WITH_PRINCIPLE]->(p)
WITH p, guided_goals, collect({
    uid: choice.uid,
    title: choice.title
}) as aligned_choices

// Habits that embody this principle
OPTIONAL MATCH (habit:Habit)-[:EMBODIES_PRINCIPLE]->(p)
WITH p, guided_goals, aligned_choices, collect({
    uid: habit.uid,
    title: habit.title,
    streak: habit.current_streak
}) as embodying_habits

// Grounding knowledge
OPTIONAL MATCH (p)-[:GROUNDED_IN_KNOWLEDGE]->(ku:Ku)
RETURN p as principle,
       guided_goals,
       aligned_choices,
       embodying_habits,
       collect({uid: ku.uid, title: ku.title}) as grounding_knowledge
```

## Choices Domain

### Get Choice with Decision Context
```cypher
MATCH (c:Choice {uid: $uid})

// Guiding principles
OPTIONAL MATCH (c)-[:ALIGNED_WITH_PRINCIPLE]->(p:Principle)
WITH c, collect({uid: p.uid, title: p.title}) as guiding_principles

// Informing knowledge
OPTIONAL MATCH (c)-[:INFORMED_BY_KNOWLEDGE]->(ku:Ku)
WITH c, guiding_principles, collect({
    uid: ku.uid,
    title: ku.title
}) as informing_knowledge

// Affected goals
OPTIONAL MATCH (c)-[:AFFECTS_GOAL]->(goal:Goal)
WITH c, guiding_principles, informing_knowledge, collect({
    uid: goal.uid,
    title: goal.title
}) as affected_goals

// Implementing tasks
OPTIONAL MATCH (task:Task)-[:IMPLEMENTS_CHOICE]->(c)
RETURN c as choice,
       guiding_principles,
       informing_knowledge,
       affected_goals,
       collect({uid: task.uid, title: task.title}) as implementing_tasks
```

## Cross-Domain Patterns

### MEGA-QUERY: Complete User Context
```cypher
// This is a simplified version of SKUEL's MEGA-QUERY
// See /core/services/user/user_context_queries.py for full version

MATCH (user:User {uid: $user_uid})

// Tasks by status
OPTIONAL MATCH (user)-[:OWNS]->(task:Task)
WITH user,
     collect(CASE WHEN task.status IN ['draft', 'scheduled', 'active', 'blocked'] THEN task.uid END) as active_tasks,
     collect(CASE WHEN task.status = 'completed' THEN task.uid END) as completed_tasks,
     collect(CASE WHEN task.due_date IS NOT NULL
                   AND date(left(toString(task.due_date), 10)) < date()
                   AND task.status NOT IN ['completed', 'cancelled']
             THEN task.uid END) as overdue_tasks

// Goals by status
OPTIONAL MATCH (user)-[:OWNS]->(goal:Goal)
WITH user, active_tasks, completed_tasks, overdue_tasks,
     collect(CASE WHEN goal.status IN ['active', 'scheduled'] THEN goal.uid END) as active_goals,
     collect(CASE WHEN goal.status = 'completed' THEN goal.uid END) as completed_goals

// Active habits
OPTIONAL MATCH (user)-[:OWNS]->(habit:Habit)
WHERE habit.status = 'active'
WITH user, active_tasks, completed_tasks, overdue_tasks, active_goals, completed_goals,
     collect(habit.uid) as active_habits

// Knowledge mastery
OPTIONAL MATCH (user)-[m:MASTERED]->(ku:Ku)
WITH user, active_tasks, completed_tasks, overdue_tasks,
     active_goals, completed_goals, active_habits,
     collect({uid: ku.uid, score: m.mastery_score}) as mastered_knowledge

RETURN user,
       {
           tasks: {active: active_tasks, completed: completed_tasks, overdue: overdue_tasks},
           goals: {active: active_goals, completed: completed_goals},
           habits: {active: active_habits},
           knowledge: {mastered: mastered_knowledge}
       } as context
```

### Find Cross-Domain Synergies
```cypher
// Find where knowledge, goals, and habits align
MATCH (u:User {uid: $user_uid})

// Knowledge user is learning
MATCH (u)-[:IN_PROGRESS|MASTERED]->(ku:Ku)

// Goals that require this knowledge
OPTIONAL MATCH (goal:Goal)-[:REQUIRES_KNOWLEDGE]->(ku)
WHERE (u)-[:OWNS]->(goal)

// Habits that reinforce this knowledge
OPTIONAL MATCH (habit:Habit)-[:REINFORCES_KNOWLEDGE]->(ku)
WHERE (u)-[:OWNS]->(habit)

// Tasks that apply this knowledge
OPTIONAL MATCH (task:Task)-[:APPLIES_KNOWLEDGE]->(ku)
WHERE (u)-[:OWNS]->(task) AND task.status IN ['draft', 'scheduled', 'active', 'blocked']

WITH ku,
     collect(DISTINCT goal) as goals,
     collect(DISTINCT habit) as habits,
     collect(DISTINCT task) as tasks
WHERE size(goals) > 0 OR size(habits) > 0 OR size(tasks) > 0

RETURN ku.uid as knowledge,
       ku.title as title,
       [g IN goals | g.title] as aligned_goals,
       [h IN habits | h.title] as reinforcing_habits,
       [t IN tasks | t.title] as applying_tasks
```

### Graph-Aware Search
```cypher
// Search with relationship context
MATCH (t:Task)
WHERE t.title CONTAINS $query OR t.description CONTAINS $query

// Ownership check
MATCH (u:User {uid: $user_uid})-[:OWNS]->(t)

// Get graph context
OPTIONAL MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Ku)
OPTIONAL MATCH (t)-[:FULFILLS_GOAL]->(g:Goal)

WITH t,
     collect(DISTINCT ku.uid) as knowledge_uids,
     collect(DISTINCT g.uid) as goal_uids

RETURN t,
       knowledge_uids,
       goal_uids,
       size(knowledge_uids) + size(goal_uids) as connection_count
ORDER BY connection_count DESC
```

## Performance Patterns

### Batch Node Creation
```cypher
// Create multiple nodes in one query
UNWIND $nodes as node
MERGE (n:Task {uid: node.uid})
SET n += node.properties,
    n.updated_at = datetime()
RETURN count(n) as created
```

### Batch Relationship Creation
```cypher
// Create multiple relationships in one query.
// Label guard is mandatory — an unlabeled MATCH by uid also binds the
// entity's :Content shadow node (G13 rule, SKILL.md § 0).
UNWIND $edges as edge
MATCH (a:Entity {uid: edge.from_uid})
MATCH (b:Entity {uid: edge.to_uid})
MERGE (a)-[r:REQUIRES_KNOWLEDGE]->(b)
SET r.confidence = edge.confidence,
    r.created_at = coalesce(r.created_at, datetime())
RETURN count(r) as created
```

### Count Without Loading Entities
```cypher
// Efficient counting
MATCH (u:User {uid: $user_uid})-[:OWNS]->(t:Task)
WHERE t.status = 'completed'
RETURN count(t) as completed_count
```

### Pagination with Ordering
```cypher
MATCH (u:User {uid: $user_uid})-[:OWNS]->(t:Task)
WHERE t.status IN ['draft', 'scheduled', 'active', 'blocked']
RETURN t
ORDER BY t.priority DESC, t.due_date ASC
SKIP $offset
LIMIT $limit
```
