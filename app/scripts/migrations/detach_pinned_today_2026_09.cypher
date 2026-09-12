// Detach every persisted PINNED_TODAY edge (one-shot, 2026-09 — day-view arc D.1).
//
// The Today surface's star/pin (user)-[:PINNED_TODAY {pinned_at}]->(entity) died
// with the client-rendered Today page: the day view renders per-domain lists
// through the domain cards and carries no pin. The RelationshipName member, the
// UserRelationshipOperations methods and the backend writers are deleted, so
// nothing can read or write these edges again — the rows are dead weight on the
// AuraDB node/relationship budget.
//
// Idempotent: a second run matches zero edges. Run against the live graph once
// the code that named the edge is deployed (the edge type is not in the enum any
// more, so it is spelled here as a literal by design).
MATCH ()-[r:PINNED_TODAY]->()
DELETE r
RETURN count(r) AS detached;
