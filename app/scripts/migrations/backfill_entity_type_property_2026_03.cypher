// Backfill entity_type property on Entity nodes that lack it.
// ============================================================
//
// Context: The ingestion pipeline (YAML → Neo4j) was not injecting the
// entity_type property on nodes. Nodes created via API/CRUD had it (from the
// Entity dataclass), but ingested nodes did not. This migration uses domain
// labels to set the correct value.
//
// Safe to run multiple times (idempotent — only sets WHERE n.entity_type IS NULL).
// Run after deploying the preparer.py fix that injects entity_type during ingestion.
//
// ⚠ 2026-08-10 (#1009): the :PathStep line wrote `learning_step`, which is NOT
// an EntityType member. Because this file is idempotent and still in the tree it
// was a latent RESPAWNER — a future run would stamp a discriminator that every
// entity_type-scoped query silently misses (Neo4j matches zero rows on an
// unknown value rather than erroring). Corrected to `path_step`. This fixes the
// WRITER, not the data: no live node carries it (all 25 :PathStep nodes already
// read `path_step`).
//
// STILL STALE, deliberately left for a separate change — this is pre-ADR-054
// residue and does not belong in a security PR. FIVE more values here are not
// EntityType members (`lesson`, `exercise_submission`, `exercise_report`,
// `je_input`, `je_output`) and five labels are not NeoLabel members (:Lesson,
// :ExerciseSubmission, :ExerciseReport, :JeInput, :JeOutput — ADR-054 replaced
// submissions/ and journal/ with UserEntry/EntryReport). All have zero live
// nodes. Retiring this file wholesale is the likely right answer.

// Activity domains (6)
MATCH (n:Task) WHERE n.entity_type IS NULL SET n.entity_type = "task";
MATCH (n:Goal) WHERE n.entity_type IS NULL SET n.entity_type = "goal";
MATCH (n:Habit) WHERE n.entity_type IS NULL SET n.entity_type = "habit";
MATCH (n:Event) WHERE n.entity_type IS NULL SET n.entity_type = "event";
MATCH (n:Choice) WHERE n.entity_type IS NULL SET n.entity_type = "choice";
MATCH (n:Principle) WHERE n.entity_type IS NULL SET n.entity_type = "principle";

// Curriculum domains (5)
MATCH (n:Lesson) WHERE n.entity_type IS NULL SET n.entity_type = "lesson";
MATCH (n:Ku) WHERE n.entity_type IS NULL SET n.entity_type = "ku";
MATCH (n:PathStep) WHERE n.entity_type IS NULL SET n.entity_type = "path_step";
MATCH (n:LearningPath) WHERE n.entity_type IS NULL SET n.entity_type = "learning_path";
MATCH (n:Exercise) WHERE n.entity_type IS NULL SET n.entity_type = "exercise";

// Instruction Templates + Curated (3)
MATCH (n:RevisedExercise) WHERE n.entity_type IS NULL SET n.entity_type = "revised_exercise";
MATCH (n:Resource) WHERE n.entity_type IS NULL SET n.entity_type = "resource";

// Submissions/Reports (3)
MATCH (n:ExerciseSubmission) WHERE n.entity_type IS NULL SET n.entity_type = "exercise_submission";
MATCH (n:ActivityReport) WHERE n.entity_type IS NULL SET n.entity_type = "activity_report";
MATCH (n:ExerciseReport) WHERE n.entity_type IS NULL SET n.entity_type = "exercise_report";

// Journal (2)
MATCH (n:JeInput) WHERE n.entity_type IS NULL SET n.entity_type = "je_input";
MATCH (n:JeOutput) WHERE n.entity_type IS NULL SET n.entity_type = "je_output";

// General-Purpose Forms (2)
MATCH (n:FormTemplate) WHERE n.entity_type IS NULL SET n.entity_type = "form_template";
MATCH (n:FormSubmission) WHERE n.entity_type IS NULL SET n.entity_type = "form_submission";

// Destination (1)
MATCH (n:LifePath) WHERE n.entity_type IS NULL SET n.entity_type = "life_path";

// Fix nodes that may have been ingested with wrong :Report label (stale config).
// These should have been :ExerciseSubmission all along.
MATCH (n:Report) WHERE n:Entity
REMOVE n:Report
SET n:ExerciseSubmission, n.entity_type = "exercise_submission";
