// Constraints for LifePrinciple entities
CREATE CONSTRAINT lp_uid IF NOT EXISTS
FOR (n:LifePrinciple) REQUIRE n.uid IS UNIQUE;

CREATE CONSTRAINT kd_uid IF NOT EXISTS
FOR (n:KnowledgeDomain) REQUIRE n.uid IS UNIQUE;

CREATE CONSTRAINT ku_uid IF NOT EXISTS
FOR (n:Entity) REQUIRE n.uid IS UNIQUE;

CREATE CONSTRAINT je_uid IF NOT EXISTS
FOR (n:JournalEntry) REQUIRE n.uid IS UNIQUE;