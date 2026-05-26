// Bulk upsert template for LifePrinciples with relationships
UNWIND $items AS i
MERGE (lp:LifePrinciple {uid: i.uid})
  ON CREATE SET
    lp.title = i.title,
    lp.type = coalesce(i.type, "principle"),
    lp.created_at = datetime()
  ON MATCH SET
    lp.title = i.title,
    lp.type = coalesce(i.type, "principle"),
    lp.updated_at = datetime(),
    lp.description = i.description,
    lp.metaphor = i.metaphor,
    lp.rationale = i.rationale,
    lp.applications = coalesce(i.applications, []),
    lp.anti_patterns = coalesce(i.anti_patterns, []),
    lp.success_signals = coalesce(i.success_signals, []),
    lp.tags = coalesce(i.tags, [])

// Handle domains
WITH lp, i
FOREACH (dom IN coalesce(i.domains, []) |
  MERGE (d:KnowledgeDomain {uid: dom})
  MERGE (lp)-[:IN_DOMAIN]->(d)
)

// Handle connections
WITH lp, i
FOREACH (rid IN coalesce(i.connections.related, []) |
  MERGE (rku:Entity {uid: rid})
  MERGE (lp)-[:RELATED_TO]->(rku)
)

WITH lp, i
FOREACH (sid IN coalesce(i.connections.supports, []) |
  MERGE (sku:Entity {uid: sid})
  MERGE (lp)-[:SUPPORTS]->(sku)
)

WITH lp, i
FOREACH (jid IN coalesce(i.connections.mentions_in, []) |
  MERGE (je:JournalEntry {uid: jid})
  MERGE (lp)-[:MENTIONS_IN]->(je)
)

RETURN count(lp) as processed