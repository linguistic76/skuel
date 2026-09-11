// Migration: Collapse persisted priority 'critical' to 'high' (2026-09)
// =====================================================================
// Ruling: Priority has exactly three levels — low / medium / high
//   (docs/roadmap/calendar-priority-lens-arc.md, ruling 1; amends ADR-045).
//   The enum member Priority.CRITICAL is deleted in the code PR that follows
//   this migration (arc B1). This file runs FIRST: Priority(task.priority) is
//   constructed directly on every calendar and Today read, so a deleted member
//   with 'critical' rows still persisted would raise on those pages. 'high' is
//   a member under both vocabularies, so converging the rows first is safe in
//   either order of deploys.
//
// Scope: two carriers of the property.
//   1. :Entity nodes — priority lives on UserOwnedEntity (the six Activity
//      domains, LifePath, reports, entries) and is authored on PathStep
//      frontmatter. Anchoring on :Entity is load-bearing: no non-Entity label
//      carries a `priority` property in SKUEL's vocabulary (Insight has
//      `impact`, AuthEvent has `event_type`), and the census below proves it
//      before anything is written.
//   2. Lateral relationships — the lateral add-modal persists `priority` on the
//      edge (lateral_route_factory → SET r += $properties) and skuel.js reads
//      it back for edge width. Anchored on the lateral type set
//      (core/models/relationship_names.py `_LATERAL_TYPES`).
//
// Idempotent and re-runnable: a row already at 'high' does not match either
//   WHERE. Run it TWICE around the code cutover — once before the enum member
//   is deleted (so no read raises while the old code still runs) and once
//   again right after the deleting code is deployed: until that deploy, the
//   old enum still accepts 'critical' on every activity write, so a row
//   written between the first run and the cutover would escape it. The second
//   run is the write cutoff; its verify below must return no 'critical' row.
//
// Verify (before/after each run):
//   MATCH (n) WHERE n.priority IS NOT NULL
//   RETURN labels(n) AS labels, toString(n.priority) AS value, count(*) AS n
//   ORDER BY labels, value
//   MATCH ()-[r]->() WHERE r.priority IS NOT NULL
//   RETURN type(r) AS type, toString(r.priority) AS value, count(*) AS n
//   ORDER BY type, value
//   -- After: no `value` reads 'critical' on either side.

// Statement 1: Entity nodes.
MATCH (n:Entity)
WHERE n.priority = 'critical'
SET n.priority = 'high';

// Statement 2: lateral relationships (the one edge family that persists priority).
MATCH ()-[r]->()
WHERE type(r) IN ['SIBLING', 'COUSIN', 'AUNT_UNCLE', 'NIECE_NEPHEW', 'BLOCKS', 'BLOCKED_BY',
                  'PREREQUISITE_FOR', 'REQUIRES_PREREQUISITE', 'LATERAL_ENABLES',
                  'LATERAL_ENABLED_BY', 'RELATED_TO', 'SIMILAR_TO', 'COMPLEMENTARY_TO',
                  'CONFLICTS_WITH', 'ALTERNATIVE_TO', 'RECOMMENDED_WITH', 'STACKS_WITH']
  AND r.priority = 'critical'
SET r.priority = 'high';
