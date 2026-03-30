// Migration: Rename LearningStep to PathStep
// Date: 2026-03-30
// Context: LearningStep renamed to PathStep for better clarity (step within a LearningPath)

// Step 1: Add :PathStep label, remove :LearningStep, update entity_type property
MATCH (n:LearningStep)
SET n:PathStep
REMOVE n:LearningStep
SET n.entity_type = "path_step"
RETURN count(n) AS migrated_label_count;

// Step 2: Update UID prefixes from ls: to ps:
MATCH (n:PathStep) WHERE n.uid STARTS WITH "ls:"
SET n.uid = "ps:" + substring(n.uid, 3)
RETURN count(n) AS uid_migrated_count;

// Step 3: Verify — should return 0
MATCH (n:LearningStep) RETURN count(n) AS remaining_old_labels;
MATCH (n:PathStep) WHERE n.uid STARTS WITH "ls:" RETURN count(n) AS remaining_old_uids;
