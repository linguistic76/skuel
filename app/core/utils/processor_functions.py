"""
Processor Functions for Neo4j Result Processing
================================================

Named processor functions to replace lambda expressions in graph query result processing.
Following clean code principle: no lambdas, only named functions.

These functions transform Neo4j query results (list of records) into Python data structures.
Used extensively by GraphQueryExecutor and relationship services.
"""

from typing import Any


def extract_field_list(field: str):
    """
    Create processor that extracts a specific field from records into a list.

    Generic version of extract_uids_list - works with any field name.
    Returns a processor function that extracts the specified field from each record.

    Example:
        result = await executor.execute(
            query='MATCH (p:Lp)-[:HAS_STEP]->(s:Ls) RETURN p.uid as path_uid',
            processor=extract_field_list("path_uid")
        )

    Args:
        field: Name of the field to extract from each record

    Returns:
        Processor function that extracts field into list
    """

    def processor(records: list[dict[str, Any]]) -> list[Any]:
        """Extract specific field from all records into list."""
        return [record[field] for record in records]

    return processor


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


def extract_uids_set_filtered(records: list[dict[str, Any]]) -> set[str]:
    """
    Extract non-null UIDs from Neo4j records into a set.

    Use when optional relationships might return None UIDs.
    Filters out None/null values before creating set.

    Example:
        result = await executor.execute(
            query='MATCH (n) OPTIONAL MATCH (n)-[:REL]->(m) RETURN m.uid as uid',
            processor=extract_uids_set_filtered
        )

    Args:
        records: Neo4j query results (list of dicts with 'uid' key that may be None)

    Returns:
        Set of unique UID strings (None values filtered out)
    """
    return {record["uid"] for record in records if record["uid"]}


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


def extract_single_value(field: str, default: Any = None):
    """
    Create processor that extracts a single field value from first record.

    Generic version of extract_single_int - works with any value type.
    Returns the specified field from the first record, or default if no records.

    Example:
        result = await executor.execute(
            query='MATCH (n {uid: $uid}) RETURN n.title as title',
            processor=extract_single_value("title", "Untitled")
        )

    Args:
        field: Name of the field to extract from record
        default: Value to return if no records (default: None)

    Returns:
        Processor function that extracts single field value
    """

    def processor(records: list[dict[str, Any]]) -> Any:
        """Extract single field value from first record."""
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


def extract_dict_from_records(key_field: str, value_field: str):
    """
    Create processor that builds a dictionary from record fields.

    Returns a processor function that transforms records into a dict.
    Each record provides one key-value pair.

    Example:
        result = await executor.execute(
            query='MATCH (n)-[:REL]->(m) RETURN m.domain as domain, count(*) as count',
            processor=extract_dict_from_records("domain", "count")
        )
        # Returns: {"TECH": 5, "BUSINESS": 3, "PERSONAL": 7}

    Args:
        key_field: Name of the field to use as dict keys
        value_field: Name of the field to use as dict values

    Returns:
        Processor function that builds dict from records
    """

    def processor(records: list[dict[str, Any]]) -> dict[str, Any]:
        """Build dictionary from record fields."""
        return {record[key_field]: record[value_field] for record in records}

    return processor


def extract_dict_from_first_record(field_mapping: dict[str, str], default: int = 0):
    """
    Create processor that extracts multiple fields from first record into a dict.

    Returns a processor function that builds a dict from the first record.
    Use for aggregate queries that return multiple count/summary fields.

    Example:
        result = await executor.execute(
            query='''
                MATCH (journal:Journal)
                OPTIONAL MATCH (journal)-[:RELATED_TO]->(related)
                OPTIONAL MATCH (journal)-[:SUPPORTS_GOAL]->(goal)
                RETURN count(DISTINCT related) as related_count,
                       count(DISTINCT goal) as goal_count
            ''',
            processor=extract_dict_from_first_record({
                "related_journal_count": "related_count",
                "supported_goal_count": "goal_count"
            })
        )
        # Returns: {"related_journal_count": 5, "supported_goal_count": 3}

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

# Total/aggregate queries
extract_total = extract_single_int("total", 0)
"""Extract 'total' field from first record (default: 0)."""

# Deleted counts
extract_deleted_count = extract_single_int("deleted_count", 0)
"""Extract 'deleted_count' field from first record (default: 0)."""


# ============================================================================
# Migration Guide from Lambda to Named Functions
# ============================================================================
"""
Common Lambda → Named Function Migrations:

1. Extract UIDs to list:
   BEFORE: Inline list comprehension with record["uid"]
   AFTER:  processor=extract_uids_list

2. Extract UIDs to set:
   BEFORE: Inline set comprehension with record["uid"]
   AFTER:  processor=extract_uids_set

3. Extract count:
   BEFORE: Conditional expression accessing records[0]["count"]
   AFTER:  processor=extract_count

4. Extract created count:
   BEFORE: Conditional expression accessing records[0]["created"]
   AFTER:  processor=extract_created_count

5. Check existence:
   BEFORE: Length comparison expression
   AFTER:  processor=check_exists

6. Extract domain counts:
   BEFORE: Dict comprehension with domain and count fields
   AFTER:  processor=extract_dict_from_records("domain", "count")

7. Extract filtered UIDs:
   BEFORE: Set comprehension with conditional filter on uid
   AFTER:  processor=extract_uids_set_filtered

8. Extract custom field:
   BEFORE: Conditional expression accessing records[0][field_name]
   AFTER:  processor=extract_single_value("field_name", default_value)

9. Extract multiple fields from first record:
   BEFORE: Dict with conditional expressions for each field
   AFTER:  processor=extract_dict_from_first_record({
               "related_journal_count": "related_count",
               "supported_goal_count": "goal_count"
           })
"""
