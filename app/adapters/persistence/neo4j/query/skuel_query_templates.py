"""
SKUEL-Specific Query Templates - Pure Cypher patterns for curriculum navigation.

This module provides reusable Cypher query templates optimized for SKUEL's
curriculum architecture (LearningPaths → KnowledgeUnits → Supporting Domains)
and UserContext-driven personalization.

Core Design Principles:
- UserContext-driven: Every query considers user state for personalization
- Curriculum-aware: Leverage LearningPath → KnowledgeUnit → Domains structure
- Pure Cypher first: Core functionality uses standard Cypher only
- APOC optional: Metadata enhancements when available, graceful degradation
- Life path alignment: Track substance (real-world application) not just mastery
- Performance-conscious: Proper indexing, limited traversal, early filtering

See: /docs/SKUEL_QUERY_DESIGN.md for complete design documentation
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class SkuelQueryTemplate:
    """
    Container for SKUEL-specific Cypher query templates.

    Each template is:
    - Pure Cypher (no APOC dependency)
    - UserContext-aware (accepts user state parameters)
    - Curriculum-optimized (leverages graph structure)
    - Performance-tuned (proper indexing, limited depth)
    """

    name: str
    description: str
    cypher: str
    parameters: dict[str, str]  # param_name -> description

    def execute_params(self, **kwargs: Any) -> dict[str, Any]:
        """
        Build parameter dict for query execution.

        Args:
            **kwargs: Parameter values

        Returns:
            Dict ready for Neo4j query execution
        """
        params = {}
        for param_name in self.parameters:
            if param_name in kwargs:
                params[param_name] = kwargs[param_name]
        return params


# ============================================================================
# Learning Path Navigation Templates
# ============================================================================

NEXT_KNOWLEDGE_IN_PATH = SkuelQueryTemplate(
    name="next_knowledge_in_path",
    description="Get next knowledge units in user's current learning path (prerequisites met)",
    cypher="""
    // Get user's current learning path
    MATCH (user:User {uid: $user_uid})-[:ENROLLED_IN]->(lp:Lp)
    WHERE lp.uid = $current_path_uid

    // Get available knowledge units
    MATCH (lp)-[:CONTAINS]->(ku:Entity)

    // Filter by prerequisites (all must be mastered)
    OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
    WITH ku, lp, user,
         collect(prereq.uid) AS prereq_uids,
         $mastered_uids AS mastered

    WHERE
      // Prerequisites met
      (size(prereq_uids) = 0 OR all(p IN prereq_uids WHERE p IN mastered))

      // Not already mastered
      AND ku.uid NOT IN mastered

      // Time budget filter
      AND ku.estimated_minutes <= $available_minutes

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
    """,
    parameters={
        "user_uid": "User identifier",
        "current_path_uid": "Current learning path UID",
        "mastered_uids": "List of mastered knowledge UIDs",
        "available_minutes": "User's available time in minutes",
        "limit": "Maximum number of results (default: 10)",
    },
)

LIFE_PATH_ALIGNMENT = SkuelQueryTemplate(
    name="life_path_alignment",
    description="Calculate life alignment by checking knowledge substance across life path",
    cypher="""
    // Get user's life path knowledge with substance scores
    MATCH (user:User {uid: $user_uid})-[:ULTIMATE_PATH]->(life_path:Lp)

    // Get all knowledge in life path
    MATCH (life_path)-[:CONTAINS]->(ku:Entity)

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
    """,
    parameters={"user_uid": "User identifier"},
)

REQUIRES_KNOWLEDGE_CHAIN = SkuelQueryTemplate(
    name="requires_knowledge_chain",
    description="Find complete requires-knowledge chain (recursive) for a target knowledge unit",
    cypher="""
    // Find complete requires-knowledge chain for target knowledge
    MATCH path = (target:Entity {uid: $target_uid})-[:REQUIRES_KNOWLEDGE*0..5]->(prereq:Entity)

    // Get user's mastery state
    MATCH (user:User {uid: $user_uid})
    OPTIONAL MATCH (user)-[r:MASTERED]->(prereq)

    WITH prereq, target, path,
         exists((user)-[:MASTERED]->(prereq)) AS is_mastered,
         length(path) AS depth

    RETURN
      prereq.uid AS knowledge_uid,
      prereq.title AS title,
      depth AS prerequisite_depth,
      is_mastered,
      CASE
        WHEN depth = 0 THEN 'TARGET'
        WHEN depth = 1 THEN 'DIRECT_PREREQUISITE'
        ELSE 'TRANSITIVE_PREREQUISITE'
      END AS prerequisite_type

    ORDER BY depth, prereq.sequence_order
    """,
    parameters={"user_uid": "User identifier", "target_uid": "Target knowledge unit UID"},
)

CROSS_DOMAIN_APPLICATIONS = SkuelQueryTemplate(
    name="cross_domain_applications",
    description="Show how knowledge is applied across supporting domains",
    cypher="""
    // Find all applications of specific knowledge across domains
    MATCH (ku:Entity {uid: $knowledge_uid})

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

      // Substance indicators
      count(DISTINCT task) AS task_count,
      count(DISTINCT habit) AS habit_count,
      count(DISTINCT goal) AS goal_count,
      count(DISTINCT event) AS event_count,
      count(DISTINCT journal) AS journal_count,

      // Estimated substance score
      (count(DISTINCT habit) * 0.10 +
       count(DISTINCT journal) * 0.07 +
       count(DISTINCT event) * 0.05 +
       count(DISTINCT task) * 0.05) AS estimated_substance_score
    """,
    parameters={"user_uid": "User identifier", "knowledge_uid": "Knowledge unit UID"},
)

USER_PROGRESS_SNAPSHOT = SkuelQueryTemplate(
    name="user_progress_snapshot",
    description="Get complete snapshot of user's learning progress across all paths",
    cypher="""
    // Get comprehensive user progress across all learning paths
    MATCH (user:User {uid: $user_uid})

    // Get all enrolled learning paths
    OPTIONAL MATCH (user)-[:ENROLLED_IN]->(lp:Lp)
    OPTIONAL MATCH (lp)-[:CONTAINS]->(ku:Entity)

    // Get mastery state
    OPTIONAL MATCH (user)-[m:MASTERED]->(mastered_ku:Entity)
    WHERE mastered_ku.uid = ku.uid

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
    """,
    parameters={"user_uid": "User identifier"},
)

ADAPTIVE_RECOMMENDATIONS = SkuelQueryTemplate(
    name="adaptive_recommendations",
    description="Recommend next knowledge units based on UserContext",
    cypher="""
    // Adaptive recommendations based on user context
    MATCH (user:User {uid: $user_uid})

    // Get user's current learning path
    MATCH (user)-[:ENROLLED_IN]->(current_path:Lp)
    WHERE current_path.uid = $current_path_uid

    // Get available knowledge units
    MATCH (current_path)-[:CONTAINS]->(ku:Entity)

    // Filter by prerequisites (all must be mastered)
    OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
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
        WHEN 'advanced' THEN true
        ELSE true
      END

    // Calculate recommendation score
    WITH ku, current_path,
         CASE ku.section
           WHEN 'foundation' THEN 3.0
           WHEN 'practice' THEN 2.0
           WHEN 'integration' THEN 1.0
         END AS section_priority,

         CASE ku.difficulty
           WHEN $learning_level THEN 2.0
           ELSE 1.0
         END AS difficulty_match,

         size((ku)-[:ENABLES_KNOWLEDGE]->(:Entity)) AS enablement_score

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
    """,
    parameters={
        "user_uid": "User identifier",
        "current_path_uid": "Current learning path UID",
        "mastered_uids": "List of mastered knowledge UIDs",
        "available_minutes": "User's available time in minutes",
        "learning_level": "User's learning level (beginner/intermediate/advanced)",
        "limit": "Maximum number of results (default: 10)",
    },
)

KNOWLEDGE_SUBSTANCE_UPDATE = SkuelQueryTemplate(
    name="knowledge_substance_update",
    description="Update knowledge substance score based on domain event applications",
    cypher="""
    // Update knowledge substance based on domain events
    MATCH (user:User {uid: $user_uid})
    MATCH (ku:Entity {uid: $knowledge_uid})

    // Get application counts over last 30 days
    OPTIONAL MATCH (ku)<-[app:APPLIES_KNOWLEDGE]-(entity)
    WHERE
      entity.user_uid = $user_uid
      AND app.created_at >= datetime() - duration({days: 30})

    // Group by domain type
    WITH ku, user, entity,
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

    // Calculate substance score (weighted, capped at 1.0)
    WITH ku, user,
         habit_count, journal_count, choice_count, event_count, task_count,
         CASE
           WHEN (habit_count * 0.10 + journal_count * 0.07 + choice_count * 0.07 + event_count * 0.05 + task_count * 0.05) > 1.0
           THEN 1.0
           ELSE (habit_count * 0.10 + journal_count * 0.07 + choice_count * 0.07 + event_count * 0.05 + task_count * 0.05)
         END AS capped_substance

    // Apply time decay (30-day half-life)
    WITH ku, user,
         capped_substance * 0.85 AS substance_score,
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
    """,
    parameters={"user_uid": "User identifier", "knowledge_uid": "Knowledge unit UID to update"},
)

# ============================================================================
# Bulk Ingestion Templates
# ============================================================================

BULK_LEARNING_PATH_INGESTION = SkuelQueryTemplate(
    name="bulk_learning_path_ingestion",
    description="Import learning paths and knowledge units from structured data",
    cypher="""
    // Create LearningPaths with sections
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

    // Create KnowledgeUnits
    UNWIND lp_data.knowledge_units AS ku_data

    MERGE (ku:Entity {uid: ku_data.uid})
    SET
      ku.title = ku_data.title,
      ku.word_count = coalesce(ku_data.word_count, 0),
      ku.section = ku_data.section,
      ku.sequence_order = ku_data.sequence_order,
      ku.estimated_minutes = ku_data.estimated_minutes,
      ku.difficulty = ku_data.difficulty,
      ku.domain = ku_data.domain,
      ku.updated_at = datetime()

    // Wire KU to LearningPath
    MERGE (ku)-[:PART_OF]->(lp)

    WITH ku, ku_data

    // Create prerequisite relationships
    FOREACH (prereq_uid IN coalesce(ku_data.prerequisites, []) |
      MERGE (prereq:Entity {uid: prereq_uid})
      MERGE (ku)-[:REQUIRES_KNOWLEDGE]->(prereq)
    )

    // Create enables relationships
    FOREACH (enabled_uid IN coalesce(ku_data.enables, []) |
      MERGE (enabled:Entity {uid: enabled_uid})
      MERGE (ku)-[:ENABLES_KNOWLEDGE]->(enabled)
    )

    RETURN
      count(DISTINCT lp) AS learning_paths_created,
      count(DISTINCT ku) AS knowledge_units_created
    """,
    parameters={
        "learning_paths": "List of learning path data structures with nested knowledge units"
    },
)

# ============================================================================
# Schema Setup Templates
# ============================================================================

CREATE_CONSTRAINTS = SkuelQueryTemplate(
    name="create_constraints",
    description="Create unique constraints for SKUEL core entities (idempotent)",
    cypher="""
    // Core entity constraints
    CREATE CONSTRAINT lp_uid IF NOT EXISTS FOR (lp:Lp) REQUIRE lp.uid IS UNIQUE;
    CREATE CONSTRAINT ku_uid IF NOT EXISTS FOR (ku:Entity) REQUIRE ku.uid IS UNIQUE;
    CREATE CONSTRAINT user_uid IF NOT EXISTS FOR (u:User) REQUIRE u.uid IS UNIQUE;

    // Supporting domain constraints
    CREATE CONSTRAINT task_uid IF NOT EXISTS FOR (t:Task) REQUIRE t.uid IS UNIQUE;
    CREATE CONSTRAINT habit_uid IF NOT EXISTS FOR (h:Habit) REQUIRE h.uid IS UNIQUE;
    CREATE CONSTRAINT goal_uid IF NOT EXISTS FOR (g:Goal) REQUIRE g.uid IS UNIQUE;
    CREATE CONSTRAINT event_uid IF NOT EXISTS FOR (e:Event) REQUIRE e.uid IS UNIQUE;
    CREATE CONSTRAINT journal_uid IF NOT EXISTS FOR (j:Journal) REQUIRE j.uid IS UNIQUE;
    """,
    parameters={},
)

CREATE_INDEXES = SkuelQueryTemplate(
    name="create_indexes",
    description="Create indexes for common query patterns (idempotent)",
    cypher="""
    // Section-based queries (foundation/practice/integration)
    CREATE INDEX ku_section IF NOT EXISTS FOR (ku:Entity) ON (ku.section);
    CREATE INDEX lp_section IF NOT EXISTS FOR (lp:Lp) ON (lp.section);

    // User lookup
    CREATE INDEX user_lookup IF NOT EXISTS FOR (u:User) ON (u.username);

    // Domain filtering
    CREATE INDEX ku_domain IF NOT EXISTS FOR (ku:Entity) ON (ku.domain);
    """,
    parameters={},
)

# ============================================================================
# Template Registry
# ============================================================================

ALL_TEMPLATES = {
    "next_knowledge_in_path": NEXT_KNOWLEDGE_IN_PATH,
    "life_path_alignment": LIFE_PATH_ALIGNMENT,
    "requires_knowledge_chain": REQUIRES_KNOWLEDGE_CHAIN,
    "cross_domain_applications": CROSS_DOMAIN_APPLICATIONS,
    "user_progress_snapshot": USER_PROGRESS_SNAPSHOT,
    "adaptive_recommendations": ADAPTIVE_RECOMMENDATIONS,
    "knowledge_substance_update": KNOWLEDGE_SUBSTANCE_UPDATE,
    "bulk_learning_path_ingestion": BULK_LEARNING_PATH_INGESTION,
    "create_constraints": CREATE_CONSTRAINTS,
    "create_indexes": CREATE_INDEXES,
}


def get_template(name: str) -> SkuelQueryTemplate:
    """
    Get query template by name.

    Args:
        name: Template name (e.g., 'next_knowledge_in_path')

    Returns:
        SkuelQueryTemplate instance

    Raises:
        KeyError: If template not found
    """
    if name not in ALL_TEMPLATES:
        available = ", ".join(ALL_TEMPLATES.keys())
        msg = f"Template '{name}' not found. Available templates: {available}"
        raise KeyError(msg)

    return ALL_TEMPLATES[name]


def list_templates() -> list[str]:
    """Get list of all available template names."""
    return list(ALL_TEMPLATES.keys())


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "ADAPTIVE_RECOMMENDATIONS",
    "ALL_TEMPLATES",
    "BULK_LEARNING_PATH_INGESTION",
    "CREATE_CONSTRAINTS",
    "CREATE_INDEXES",
    "CROSS_DOMAIN_APPLICATIONS",
    "KNOWLEDGE_SUBSTANCE_UPDATE",
    "LIFE_PATH_ALIGNMENT",
    # Individual templates
    "NEXT_KNOWLEDGE_IN_PATH",
    "REQUIRES_KNOWLEDGE_CHAIN",
    "USER_PROGRESS_SNAPSHOT",
    "SkuelQueryTemplate",
    "get_template",
    "list_templates",
]
