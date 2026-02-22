// Migration: Add RANGE index on Ku.ku_type
// Date: 2026-02-22
// Reason: Every backend query filters on ku_type via default_filters.
//         Without this index, queries scan all Ku nodes.
//
// Run: cat scripts/migrations/add_ku_type_index.cypher | cypher-shell -u neo4j -p <password>
// Verify: SHOW INDEXES YIELD name, labelsOrTypes, properties WHERE name = 'ku_type_idx'

CREATE RANGE INDEX ku_type_idx IF NOT EXISTS FOR (n:Ku) ON (n.ku_type);
