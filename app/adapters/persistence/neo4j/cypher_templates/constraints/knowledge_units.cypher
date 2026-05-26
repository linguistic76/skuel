// Constraints for KnowledgeUnit entities and KnowledgeDomain taxonomy
CREATE CONSTRAINT ku_uid IF NOT EXISTS
FOR (n:Entity) REQUIRE n.uid IS UNIQUE;

CREATE CONSTRAINT kd_uid IF NOT EXISTS
FOR (n:KnowledgeDomain) REQUIRE n.uid IS UNIQUE;