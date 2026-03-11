---
title: SKUEL Query Design - Pure Cypher Patterns for Curriculum Navigation
updated: 2025-11-27
status: current
category: general
tags: [design, query, skuel]
related: []
---

# SKUEL Query Design - Pure Cypher Patterns for Curriculum Navigation

**Core Principle:** "UserContext-driven queries that navigate the curriculum graph efficiently"

This document defines SKUEL-specific Pure Cypher query patterns optimized for the curriculum architecture (LearningPaths → KnowledgeUnits → Supporting Domains) and UserContext personalization.

---

## Table of Contents

1. [Curriculum Architecture Overview](#curriculum-architecture-overview)
2. [UserContext Integration](#usercontext-integration)
3. [Pure Cypher Query Patterns](#pure-cypher-query-patterns)
4. [Performance Considerations](#performance-considerations)
5. [APOC Metadata Enhancements](#apoc-metadata-enhancements)

---

## Curriculum Architecture Overview

### The Three Core Entities

SKUEL's curriculum is built on three interconnected entity types:

```
LearningPath (lp)
    ↓ PART_OF
KnowledgeUnit (ku)
    ↓ LINKS_TO
Supporting Domains (Tasks, Habits, Goals, Events, Journals, etc.)
```

**Key Characteristics:**

1. **LearningPath** - Sequences of knowledge organized by section
   - Sections: `foundation`, `practice`, `integration`
   - Streams: `yoga_and_feeling`, `human_practice`, `relationships_and_community`

2. **KnowledgeUnit** - Atomic units of knowledge with relationships
   - Relationships: `REQUIRES_KNOWLEDGE`, `ENABLES_KNOWLEDGE`, `PART_OF`, `RELATED_TO`
   - Categorized by Domain (TECH, PERSONAL, HEALTH, etc.)

3. **Supporting Domains** - Real-world application entities
   - Tasks, Habits, Goals, Events, Journals, Principles, Choices

### The Life Path Philosophy

**"Everything flows toward the life path"**

- Each user has ONE ultimate learning path (`life_path_uid`)
- All other learning paths are prerequisites or components
- Knowledge substance = real-world application across supporting domains
- Life alignment score = average substance across life path knowledge

---

## UserContext Integration

### UserContext as Primary Query Driver

Every SKUEL query should consider the UserContext to provide personalized, relevant results:

**Key Context Fields for Queries:**

| Field | Query Impact |
|-------|--------------|
| `knowledge_mastery` | Filter by mastery level |
| `prerequisites_completed` | Determine ready-to-learn knowledge |
| `current_learning_path_uid` | Prioritize current path knowledge |
| `life_path_uid` | Ultimate alignment target |
| `learning_level` | Adjust content difficulty |
| `available_minutes_daily` | Filter by estimated time |
| `domain_progress` | Balance cross-domain learning |
| `active_task_uids` / `active_habit_uids` | Show applied knowledge |

**UserContext Query Pattern:**

```cypher
// Step 1: User context awareness
MATCH (user:User {uid: $user_uid})

// Step 2: Get user's current state
WITH user,
     $current_path AS current_path,
     $mastered_knowledge AS mastered,
     $available_minutes AS time_budget

// Step 3: Query curriculum with context filters
MATCH (lp:Lp)-[:CONTAINS]->(ku:Curriculum)
WHERE
  // Context-driven filtering
  lp.uid = current_path
  AND ku.uid NOT IN mastered
  AND ku.estimated_minutes <= time_budget

// Step 4: Return personalized results
RETURN ku
ORDER BY ku.sequence_order
```

---

## Pure Cypher Query Patterns

### Pattern 1: Learning Path Navigation

**Use Case:** Get next knowledge units in user's current learning path

```cypher
// Get next knowledge units for user's current learning path
MATCH (user:User {uid: $user_uid})-[:ENROLLED_IN]->(lp:Lp)
WHERE lp.uid = $current_path_uid

// Get all knowledge units in this path
MATCH (lp)-[:CONTAINS]->(ku:Curriculum)

// Filter by prerequisites
OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Curriculum)
WITH ku, lp,
     collect(prereq.uid) AS prereq_uids,
     $mastered_knowledge_uids AS mastered

// Only show KUs where all prerequisites are mastered
WHERE
  size(prereq_uids) = 0  // No prerequisites
  OR all(p IN prereq_uids WHERE p IN mastered)  // All prereqs met

// Exclude already mastered knowledge
AND ku.uid NOT IN mastered

// Sort by section and sequence
RETURN
  ku.uid AS knowledge_uid,
  ku.title AS title,
  ku.section AS section,
  ku.estimated_minutes AS time_required,
  lp.title AS path_title,
  prereq_uids AS prerequisites

ORDER BY
  CASE ku.section
    WHEN 'foundation' THEN 1
    WHEN 'practice' THEN 2
    WHEN 'integration' THEN 3
  END,
  ku.sequence_order
LIMIT $limit
```

### Pattern 2: Life Path Alignment Query

**Use Case:** Calculate life alignment by checking knowledge substance across life path

```cypher
// Get user's life path knowledge with substance scores
MATCH (user:User {uid: $user_uid})-[:ULTIMATE_PATH]->(life_path:Lp)

// Get all knowledge in life path
MATCH (life_path)-[:CONTAINS]->(ku:Curriculum)

// Get substance score (real-world application)
OPTIONAL MATCH (user)-[r:APPLIED]->(ku)

// Calculate substance from supporting domain connections
OPTIONAL MATCH (ku)<-[:APPLIES_KNOWLEDGE]-(task:Task {user_uid: $user_uid})
OPTIONAL MATCH (ku)<-[:APPLIES_KNOWLEDGE]-(habit:Habit {user_uid: $user_uid})
OPTIONAL MATCH (ku)<-[:APPLIES_KNOWLEDGE]-(goal:Goal {user_uid: $user_uid})
OPTIONAL MATCH (ku)<-[:APPLIES_KNOWLEDGE]-(journal:Journal {user_uid: $user_uid})

WITH ku, life_path,
     coalesce(r.substance_score, 0.0) AS recorded_substance,
     count(DISTINCT task) AS task_applications,
     count(DISTINCT habit) AS habit_applications,
     count(DISTINCT goal) AS goal_applications,
     count(DISTINCT journal) AS journal_applications

// Calculate substance score (0.0-1.0)
WITH ku, life_path,
     CASE
       WHEN recorded_substance > 0 THEN recorded_substance
       ELSE
         // Substance from application counts (weighted)
         (task_applications * 0.05 +
          habit_applications * 0.10 +
          goal_applications * 0.07 +
          journal_applications * 0.07)
     END AS substance_score

// Aggregate life alignment
WITH life_path,
     collect({
       uid: ku.uid,
       title: ku.title,
       substance: substance_score
     }) AS knowledge_items,
     avg(substance_score) AS life_alignment_score

RETURN
  life_path.uid AS life_path_uid,
  life_path.title AS life_path_title,
  life_alignment_score,
  knowledge_items,
  size(knowledge_items) AS total_knowledge,
  size([item IN knowledge_items WHERE item.substance >= 0.7]) AS well_practiced,
  size([item IN knowledge_items WHERE item.substance < 0.3]) AS theoretical_only

// Interpretation:
// 0.0-0.2: Pure theory (read about it)
// 0.3-0.5: Applied knowledge (tried it)
// 0.6-0.7: Well-practiced (regular use)
// 0.8-1.0: Lifestyle-integrated (embodied)
```

### Pattern 3: Prerequisite Chain Traversal

**Use Case:** Find all prerequisites (recursive) for a target knowledge unit

```cypher
// Find complete prerequisite chain for target knowledge
MATCH path = (target:Curriculum {uid: $target_uid})-[:REQUIRES_KNOWLEDGE*0..5]->(prereq:Curriculum)

// Get user's mastery state
MATCH (user:User {uid: $user_uid})
OPTIONAL MATCH (user)-[r:MASTERED]->(prereq)

WITH prereq, target, path,
     exists((user)-[:MASTERED]->(prereq)) AS is_mastered,
     length(path) AS depth

// Calculate readiness (all prerequisites at depth-1 are mastered)
WITH prereq, target, depth, is_mastered,
     CASE
       WHEN depth = 0 THEN true  // Target node itself
       WHEN depth = 1 THEN is_mastered  // Direct prereq
       ELSE is_mastered  // Transitive prereq
     END AS is_ready

RETURN
  prereq.uid AS knowledge_uid,
  prereq.title AS title,
  depth AS prerequisite_depth,
  is_mastered,
  is_ready,
  CASE
    WHEN depth = 0 THEN 'TARGET'
    WHEN depth = 1 THEN 'DIRECT_PREREQUISITE'
    ELSE 'TRANSITIVE_PREREQUISITE'
  END AS prerequisite_type

ORDER BY depth, prereq.sequence_order
```

### Pattern 4: Cross-Domain Knowledge Application

**Use Case:** Show how knowledge is applied across supporting domains

```cypher
// Find all applications of specific knowledge across domains
MATCH (ku:Curriculum {uid: $knowledge_uid})

// Tasks applying this knowledge
OPTIONAL MATCH (ku)<-[:APPLIES_KNOWLEDGE]-(task:Task {user_uid: $user_uid})
WHERE task.status IN ['active', 'in_progress']

// Habits applying this knowledge
OPTIONAL MATCH (ku)<-[:APPLIES_KNOWLEDGE]-(habit:Habit {user_uid: $user_uid})
WHERE habit.is_active = true

// Goals enabled by this knowledge
OPTIONAL MATCH (ku)-[:ENABLES_GOAL]->(goal:Goal {user_uid: $user_uid})
WHERE goal.status <> 'completed'

// Events practicing this knowledge
OPTIONAL MATCH (ku)<-[:PRACTICES]-(event:Event {user_uid: $user_uid})
WHERE event.event_date >= date()

// Journal reflections on this knowledge
OPTIONAL MATCH (ku)<-[:REFLECTS_ON]-(journal:Journal {user_uid: $user_uid})
WHERE journal.created_at >= datetime() - duration({days: 30})

// Principles aligned with this knowledge
OPTIONAL MATCH (ku)-[:ALIGNS_WITH]->(principle:Principle {user_uid: $user_uid})

RETURN
  ku.uid AS knowledge_uid,
  ku.title AS knowledge_title,
  collect(DISTINCT {type: 'task', uid: task.uid, title: task.title}) AS tasks,
  collect(DISTINCT {type: 'habit', uid: habit.uid, title: habit.title}) AS habits,
  collect(DISTINCT {type: 'goal', uid: goal.uid, title: goal.title}) AS goals,
  collect(DISTINCT {type: 'event', uid: event.uid, title: event.title}) AS events,
  collect(DISTINCT {type: 'journal', uid: journal.uid, title: journal.title}) AS journals,
  collect(DISTINCT {type: 'principle', uid: principle.uid, title: principle.title}) AS principles,

  // Calculate substance indicators
  count(DISTINCT task) AS task_count,
  count(DISTINCT habit) AS habit_count,
  count(DISTINCT goal) AS goal_count,
  count(DISTINCT event) AS event_count,
  count(DISTINCT journal) AS journal_count,

  // Substance score (weighted by domain importance)
  (count(DISTINCT habit) * 0.10 +
   count(DISTINCT journal) * 0.07 +
   count(DISTINCT event) * 0.05 +
   count(DISTINCT task) * 0.05) AS estimated_substance_score
```

### Pattern 5: Bulk Learning Path Ingestion

**Use Case:** Import learning paths and knowledge units from YAML/markdown files

```cypher
// Phase 1: Create LearningPaths with sections
UNWIND $learning_paths AS lp_data

MERGE (lp:Lp {uid: lp_data.uid})
SET
  lp.title = lp_data.title,
  lp.section = lp_data.section,
  lp.stream = lp_data.stream,
  lp.description = lp_data.description,
  lp.estimated_hours = lp_data.estimated_hours,
  lp.updated_at = datetime()

WITH lp, lp_data

// Phase 2: Create KnowledgeUnits
UNWIND lp_data.knowledge_units AS ku_data

MERGE (ku:Curriculum {uid: ku_data.uid})
SET
  ku.title = ku_data.title,
  ku.content = ku_data.content,
  ku.section = ku_data.section,
  ku.sequence_order = ku_data.sequence_order,
  ku.estimated_minutes = ku_data.estimated_minutes,
  ku.difficulty = ku_data.difficulty,
  ku.domain = ku_data.domain,
  ku.updated_at = datetime()

// Phase 3: Wire KU to LearningPath
MERGE (ku)-[:PART_OF]->(lp)

WITH ku, ku_data

// Phase 4: Create prerequisite relationships
FOREACH (prereq_uid IN coalesce(ku_data.prerequisites, []) |
  MERGE (prereq:Curriculum {uid: prereq_uid})
  MERGE (ku)-[:REQUIRES_KNOWLEDGE]->(prereq)
)

// Phase 5: Create enables relationships
FOREACH (enabled_uid IN coalesce(ku_data.enables, []) |
  MERGE (enabled:Curriculum {uid: enabled_uid})
  MERGE (ku)-[:ENABLES_KNOWLEDGE]->(enabled)
)

RETURN
  count(DISTINCT lp) AS learning_paths_created,
  count(DISTINCT ku) AS knowledge_units_created
```

### Pattern 6: User Progress Snapshot

**Use Case:** Get complete snapshot of user's learning progress

```cypher
// Get comprehensive user progress across all learning paths
MATCH (user:User {uid: $user_uid})

// Get all enrolled learning paths
OPTIONAL MATCH (user)-[:ENROLLED_IN]->(lp:Lp)
OPTIONAL MATCH (lp)-[:CONTAINS]->(ku:Curriculum)

// Get mastery state
OPTIONAL MATCH (user)-[m:MASTERED]->(mastered_ku:Curriculum)

// Calculate progress per path
WITH user, lp,
     count(DISTINCT ku) AS total_knowledge,
     count(DISTINCT mastered_ku) AS mastered_knowledge

WITH user, lp,
     total_knowledge,
     mastered_knowledge,
     CASE
       WHEN total_knowledge > 0 THEN toFloat(mastered_knowledge) / total_knowledge
       ELSE 0.0
     END AS path_progress

// Get life path
OPTIONAL MATCH (user)-[:ULTIMATE_PATH]->(life_path:Lp)

RETURN
  user.uid AS user_uid,
  user.username AS username,

  // Learning paths progress
  collect({
    uid: lp.uid,
    title: lp.title,
    section: lp.section,
    total_knowledge: total_knowledge,
    mastered: mastered_knowledge,
    progress: path_progress,
    is_life_path: lp.uid = life_path.uid
  }) AS learning_paths,

  // Overall stats
  sum(total_knowledge) AS total_knowledge_available,
  sum(mastered_knowledge) AS total_knowledge_mastered,
  avg(path_progress) AS average_path_progress,

  // Life path info
  life_path.uid AS life_path_uid,
  life_path.title AS life_path_title

ORDER BY lp.section, lp.title
```

### Pattern 7: Adaptive Learning Recommendations

**Use Case:** Recommend next knowledge units based on UserContext

```cypher
// Adaptive recommendations based on user context
MATCH (user:User {uid: $user_uid})

// Get user's current learning path
MATCH (user)-[:ENROLLED_IN]->(current_path:Lp)
WHERE current_path.uid = $current_path_uid

// Get available knowledge units
MATCH (current_path)-[:CONTAINS]->(ku:Curriculum)

// Filter by prerequisites (all must be mastered)
OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Curriculum)
WITH ku, current_path, user,
     collect(prereq.uid) AS prereq_uids,
     $mastered_uids AS mastered

WHERE
  // Prerequisites met
  (size(prereq_uids) = 0 OR all(p IN prereq_uids WHERE p IN mastered))

  // Not already mastered
  AND ku.uid NOT IN mastered

  // Time budget filter
  AND ku.estimated_minutes <= $available_minutes

  // Difficulty filter based on learning level
  AND CASE $learning_level
    WHEN 'beginner' THEN ku.difficulty IN ['beginner', 'intermediate']
    WHEN 'intermediate' THEN ku.difficulty IN ['intermediate', 'advanced']
    WHEN 'advanced' THEN true  // All levels
    ELSE true
  END

// Calculate recommendation score
WITH ku, current_path,
     CASE ku.section
       WHEN 'foundation' THEN 3.0  // Prioritize foundation
       WHEN 'practice' THEN 2.0
       WHEN 'integration' THEN 1.0
     END AS section_priority,

     CASE ku.difficulty
       WHEN $learning_level THEN 2.0  // Match user level
       ELSE 1.0
     END AS difficulty_match,

     // Prefer knowledge that enables more downstream knowledge
     size((ku)-[:ENABLES_KNOWLEDGE]->(:Curriculum)) AS enablement_score

WITH ku, current_path,
     (section_priority + difficulty_match + (enablement_score * 0.5)) AS recommendation_score

RETURN
  ku.uid AS knowledge_uid,
  ku.title AS title,
  ku.section AS section,
  ku.estimated_minutes AS time_required,
  ku.difficulty AS difficulty,
  recommendation_score,
  current_path.title AS path_title

ORDER BY recommendation_score DESC, ku.sequence_order
LIMIT $limit
```

### Pattern 8: Knowledge Substance Tracking

**Use Case:** Track and update knowledge substance scores based on real-world application

```cypher
// Update knowledge substance based on domain events
MATCH (user:User {uid: $user_uid})-[:APPLIED]->(ku:Curriculum {uid: $knowledge_uid})

// Get application counts over last 30 days
MATCH (ku)<-[app:APPLIES_KNOWLEDGE]-(entity)
WHERE
  entity.user_uid = $user_uid
  AND app.created_at >= datetime() - duration({days: 30})

// Group by domain type
WITH ku, user, app, entity,
     CASE
       WHEN entity:Task THEN 'task'
       WHEN entity:Habit THEN 'habit'
       WHEN entity:Goal THEN 'goal'
       WHEN entity:Event THEN 'event'
       WHEN entity:Journal THEN 'journal'
       WHEN entity:Choice THEN 'choice'
       ELSE 'other'
     END AS domain_type

WITH ku, user,
     count(CASE WHEN domain_type = 'habit' THEN 1 END) AS habit_count,
     count(CASE WHEN domain_type = 'journal' THEN 1 END) AS journal_count,
     count(CASE WHEN domain_type = 'choice' THEN 1 END) AS choice_count,
     count(CASE WHEN domain_type = 'event' THEN 1 END) AS event_count,
     count(CASE WHEN domain_type = 'task' THEN 1 END) AS task_count

// Calculate substance score (weighted by domain importance)
WITH ku, user,
     habit_count, journal_count, choice_count, event_count, task_count,

     // Base substance from application counts
     (habit_count * 0.10 +      // Max 0.30 (lifestyle integration)
      journal_count * 0.07 +     // Max 0.20 (metacognition)
      choice_count * 0.07 +      // Max 0.15 (decision wisdom)
      event_count * 0.05 +       // Max 0.25 (practice)
      task_count * 0.05) AS raw_substance,

     // Cap at 1.0 max
     CASE
       WHEN (habit_count * 0.10 + journal_count * 0.07 + choice_count * 0.07 + event_count * 0.05 + task_count * 0.05) > 1.0
       THEN 1.0
       ELSE (habit_count * 0.10 + journal_count * 0.07 + choice_count * 0.07 + event_count * 0.05 + task_count * 0.05)
     END AS capped_substance

// Apply time decay (30-day half-life)
WITH ku, user,
     habit_count, journal_count, choice_count, event_count, task_count,
     capped_substance,

     // Time decay factor (assumes apps distributed over 30 days)
     0.85 AS decay_factor  // Approx 30-day half-life

WITH ku, user,
     capped_substance * decay_factor AS substance_score,
     habit_count, journal_count, choice_count, event_count, task_count

// Update or create APPLIED relationship
MERGE (user)-[r:APPLIED]->(ku)
SET
  r.substance_score = substance_score,
  r.updated_at = datetime(),
  r.habit_applications = habit_count,
  r.journal_applications = journal_count,
  r.choice_applications = choice_count,
  r.event_applications = event_count,
  r.task_applications = task_count

RETURN
  ku.uid AS knowledge_uid,
  ku.title AS title,
  substance_score,
  habit_count,
  journal_count,
  choice_count,
  event_count,
  task_count,

  // Interpretation
  CASE
    WHEN substance_score >= 0.8 THEN 'Lifestyle Integrated'
    WHEN substance_score >= 0.6 THEN 'Well Practiced'
    WHEN substance_score >= 0.3 THEN 'Applied Knowledge'
    ELSE 'Pure Theory'
  END AS substance_level
```

---

## Performance Considerations

### Indexes (Pure Cypher)

```cypher
// Core entity constraints (unique identifiers)
CREATE CONSTRAINT lp_uid IF NOT EXISTS FOR (lp:Lp) REQUIRE lp.uid IS UNIQUE;
CREATE CONSTRAINT ku_uid IF NOT EXISTS FOR (ku:Curriculum) REQUIRE ku.uid IS UNIQUE;
CREATE CONSTRAINT user_uid IF NOT EXISTS FOR (u:User) REQUIRE u.uid IS UNIQUE;

// Supporting domain constraints
CREATE CONSTRAINT task_uid IF NOT EXISTS FOR (t:Task) REQUIRE t.uid IS UNIQUE;
CREATE CONSTRAINT habit_uid IF NOT EXISTS FOR (h:Habit) REQUIRE h.uid IS UNIQUE;
CREATE CONSTRAINT goal_uid IF NOT EXISTS FOR (g:Goal) REQUIRE g.uid IS UNIQUE;
CREATE CONSTRAINT event_uid IF NOT EXISTS FOR (e:Event) REQUIRE e.uid IS UNIQUE;
CREATE CONSTRAINT journal_uid IF NOT EXISTS FOR (j:Journal) REQUIRE j.uid IS UNIQUE;

// Indexes for common query patterns
CREATE INDEX ku_section IF NOT EXISTS FOR (ku:Curriculum) ON (ku.section);
CREATE INDEX lp_section IF NOT EXISTS FOR (lp:Lp) ON (lp.section);
CREATE INDEX user_lookup IF NOT EXISTS FOR (u:User) ON (u.username);
```

### Query Optimization Tips

1. **Use PROFILE to analyze queries**
   ```cypher
   PROFILE <your query>
   ```

2. **Limit relationship traversal depth**
   - Use `[:REQUIRES_KNOWLEDGE*0..5]` instead of `[:REQUIRES_KNOWLEDGE*]`
   - Set reasonable max depth based on curriculum structure

3. **Filter early in the query**
   - Apply WHERE clauses immediately after MATCH
   - Use parameters for user-specific filters

4. **Use EXISTS for conditional relationships**
   ```cypher
   WHERE exists((ku)-[:REQUIRES_KNOWLEDGE]->())  // Has prerequisites
   ```

5. **Batch operations with UNWIND**
   - Process multiple entities in single query
   - Reduce network round-trips

---

## APOC Metadata Enhancements

While SKUEL runs Pure Cypher by default, APOC can enhance metadata operations when available.

### Optional APOC Pattern: Enhanced Metadata Aggregation

```cypher
// Enhanced metadata collection using APOC (optional)
MATCH (user:User {uid: $user_uid})
MATCH (ku:Curriculum {uid: $knowledge_uid})

// Collect all metadata using APOC (if available)
WITH ku, user,
     apoc.map.fromPairs([
       ['applications', apoc.meta.stats()],
       ['relationships', apoc.meta.relTypeProperties()],
       ['schema_info', apoc.meta.schema()]
     ]) AS enhanced_metadata

// Fallback to pure Cypher if APOC not available
RETURN
  CASE
    WHEN enhanced_metadata IS NOT NULL THEN enhanced_metadata
    ELSE {
      applications: 'N/A',
      relationships: 'N/A',
      schema_info: 'N/A'
    }
  END AS metadata
```

**When to use APOC:**
- Schema introspection (`apoc.meta.*`)
- Complex metadata aggregation
- Performance-critical batch operations
- Non-critical features (graceful degradation if unavailable)

**When NOT to use APOC:**
- Core curriculum queries (use Pure Cypher)
- Prerequisite traversal (use Pure Cypher)
- User progress tracking (use Pure Cypher)
- Any query that blocks core functionality

---

## Summary

**SKUEL Query Design Principles:**

1. **UserContext-Driven** - Every query considers user state for personalization
2. **Curriculum-Aware** - Leverage LearningPath → KnowledgeUnit → Domains structure
3. **Pure Cypher First** - Core functionality uses standard Cypher only
4. **APOC Optional** - Metadata enhancements when available, graceful degradation
5. **Life Path Alignment** - Track substance (real-world application) not just mastery
6. **Performance-Conscious** - Proper indexing, limited traversal depth, early filtering

**Next Steps:**

1. Add query performance monitoring
2. Document query usage in service layer
3. See `/docs/intelligence/PEDAGOGICAL_QUESTIONS.md` for the pedagogical questions these patterns serve
