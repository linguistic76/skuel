// Revert the in-place designation mutation — LIFEPATH_ALIGNMENT_DEBT item 2.
//
// Designation used to promote a LearningPath by flipping its `entity_type` to
// 'life_path' IN PLACE, leaving the `:LearningPath` label untouched. Label and
// discriminator therefore disagreed, and every reader saw a different answer
// depending on which it keyed on — most visibly `LpService`, which built a
// `LearningPath` from the node and tripped that model's honest-leaf-identity
// guard (G6), so the alignment payload named the path "Unknown".
//
// Designation now lives on the `ULTIMATE_PATH` edge alone and touches no node
// property. Nodes promoted by the OLD writer keep the stale discriminator
// forever — nothing reverts them, because nothing sets it any more — so they
// need this one-shot repair.
//
// SAFE TO RE-RUN. Idempotent: the second run matches nothing.
//
// Run:  cat scripts/migrations/revert_designated_life_path_entity_type_2026_08.cypher \
//         | cypher-shell -u neo4j -p "$NEO4J_PASSWORD"

// --- 1. Inspect before changing anything -----------------------------------
// Expect: every row labelled ["Entity","LearningPath"]. A row WITHOUT the
// :LearningPath label is an authored `type: life_path` entity, not a promoted
// path — those are legitimate and must NOT be rewritten by step 2.
MATCH (n:Entity {entity_type: 'life_path'})
RETURN n.uid AS uid, n.title AS title, labels(n) AS labels,
       exists((:User)-[:ULTIMATE_PATH]->(n)) AS is_designated;

// --- 2. Revert ONLY nodes the old writer promoted --------------------------
// Scoped by the :LearningPath label, which the old writer never removed. That
// label is what makes a promoted path distinguishable from an authored
// life_path entity, so it is the correct discriminator here.
MATCH (n:Entity:LearningPath {entity_type: 'life_path'})
SET n.entity_type = 'learning_path'
RETURN count(n) AS reverted;

// --- 3. Verify --------------------------------------------------------------
// Expect reverted = 0 on a re-run, and every designated path reading as a
// well-formed LearningPath.
MATCH (u:User)-[:ULTIMATE_PATH]->(lp:Entity)
RETURN lp.uid AS uid, lp.entity_type AS entity_type, labels(lp) AS labels,
       count(u) AS designating_users
ORDER BY uid;
