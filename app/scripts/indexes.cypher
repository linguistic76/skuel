// =============================================================================
// SKUEL Neo4j Index Reference
// =============================================================================
// This file documents the complete index set. Actual creation is automated
// via Neo4jSchemaManager.sync_domain_indexes() at bootstrap.
//
// Run manually only if needed: paste into Neo4j Browser or cypher-shell.
// =============================================================================

// UID indexes (19 — one per indexed entity type + Entity base)
CREATE INDEX entity_uid_idx IF NOT EXISTS FOR (n:Entity) ON (n.uid);
CREATE INDEX task_uid_idx IF NOT EXISTS FOR (n:Task) ON (n.uid);
CREATE INDEX goal_uid_idx IF NOT EXISTS FOR (n:Goal) ON (n.uid);
CREATE INDEX habit_uid_idx IF NOT EXISTS FOR (n:Habit) ON (n.uid);
CREATE INDEX event_uid_idx IF NOT EXISTS FOR (n:Event) ON (n.uid);
CREATE INDEX choice_uid_idx IF NOT EXISTS FOR (n:Choice) ON (n.uid);
CREATE INDEX principle_uid_idx IF NOT EXISTS FOR (n:Principle) ON (n.uid);
CREATE INDEX ku_uid_idx IF NOT EXISTS FOR (n:Ku) ON (n.uid);
CREATE INDEX exercise_uid_idx IF NOT EXISTS FOR (n:Exercise) ON (n.uid);
CREATE INDEX learning_path_uid_idx IF NOT EXISTS FOR (n:LearningPath) ON (n.uid);
CREATE INDEX learning_step_uid_idx IF NOT EXISTS FOR (n:PathStep) ON (n.uid);
CREATE INDEX life_path_uid_idx IF NOT EXISTS FOR (n:LifePath) ON (n.uid);
CREATE INDEX resource_uid_idx IF NOT EXISTS FOR (n:Resource) ON (n.uid);
CREATE INDEX user_entry_uid_idx IF NOT EXISTS FOR (n:UserEntry) ON (n.uid);
CREATE INDEX exercise_report_uid_idx IF NOT EXISTS FOR (n:ExerciseReport) ON (n.uid);
CREATE INDEX activity_report_uid_idx IF NOT EXISTS FOR (n:ActivityReport) ON (n.uid);
CREATE INDEX form_template_uid_idx IF NOT EXISTS FOR (n:FormTemplate) ON (n.uid);
CREATE INDEX form_submission_uid_idx IF NOT EXISTS FOR (n:FormSubmission) ON (n.uid);
CREATE INDEX revised_exercise_uid_idx IF NOT EXISTS FOR (n:RevisedExercise) ON (n.uid);

// User UID indexes (12 — all UserOwnedEntity types)
CREATE INDEX task_user_uid_idx IF NOT EXISTS FOR (n:Task) ON (n.user_uid);
CREATE INDEX goal_user_uid_idx IF NOT EXISTS FOR (n:Goal) ON (n.user_uid);
CREATE INDEX habit_user_uid_idx IF NOT EXISTS FOR (n:Habit) ON (n.user_uid);
CREATE INDEX event_user_uid_idx IF NOT EXISTS FOR (n:Event) ON (n.user_uid);
CREATE INDEX choice_user_uid_idx IF NOT EXISTS FOR (n:Choice) ON (n.user_uid);
CREATE INDEX principle_user_uid_idx IF NOT EXISTS FOR (n:Principle) ON (n.user_uid);
CREATE INDEX user_entry_user_uid_idx IF NOT EXISTS FOR (n:UserEntry) ON (n.user_uid);
CREATE INDEX exercise_report_user_uid_idx IF NOT EXISTS FOR (n:ExerciseReport) ON (n.user_uid);
CREATE INDEX activity_report_user_uid_idx IF NOT EXISTS FOR (n:ActivityReport) ON (n.user_uid);
CREATE INDEX form_submission_user_uid_idx IF NOT EXISTS FOR (n:FormSubmission) ON (n.user_uid);
CREATE INDEX revised_exercise_user_uid_idx IF NOT EXISTS FOR (n:RevisedExercise) ON (n.user_uid);
CREATE INDEX life_path_user_uid_idx IF NOT EXISTS FOR (n:LifePath) ON (n.user_uid);

// Status indexes (4 — time-sensitive activity domains)
CREATE INDEX task_status_idx IF NOT EXISTS FOR (n:Task) ON (n.status);
CREATE INDEX goal_status_idx IF NOT EXISTS FOR (n:Goal) ON (n.status);
CREATE INDEX habit_status_idx IF NOT EXISTS FOR (n:Habit) ON (n.status);
CREATE INDEX event_status_idx IF NOT EXISTS FOR (n:Event) ON (n.status);

// Date indexes (4 — temporal queries)
CREATE INDEX task_due_date_idx IF NOT EXISTS FOR (n:Task) ON (n.due_date);
CREATE INDEX event_event_date_idx IF NOT EXISTS FOR (n:Event) ON (n.event_date);
CREATE INDEX goal_target_date_idx IF NOT EXISTS FOR (n:Goal) ON (n.target_date);
CREATE INDEX expense_expense_date_idx IF NOT EXISTS FOR (n:Expense) ON (n.expense_date);

// Entity type discriminator index
CREATE INDEX entity_type_idx IF NOT EXISTS FOR (n:Entity) ON (n.entity_type);

// Composite indexes (3 — hot query paths)
CREATE INDEX task_user_status_idx IF NOT EXISTS FOR (n:Task) ON (n.user_uid, n.status);
CREATE INDEX goal_user_status_idx IF NOT EXISTS FOR (n:Goal) ON (n.user_uid, n.status);
CREATE INDEX entity_user_type_idx IF NOT EXISTS FOR (n:Entity) ON (n.user_uid, n.entity_type);

// =============================================================================
// Stale indexes (DROP if present from old schema)
// =============================================================================
DROP INDEX ai_report_uid_idx IF EXISTS;
DROP INDEX lpstep_embedding_idx IF EXISTS;
DROP INDEX lesson_uid_idx IF EXISTS;
DROP INDEX journal_submission_uid_idx IF EXISTS;
DROP INDEX journal_report_uid_idx IF EXISTS;
DROP INDEX journal_submission_user_uid_idx IF EXISTS;
DROP INDEX journal_report_user_uid_idx IF EXISTS;
