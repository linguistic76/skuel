"""
Processor Functions for Neo4j Result Processing
================================================

Named processors, passed as ``processor=`` to ``Neo4jQueryExecutor.execute``. Each turns
Neo4j query results (a list of records) into a Python data structure. No lambdas.

CONTRACT — processors return RAW values, never ``Result``:
    ``Neo4jQueryExecutor.execute(...)`` calls ``Result.ok(processor(records))``,
    i.e. it wraps the processor's return value itself. A processor that returns a
    ``Result`` therefore produces ``Result[Result[T]]`` — a double-wrap. The inner
    failure then hides inside an outer ``ok``, so callers checking ``.is_error``
    never see it (e.g. a ``not_found`` silently read as success). To gate on
    emptiness, return a raw ``bool`` (see ``check_exists``) and apply the
    ``Result.fail(...)`` guard in the calling method, NOT in the processor.
    See: /docs/patterns/ERROR_HANDLING.md (Result anti-patterns).
"""

from typing import Any


def extract_uids_list(records: list[dict[str, Any]]) -> list[str]:
    """
    Extract UIDs from Neo4j records into a list.

    Most common processor pattern - extracts 'uid' field from each record.
    Used for relationship traversal queries that return related entity UIDs.

    Example:
        result = await executor.execute(
            query='MATCH (n)-[:REL]->(m) RETURN m.uid as uid',
            processor=extract_uids_list
        )

    Args:
        records: Neo4j query results (list of dicts with 'uid' key)

    Returns:
        List of UID strings in query result order
    """
    return [record["uid"] for record in records]


def extract_uids_set(records: list[dict[str, Any]]) -> set[str]:
    """
    Extract UIDs from Neo4j records into a set.

    Use when order doesn't matter and duplicates should be removed.
    Slightly more efficient than list for membership testing.

    Example:
        result = await executor.execute(
            query='MATCH (n)-[:REL*]-(m) RETURN m.uid as uid',
            processor=extract_uids_set
        )

    Args:
        records: Neo4j query results (list of dicts with 'uid' key)

    Returns:
        Set of unique UID strings
    """
    return {record["uid"] for record in records}


def extract_single_int(field: str, default: int = 0):
    """
    Create processor that extracts a single integer field from first record.

    Returns a processor function that gets one field value from the first record.
    If no records exist, returns default value.

    Common use cases:
    - COUNT queries: extract_single_int("count")
    - Total calculations: extract_single_int("total")
    - Relationship counts: extract_single_int("created")

    Example:
        result = await executor.execute(
            query='MATCH (n)-[:REL]->(m) RETURN count(m) as count',
            processor=extract_single_int("count")
        )

    Args:
        field: Name of the field to extract from record
        default: Value to return if no records (default: 0)

    Returns:
        Processor function that extracts single int value
    """

    def processor(records: list[dict[str, Any]]) -> int:
        """Extract single int field from first record."""
        return records[0][field] if records else default

    return processor


def check_exists(records: list[dict[str, Any]]) -> bool:
    """
    Check if any records exist.

    Simple existence check - returns True if query returned any results.
    Used for existence queries (e.g., "does this relationship exist?").

    Example:
        result = await executor.execute(
            query='MATCH (n {uid: $uid})-[:REL]->(m) RETURN m',
            processor=check_exists
        )

    Args:
        records: Neo4j query results

    Returns:
        True if at least one record exists, False otherwise
    """
    return len(records) > 0


def extract_dict_from_first_record(field_mapping: dict[str, str], default: int = 0):
    """
    Create processor that extracts multiple fields from first record into a dict.

    Returns a processor function that builds a dict from the first record.
    Use for aggregate queries that return multiple count/summary fields.

    Example:
        result = await executor.execute(
            query='''
                MATCH (user:User {uid: $user_uid})
                OPTIONAL MATCH (user)-[:FOLLOWS]->(following)
                OPTIONAL MATCH (follower)-[:FOLLOWS]->(user)
                RETURN count(DISTINCT following) as following_count,
                       count(DISTINCT follower) as follower_count
            ''',
            processor=extract_dict_from_first_record({
                "following": "following_count",
                "followers": "follower_count"
            })
        )
        # Returns: {"following": 5, "followers": 3}

    Args:
        field_mapping: Dict mapping output keys to record field names
        default: Value to use when no records or field is missing (default: 0)

    Returns:
        Processor function that builds dict from first record
    """

    def processor(records: list[dict[str, Any]]) -> dict[str, Any]:
        """Extract multiple fields from first record into dict."""
        if not records:
            return {output_key: default for output_key in field_mapping}

        record = records[0]
        return {
            output_key: record.get(record_field, default)
            for output_key, record_field in field_mapping.items()
        }

    return processor


# ============================================================================
# Convenience Aliases for Common Use Cases
# ============================================================================

# Count queries
extract_count = extract_single_int("count", 0)
"""Extract 'count' field from first record (default: 0)."""

# Relationship creation counts
extract_created_count = extract_single_int("created", 0)
"""Extract 'created' relationship count from first record (default: 0)."""
