// noqa-file: CYP011 - unreachable template; every label/edge below is unregistered vocabulary.
// ensure_constraints() resolves '{entity_label.lower()}_constraints.cypher' and upsert_batch()
// only loads a named template when a caller passes template_name= — no caller does. Nothing
// here can execute. Deletion is tracked in docs/patterns/CYPHER_VOCABULARY_FINDINGS.md.
// Constraints for LifePrinciple entities
CREATE CONSTRAINT lp_uid IF NOT EXISTS
FOR (n:LifePrinciple) REQUIRE n.uid IS UNIQUE;

CREATE CONSTRAINT kd_uid IF NOT EXISTS
FOR (n:KnowledgeDomain) REQUIRE n.uid IS UNIQUE;

CREATE CONSTRAINT ku_uid IF NOT EXISTS
FOR (n:Entity) REQUIRE n.uid IS UNIQUE;

CREATE CONSTRAINT je_uid IF NOT EXISTS
FOR (n:JournalEntry) REQUIRE n.uid IS UNIQUE;