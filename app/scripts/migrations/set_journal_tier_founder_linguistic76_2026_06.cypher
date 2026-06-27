// Migration: set linguistic76 to JournalTier.FOUNDER
// Run once after deploying PR 1 (journals-foundation).
//
// The journal_tier field defaults to "standard" for all users.
// linguistic76 is the pilot account for the full DNWF three-stage workflow.
//
// Usage:
//   Run via Neo4j Browser, Cypher shell, or the MCP neo4j tool.

MATCH (u:User {title: "linguistic76"})
SET u.journal_tier = "founder"
RETURN u.title, u.journal_tier;
