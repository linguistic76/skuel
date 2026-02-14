// Migration: Event → Ku (unified model)
// Phase 4: Activity Domain Migrations
// Date: 2026-02-11
//
// This script migrates :Event nodes to :Ku nodes with ku_type='event'.
// Idempotent — safe to re-run.

// Step 1: Add :Ku label and set ku_type on all Event nodes
MATCH (n:Event)
WHERE NOT n:Ku
SET n:Ku, n.ku_type = 'event'
RETURN count(n) AS events_labeled;

// Step 2: Map ActivityStatus to KuStatus
// SCHEDULED → scheduled (same)
// COMPLETED → completed (same)
// CANCELLED → cancelled (same)
// IN_PROGRESS → active
MATCH (n:Ku {ku_type: 'event'})
WHERE n.status = 'in_progress'
SET n.status = 'active'
RETURN count(n) AS status_mapped;

// Step 3: Convert HAS_EVENT ownership relationships to HAS_KU
MATCH (u:User)-[old:HAS_EVENT]->(k:Ku {ku_type: 'event'})
WHERE NOT EXISTS((u)-[:HAS_KU]->(k))
MERGE (u)-[:HAS_KU]->(k)
WITH old
DELETE old
RETURN count(old) AS relationships_converted;

// Step 4: Remove old :Event label
MATCH (n:Event:Ku {ku_type: 'event'})
REMOVE n:Event
RETURN count(n) AS labels_removed;

// Step 5: Verify migration
MATCH (n:Event) RETURN count(n) AS remaining_event_nodes;
MATCH (n:Ku {ku_type: 'event'}) RETURN count(n) AS event_ku_nodes;
