"""
Pure Cypher Schema DDL - Native Neo4j Data Definition Language
==============================================================

This module provides Pure Cypher DDL for schema operations using native Neo4j syntax.
No APOC dependency - works on ALL Neo4j installations (Desktop, Aura, Docker, self-hosted).

**Philosophy:** "Use native Neo4j capabilities - they're more powerful than APOC"

Neo4j 4.0+ provides complete DDL for:
- Indexes (RANGE, FULLTEXT, VECTOR, TEXT)
- Constraints (UNIQUE, NODE KEY, NOT NULL, RELATIONSHIP constraints)
- Idempotent operations (IF NOT EXISTS clause)

**Benefits over APOC:**
- More index types and options
- Better performance (native implementation)
- Idempotent by default (IF NOT EXISTS)
- Works on ALL Neo4j installations
- Future-proof (native Neo4j feature)
"""


def build_create_index_ddl(
    name: str, labels: list[str], properties: list[str], index_type: str = "RANGE"
) -> str:
    """
    Build Pure Cypher DDL to create an index.

    Args:
        name: Index name
        labels: Node label(s) to index
        properties: Property name(s) to index
        index_type: Type of index (RANGE, FULLTEXT, VECTOR, TEXT, POINT)

    Returns:
        Pure Cypher CREATE INDEX statement

    Examples:
        # Range index (default - fast property lookups)
        >>> build_create_index_ddl("task_priority_idx", ["Task"], ["priority"])
        "CREATE RANGE INDEX task_priority_idx IF NOT EXISTS FOR (n:Task) ON (n.priority)"

        # Composite index (multiple properties)
        >>> build_create_index_ddl("task_composite_idx", ["Task"], ["user_uid", "status"])
        "CREATE RANGE INDEX task_composite_idx IF NOT EXISTS FOR (n:Task) ON (n.user_uid, n.status)"

        # Fulltext index (text search)
        >>> build_create_index_ddl(
        ...     "ku_search_idx", ["Ku"], ["title", "content"], "FULLTEXT"
        ... )
        "CREATE FULLTEXT INDEX ku_search_idx IF NOT EXISTS FOR (n:Ku) ON EACH [n.title, n.content]"
    """
    label = labels[0] if labels else "Node"

    if index_type.upper() == "FULLTEXT":
        # Fulltext index for text search (supports multiple properties)
        props_list = ", ".join([f"n.{prop}" for prop in properties])
        return f"""
CREATE FULLTEXT INDEX {name} IF NOT EXISTS
FOR (n:{label})
ON EACH [{props_list}]
        """.strip()

    elif index_type.upper() == "VECTOR":
        # Vector index for semantic search (single property)
        prop = properties[0] if properties else "embedding"
        return f"""
CREATE VECTOR INDEX {name} IF NOT EXISTS
FOR (n:{label})
ON (n.{prop})
OPTIONS {{
  indexConfig: {{
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }}
}}
        """.strip()

    else:  # RANGE (default), TEXT, or POINT
        # Standard property index (supports composite indexes)
        props_str = ", ".join([f"n.{prop}" for prop in properties])
        index_kind = (
            index_type.upper() if index_type.upper() in ["RANGE", "TEXT", "POINT"] else "RANGE"
        )
        return f"""
CREATE {index_kind} INDEX {name} IF NOT EXISTS
FOR (n:{label})
ON ({props_str})
        """.strip()


def build_create_constraint_ddl(
    name: str, labels: list[str], properties: list[str], constraint_type: str = "UNIQUE"
) -> str:
    """
    Build Pure Cypher DDL to create a constraint.

    Args:
        name: Constraint name
        labels: Node label(s)
        properties: Property name(s)
        constraint_type: Type of constraint (UNIQUE, NODE_KEY, NOT_NULL, RELATIONSHIP_UNIQUE)

    Returns:
        Pure Cypher CREATE CONSTRAINT statement

    Examples:
        # Unique constraint (single property)
        >>> build_create_constraint_ddl("task_uid_unique", ["Task"], ["uid"])
        "CREATE CONSTRAINT task_uid_unique IF NOT EXISTS FOR (n:Task) REQUIRE n.uid IS UNIQUE"

        # Node key constraint (composite uniqueness + existence)
        >>> build_create_constraint_ddl(
        ...     "task_key", ["Task"], ["user_uid", "uid"], "NODE_KEY"
        ... )
        "CREATE CONSTRAINT task_key IF NOT EXISTS FOR (n:Task) REQUIRE (n.user_uid, n.uid) IS NODE KEY"

        # Not null constraint
        >>> build_create_constraint_ddl(
        ...     "task_title_required", ["Task"], ["title"], "NOT_NULL"
        ... )
        "CREATE CONSTRAINT task_title_required IF NOT EXISTS FOR (n:Task) REQUIRE n.title IS NOT NULL"
    """
    label = labels[0] if labels else "Node"

    if constraint_type.upper() == "NODE_KEY":
        # Node key constraint (composite uniqueness + all properties must exist)
        props_str = ", ".join([f"n.{prop}" for prop in properties])
        return f"""
CREATE CONSTRAINT {name} IF NOT EXISTS
FOR (n:{label})
REQUIRE ({props_str}) IS NODE KEY
        """.strip()

    elif constraint_type.upper() == "NOT_NULL" or constraint_type.upper() == "EXISTS":
        # Not null constraint (property must exist)
        prop = properties[0] if properties else "id"
        return f"""
CREATE CONSTRAINT {name} IF NOT EXISTS
FOR (n:{label})
REQUIRE n.{prop} IS NOT NULL
        """.strip()

    elif constraint_type.upper() == "RELATIONSHIP_UNIQUE":
        # Unique constraint on relationships
        prop = properties[0] if properties else "id"
        rel_type = label  # For relationships, label parameter is the relationship type
        return f"""
CREATE CONSTRAINT {name} IF NOT EXISTS
FOR ()-[r:{rel_type}]-()
REQUIRE r.{prop} IS UNIQUE
        """.strip()

    else:  # UNIQUE (default)
        # Unique constraint (single or composite)
        if len(properties) == 1:
            prop = properties[0]
            return f"""
CREATE CONSTRAINT {name} IF NOT EXISTS
FOR (n:{label})
REQUIRE n.{prop} IS UNIQUE
            """.strip()
        else:
            # Composite unique constraint
            props_str = ", ".join([f"n.{prop}" for prop in properties])
            return f"""
CREATE CONSTRAINT {name} IF NOT EXISTS
FOR (n:{label})
REQUIRE ({props_str}) IS UNIQUE
            """.strip()


def build_drop_index_ddl(name: str) -> str:
    """
    Build Pure Cypher DDL to drop an index.

    Args:
        name: Index name to drop

    Returns:
        Pure Cypher DROP INDEX statement

    Example:
        >>> build_drop_index_ddl("old_index")
        "DROP INDEX old_index IF EXISTS"
    """
    return f"DROP INDEX {name} IF EXISTS"


def build_drop_constraint_ddl(name: str) -> str:
    """
    Build Pure Cypher DDL to drop a constraint.

    Args:
        name: Constraint name to drop

    Returns:
        Pure Cypher DROP CONSTRAINT statement

    Example:
        >>> build_drop_constraint_ddl("old_constraint")
        "DROP CONSTRAINT old_constraint IF EXISTS"
    """
    return f"DROP CONSTRAINT {name} IF EXISTS"


__all__ = [
    "build_create_constraint_ddl",
    "build_create_index_ddl",
    "build_drop_constraint_ddl",
    "build_drop_index_ddl",
]
