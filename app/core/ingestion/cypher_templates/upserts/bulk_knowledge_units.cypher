// Bulk upsert template for KnowledgeUnits with relationships
UNWIND $items AS i
MERGE (ku:Ku {uid: i.uid})
  ON CREATE SET
    ku.title = i.title,
    ku.type = coalesce(i.type, "concept"),
    ku.status = coalesce(i.status, "draft"),
    ku.created_at = datetime()
  ON MATCH SET
    ku.title = i.title,
    ku.type = coalesce(i.type, ku.type),
    ku.status = coalesce(i.status, ku.status),
    ku.updated_at = datetime(),
    ku.description = i.description,
    ku.word_count = coalesce(i.word_count, 0),
    ku.notes = i.notes,
    ku.tags = coalesce(i.tags, []),
    ku.level = coalesce(i.level, ku.level),
    ku.metadata = coalesce(i.metadata, {})

// Handle domains
WITH ku, i
FOREACH (dom IN coalesce(i.domains, []) |
  MERGE (d:KnowledgeDomain {uid: dom})
  MERGE (ku)-[:IN_DOMAIN]->(d)
)

// Handle relationships
WITH ku, i
FOREACH (rid IN coalesce(i.connections.related, []) |
  MERGE (r:Ku {uid: rid})
  MERGE (ku)-[:RELATED_TO]->(r)
)

WITH ku, i
FOREACH (sid IN coalesce(i.connections.supports, []) |
  MERGE (s:Ku {uid: sid})
  MERGE (ku)-[:SUPPORTS]->(s)
)

WITH ku, i
FOREACH (eid IN coalesce(i.connections.enables, []) |
  MERGE (e:Ku {uid: eid})
  MERGE (ku)-[:ENABLES_KNOWLEDGE]->(e)
)

WITH ku, i
FOREACH (rid IN coalesce(i.connections.requires, []) |
  MERGE (r:Ku {uid: rid})
  MERGE (ku)-[:REQUIRES_KNOWLEDGE]->(r)
)

WITH ku, i
FOREACH (jid IN coalesce(i.connections.mentions_in, []) |
  MERGE (je:JournalEntry {uid: jid})
  MERGE (ku)-[:MENTIONS_IN]->(je)
)

RETURN count(ku) as processed