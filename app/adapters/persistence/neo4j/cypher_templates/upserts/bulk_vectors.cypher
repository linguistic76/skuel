// Bulk upsert template for Vectors as first-class nodes
UNWIND $items AS i
MERGE (v:Vector {uid: i.uid})
  ON CREATE SET
    v.title = i.title,
    v.space = i.space,
    v.created_at = datetime()
  ON MATCH SET
    v.title = i.title,
    v.space = i.space,
    v.updated_at = datetime(),
    v.components = coalesce(i.components, {}),
    v.magnitude = i.magnitude,
    v.notes = coalesce(i.notes, "")

// Handle timeframe
WITH v, i
FOREACH (_ IN CASE WHEN i.timeframe IS NULL THEN [] ELSE [1] END |
  SET v.timeframe_start = i.timeframe.start,
      v.timeframe_end = i.timeframe.end
)

// Handle connections
WITH v, i
FOREACH (jid IN coalesce(i.connections.mentions_in, []) |
  MERGE (je:JournalEntry {uid: jid})
  MERGE (v)-[:MENTIONS_IN]->(je)
)

WITH v, i
FOREACH (lpid IN coalesce(i.connections.grounded_by, []) |
  MERGE (lp:LifePrinciple {uid: lpid})
  MERGE (v)-[:GROUNDED_BY]->(lp)
)

// Link to origin state
WITH v, i
FOREACH (_ IN CASE WHEN i.origin IS NULL THEN [] ELSE [1] END |
  MERGE (s1:State {uid: i.origin})
  MERGE (v)-[:FROM]->(s1)
)

// Link to target state
WITH v, i
FOREACH (_ IN CASE WHEN i.target IS NULL THEN [] ELSE [1] END |
  MERGE (s2:State {uid: i.target})
  MERGE (v)-[:TO]->(s2)
)

RETURN count(v) as processed