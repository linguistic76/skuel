// Migration: Rename principle.name → principle.title
// Date: 2026-02-10
// Purpose: Standardize Principle field name to match all other domains (Task, Goal, Habit, Event, Choice)
//
// This eliminates the semantic fracture where Principle used 'name' while all other domains
// and ContextualPrinciple used 'title'.

// Step 1: Verify current state (should have 'name' property)
MATCH (p:Principle)
WHERE p.name IS NOT NULL
WITH count(p) as principle_count
RETURN 'Principles with name property: ' + toString(principle_count) as status;

// Step 2: Copy name → title, remove name
MATCH (p:Principle)
WHERE p.name IS NOT NULL
SET p.title = p.name
REMOVE p.name
RETURN count(p) as principles_updated;

// Step 3: Verify migration (should have 'title' property, no 'name')
MATCH (p:Principle)
WITH
    count(p) as total_principles,
    count(CASE WHEN p.title IS NOT NULL THEN 1 END) as with_title,
    count(CASE WHEN p.name IS NOT NULL THEN 1 END) as with_name
RETURN
    'Total principles: ' + toString(total_principles) as total,
    'With title: ' + toString(with_title) as titles,
    'With name: ' + toString(with_name) as names,
    CASE
        WHEN with_name = 0 AND with_title = total_principles THEN '✓ Migration successful'
        ELSE '✗ Migration incomplete'
    END as result;

// Step 4: Create index on title if needed
CREATE INDEX principle_title_idx IF NOT EXISTS FOR (p:Principle) ON (p.title);
