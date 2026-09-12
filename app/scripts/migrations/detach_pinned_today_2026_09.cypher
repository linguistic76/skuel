// Detach every PINNED_TODAY edge (one-shot, 2026-09).
//
// No code reads or writes (user)-[:PINNED_TODAY {pinned_at}]->(entity): the edge
// type has no RelationshipName member and no writer, so any persisted rows are
// dead weight on the AuraDB node/relationship budget. The type is spelled here
// as a literal by design — the enum does not name it. Idempotent: a second run
// matches zero edges. Run against the live graph after the code that retired
// the edge is deployed. Record: docs/decisions/ADR-058-today-surface.md
// § Amendment (2026-09-12).
MATCH ()-[r:PINNED_TODAY]->()
DELETE r
RETURN count(r) AS detached;
