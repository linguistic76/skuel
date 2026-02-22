// =============================================================================
// Migration: Add Domain-Specific Labels to Ku Nodes
// =============================================================================
// Phase 0 of domain-first architecture redesign.
//
// Changes:
// 1. Adds domain-specific labels (:Task, :Goal, etc.) based on ku_type property
// 2. Adds universal :Entity label to all :Ku nodes
// 3. Migrates HAS_KU relationships to OWNS
// 4. Creates per-domain indexes for query performance
//
// This is ADDITIVE — existing :Ku label is preserved for backward compatibility.
// After migration, nodes have triple labels: :Ku:Entity:Task
//
// Run: Each statement must be executed separately (Neo4j doesn't support
//      multiple statements in one query).
// =============================================================================

// --- Step 1: Add domain-specific labels based on ku_type ---

// Activity Domains (6)
MATCH (n:Ku) WHERE n.ku_type = 'task' SET n:Task;

MATCH (n:Ku) WHERE n.ku_type = 'goal' SET n:Goal;

MATCH (n:Ku) WHERE n.ku_type = 'habit' SET n:Habit;

MATCH (n:Ku) WHERE n.ku_type = 'event' SET n:Event;

MATCH (n:Ku) WHERE n.ku_type = 'choice' SET n:Choice;

MATCH (n:Ku) WHERE n.ku_type = 'principle' SET n:Principle;

// Curriculum Domains (4)
MATCH (n:Ku) WHERE n.ku_type = 'curriculum' SET n:Curriculum;

MATCH (n:Ku) WHERE n.ku_type = 'resource' SET n:Resource;

MATCH (n:Ku) WHERE n.ku_type = 'learning_step' SET n:LearningStep;

MATCH (n:Ku) WHERE n.ku_type = 'learning_path' SET n:LearningPath;

// Content Processing (4)
// Note: 'assignment' is legacy name for 'submission' (see KuType.SUBMISSION)
MATCH (n:Ku) WHERE n.ku_type IN ['submission', 'assignment'] SET n:Submission;

MATCH (n:Ku) WHERE n.ku_type = 'journal' SET n:Journal;

MATCH (n:Ku) WHERE n.ku_type = 'ai_report' SET n:AiReport;

MATCH (n:Ku) WHERE n.ku_type = 'feedback_report' SET n:Feedback;

// Instruction Templates (1)
MATCH (n:Ku) WHERE n.ku_type = 'exercise' SET n:Exercise;

// Destination (1)
MATCH (n:Ku) WHERE n.ku_type = 'life_path' SET n:LifePath;


// --- Step 2: Add universal Entity label to ALL Ku nodes ---
MATCH (n:Ku) SET n:Entity;


// --- Step 3: Migrate HAS_KU relationships to OWNS ---
// Create OWNS relationship with same properties, then delete HAS_KU
MATCH (u:User)-[r:HAS_KU]->(n:Ku)
CREATE (u)-[owns:OWNS]->(n)
SET owns = properties(r)
DELETE r;


// --- Step 4: Create per-domain indexes ---

// Domain-specific UID indexes (fast lookup by uid within domain)
CREATE INDEX task_uid_idx IF NOT EXISTS FOR (n:Task) ON (n.uid);
CREATE INDEX goal_uid_idx IF NOT EXISTS FOR (n:Goal) ON (n.uid);
CREATE INDEX habit_uid_idx IF NOT EXISTS FOR (n:Habit) ON (n.uid);
CREATE INDEX event_uid_idx IF NOT EXISTS FOR (n:Event) ON (n.uid);
CREATE INDEX choice_uid_idx IF NOT EXISTS FOR (n:Choice) ON (n.uid);
CREATE INDEX principle_uid_idx IF NOT EXISTS FOR (n:Principle) ON (n.uid);
CREATE INDEX curriculum_uid_idx IF NOT EXISTS FOR (n:Curriculum) ON (n.uid);
CREATE INDEX resource_uid_idx IF NOT EXISTS FOR (n:Resource) ON (n.uid);
CREATE INDEX learning_step_uid_idx IF NOT EXISTS FOR (n:LearningStep) ON (n.uid);
CREATE INDEX learning_path_uid_idx IF NOT EXISTS FOR (n:LearningPath) ON (n.uid);
CREATE INDEX submission_uid_idx IF NOT EXISTS FOR (n:Submission) ON (n.uid);
CREATE INDEX journal_uid_idx IF NOT EXISTS FOR (n:Journal) ON (n.uid);
CREATE INDEX ai_report_uid_idx IF NOT EXISTS FOR (n:AiReport) ON (n.uid);
CREATE INDEX feedback_uid_idx IF NOT EXISTS FOR (n:Feedback) ON (n.uid);
CREATE INDEX exercise_uid_idx IF NOT EXISTS FOR (n:Exercise) ON (n.uid);
CREATE INDEX life_path_uid_idx IF NOT EXISTS FOR (n:LifePath) ON (n.uid);

// Universal Entity indexes
CREATE INDEX entity_uid_idx IF NOT EXISTS FOR (n:Entity) ON (n.uid);
CREATE INDEX entity_type_idx IF NOT EXISTS FOR (n:Entity) ON (n.ku_type);

// Domain-specific user_uid indexes (ownership queries)
CREATE INDEX task_user_idx IF NOT EXISTS FOR (n:Task) ON (n.user_uid);
CREATE INDEX goal_user_idx IF NOT EXISTS FOR (n:Goal) ON (n.user_uid);
CREATE INDEX habit_user_idx IF NOT EXISTS FOR (n:Habit) ON (n.user_uid);
CREATE INDEX event_user_idx IF NOT EXISTS FOR (n:Event) ON (n.user_uid);
CREATE INDEX choice_user_idx IF NOT EXISTS FOR (n:Choice) ON (n.user_uid);
CREATE INDEX principle_user_idx IF NOT EXISTS FOR (n:Principle) ON (n.user_uid);
CREATE INDEX submission_user_idx IF NOT EXISTS FOR (n:Submission) ON (n.user_uid);
CREATE INDEX life_path_user_idx IF NOT EXISTS FOR (n:LifePath) ON (n.user_uid);
