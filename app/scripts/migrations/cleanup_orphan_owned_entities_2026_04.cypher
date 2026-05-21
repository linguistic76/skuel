// Audit: Entities OWNED by soft-deleted users
// =============================================
//
// Finding 9 replaced UserBackend.delete_user's hard DETACH DELETE with a
// soft-delete (status='deleted', is_active=false, PII scrubbed; OWNS edges
// preserved so teachers can still render historical UserEntry submissions).
// Hard-delete moved to POST /api/admin/users/hard-delete and is gated on
// ADMIN role + explicit "confirm":"erase" payload.
//
// Prior to this change, delete_user cascaded via OPTIONAL MATCH through
// :OWNS and DETACH DELETE'd every owned entity. If someone re-triggers a
// stale call site on a live database, this script surfaces:
//
//   1. Users flagged as deleted (soft-deleted via the new path).
//   2. Entities they still OWN (this is EXPECTED under the new model —
//      teacher submissions must survive soft-delete).
//   3. Orphaned OWNS edges pointing at a missing User node (from an older
//      hard delete that left dangling relationships).
//
// READ-ONLY. No MERGE, SET, DELETE. A teacher or admin reviews the output
// and decides whether to run the GDPR erasure endpoint for any specific
// user.
//
// Run:
//   cypher-shell -u neo4j -p <password> \
//     -f scripts/migrations/cleanup_orphan_owned_entities_2026_04.cypher

// ---------- 1. Soft-deleted users and their retained owned entities ----------
MATCH (u:User)
WHERE u.status = 'deleted' OR u.is_active = false
OPTIONAL MATCH (u)-[:OWNS]->(owned:Entity)
WITH u, count(owned) AS owned_count
RETURN 'soft_deleted_users' AS bucket,
       u.uid AS user_uid,
       u.status AS status,
       u.is_active AS is_active,
       u.deleted_at AS deleted_at,
       owned_count
ORDER BY owned_count DESC, deleted_at DESC;

// ---------- 2. OWNS edges pointing at a User node that no longer exists ----
// These are the real orphans — an older hard-delete path left the entity
// without its owner. Normally impossible now (the User.uid MATCH in
// user_backend.hard_delete_user DETACH DELETEs both ends together), but
// worth auditing before ripping out any remaining fallback code.
MATCH (e:Entity)
WHERE e.user_uid IS NOT NULL
  AND NOT EXISTS { MATCH (:User {uid: e.user_uid}) }
RETURN 'orphan_entities' AS bucket,
       e.uid AS entity_uid,
       e.entity_type AS entity_type,
       e.user_uid AS claimed_owner_uid,
       e.title AS title,
       e.created_at AS created_at
ORDER BY created_at DESC
LIMIT 500;
