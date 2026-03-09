"""
Hybrid Query Builder - Optimized Property + Graph Pattern Queries
==================================================================

**Core Principle:** "Filter by properties FIRST, then traverse graph"

This module provides utilities for building optimized Neo4j queries that combine:
1. Property filters (fast indexed lookups)
2. Graph patterns (relationship traversal)

**The Optimization Pattern:**
```cypher
// ✅ EFFICIENT - Filter first, then traverse
MATCH (ku:Entity)
WHERE ku.sel_category = 'self_awareness' -- Fast indexed property filter
  AND ku.learning_level = 'beginner' -- Fast indexed property filter
WITH ku
WHERE EXISTS { -- Graph traversal on filtered set
  MATCH (user)-[:MASTERED]->()-[:ENABLES_KNOWLEDGE]->(ku)
}
RETURN ku

// ❌ INEFFICIENT - Traverse first, then filter
MATCH (ku:Entity)
WHERE EXISTS { -- Graph traversal on ALL nodes
  MATCH (user)-[:MASTERED]->()-[:ENABLES_KNOWLEDGE]->(ku)
}
WITH ku
WHERE ku.sel_category = 'self_awareness' -- Filter after traversal
RETURN ku
```

**Why This Matters:**
- Property filters use indexes (O(log n) lookup)
- Graph traversal is O(edges) per node
- Filter first = traverse fewer nodes = faster query

**Created:** November 15, 2025
**Status:** Strategic Enhancement
"""

from typing import Any


class HybridQueryBuilder:
    """
    Build optimized hybrid queries combining property filters and graph patterns.

    **Query Structure:**
    1. MATCH clause with node labels
    2. WHERE clause with property filters (uses indexes)
    3. WITH clause to pass filtered results
    4. WHERE clause with graph patterns (traversal on smaller set)
    5. RETURN clause with results

    **Example:**
    ```python
    builder = HybridQueryBuilder()
    query, params = builder.build_hybrid_knowledge_query(
        property_filters={
            "sel_category": "self_awareness",
            "learning_level": "beginner",
        },
        graph_patterns={
            "ready_to_learn": "NOT EXISTS { MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq) ... }",
            "supports_goals": "EXISTS { MATCH (user)-[:PURSUING_GOAL]->(goal)-[:REQUIRES_KNOWLEDGE]->(ku) }",
        },
        user_uid="user.mike",
        QueryLimit.SMALL,
    )
    ```
    """

    @staticmethod
    def build_hybrid_knowledge_query(
        property_filters: dict[str, Any],
        graph_patterns: dict[str, str],
        user_uid: str,
        limit: int = 20,
        offset: int = 0,
        query_text: str | None = None,
        include_context: bool = True,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build optimized hybrid query for knowledge search.

        **Optimization Strategy:**
        1. Property filters narrow candidates (indexed)
        2. Text search on filtered set (if provided)
        3. Graph patterns on smaller set (relationship traversal)
        4. Optional context enrichment (prerequisites, etc.)

        Args:
            property_filters: Property-based filters (sel_category, learning_level, etc.)
            graph_patterns: Graph patterns from SearchRequest.to_graph_patterns()
            user_uid: User identifier for personalized patterns
            limit: Maximum results
            offset: Pagination offset
            query_text: Optional text search
            include_context: Include relationship context (prerequisites, enables, goals)

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            ```python
            query, params = HybridQueryBuilder.build_hybrid_knowledge_query(
                property_filters={
                    "sel_category": "self_awareness",
                    "learning_level": "beginner",
                },
                graph_patterns={
                    "ready_to_learn": "NOT EXISTS { ... }",
                    "supports_goals": "EXISTS { ... }",
                },
                user_uid="user.mike",
                QueryLimit.SMALL,
            )
            ```
        """
        # Start with MATCH clause
        cypher_parts = ["MATCH (ku:Entity)"]

        # Build parameters dict
        params: dict[str, Any] = {
            "user_uid": user_uid,
            "limit": limit,
            "offset": offset,
        }

        # Property Filters (FAST - uses indexes)
        property_conditions = []

        for key, value in property_filters.items():
            param_name = f"prop_{key}"
            property_conditions.append(f"ku.{key} = ${param_name}")
            params[param_name] = value

        # Add text search to property filters (indexed)
        if query_text:
            property_conditions.append(
                "(ku.title CONTAINS $query_text OR ku.summary CONTAINS $query_text)"
            )
            params["query_text"] = query_text

        # Add property WHERE clause if we have filters
        if property_conditions:
            cypher_parts.append("WHERE " + " AND ".join(property_conditions))

        # WITH clause to pass filtered results
        # This is KEY for optimization - graph patterns operate on filtered set
        if graph_patterns:
            cypher_parts.append("WITH ku")

        # Graph Patterns (operates on filtered candidates)
        if graph_patterns:
            # Each pattern is a complete WHERE condition
            graph_conditions = [f"({pattern_cypher})" for pattern_cypher in graph_patterns.values()]

            if graph_conditions:
                cypher_parts.append("WHERE " + " AND ".join(graph_conditions))

        # Context Enrichment (optional)
        if include_context:
            cypher_parts.extend(
                [
                    "",
                    "// Fetch relationship context for each result",
                    "OPTIONAL MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)",
                    "OPTIONAL MATCH (user:User {uid: $user_uid})-[mastery:MASTERED]->(prereq)",
                    "OPTIONAL MATCH (ku)-[:ENABLES_LEARNING]->(next:Entity)",
                    "OPTIONAL MATCH (user)-[:PURSUING_GOAL]->(goal:Goal)-[:REQUIRES_KNOWLEDGE]->(ku)",
                    "WHERE goal.status IN ['active', 'in_progress']",
                    "",
                    "WITH ku,",
                    "     collect(DISTINCT {uid: prereq.uid, title: prereq.title, mastered: mastery IS NOT NULL}) as prerequisites,",
                    "     collect(DISTINCT {uid: next.uid, title: next.title}) as enables,",
                    "     collect(DISTINCT {uid: goal.uid, title: goal.title}) as supporting_goals",
                ]
            )

            # Return with context
            cypher_parts.extend(
                [
                    "",
                    "RETURN ku,",
                    "       prerequisites,",
                    "       enables,",
                    "       supporting_goals,",
                    "       size(supporting_goals) as goal_count",
                    "ORDER BY goal_count DESC, ku.created_at DESC",
                ]
            )
        else:
            # Simple return
            cypher_parts.extend(["", "RETURN ku", "ORDER BY ku.created_at DESC"])

        # Add pagination
        cypher_parts.extend(["SKIP $offset", "LIMIT $limit"])

        # Join into final query
        cypher = "\n".join(cypher_parts)

        return cypher, params

    @staticmethod
    def build_hybrid_multi_domain_query(
        domains: list[str],
        property_filters: dict[str, Any],
        graph_patterns: dict[str, str],
        user_uid: str,
        limit: int = 20,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build hybrid query across multiple domains.

        **Use Case:** Search across Knowledge, Tasks, Habits, etc. with unified filters

        Args:
            domains: List of domain labels (e.g., ["Entity", "Task", "Habit"])
            property_filters: Shared property filters
            graph_patterns: Domain-agnostic graph patterns
            user_uid: User identifier
            limit: Maximum results per domain

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            ```python
            query, params = HybridQueryBuilder.build_hybrid_multi_domain_query(
                domains=["Entity", "Task", "Event"],
                property_filters={"status": "active"},
                graph_patterns={"user_owned": "EXISTS { MATCH (user)-[:OWNS]->(item) }"},
                user_uid="user.mike",
            )
            ```
        """
        # Build UNION query for each domain
        union_parts = []

        params: dict[str, Any] = {"user_uid": user_uid, "limit": limit}

        for domain in domains:
            # Build property conditions
            property_conditions = []
            for key, value in property_filters.items():
                param_name = f"{domain.lower()}_{key}"
                property_conditions.append(f"item.{key} = ${param_name}")
                params[param_name] = value

            # Build domain-specific query
            domain_query = f"MATCH (item:{domain})"

            if property_conditions:
                domain_query += "\nWHERE " + " AND ".join(property_conditions)

            # Add WITH for graph patterns
            if graph_patterns:
                domain_query += "\nWITH item"
                graph_conditions = [f"({p})" for p in graph_patterns.values()]
                domain_query += "\nWHERE " + " AND ".join(graph_conditions)

            domain_query += f"\nRETURN item, '{domain}' as domain_type"
            domain_query += "\nLIMIT $limit"

            union_parts.append(domain_query)

        # Join with UNION
        cypher = "\nUNION ALL\n".join(union_parts)
        cypher += "\nORDER BY item.created_at DESC"

        return cypher, params

    @staticmethod
    def build_optimized_prerequisite_chain(
        knowledge_uid: str,
        user_uid: str,
        property_filters: dict[str, Any] | None = None,
        max_depth: int = 5,
        only_unmastered: bool = True,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build optimized query for prerequisite chains with property filtering.

        **Optimization:**
        1. Start from specific knowledge unit (indexed lookup)
        2. Filter prerequisites by properties (if provided)
        3. Check mastery status via graph pattern

        Args:
            knowledge_uid: Starting knowledge unit UID
            user_uid: User identifier
            property_filters: Optional filters for prerequisites
            max_depth: Maximum prerequisite depth
            only_unmastered: Only return unmastered prerequisites

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            ```python
            # Find beginner-level unmastered prerequisites
            query, params = HybridQueryBuilder.build_optimized_prerequisite_chain(
                knowledge_uid="ku.advanced_python",
                user_uid="user.mike",
                property_filters={"learning_level": "beginner"},
                only_unmastered=True,
            )
            ```
        """
        params = {
            "knowledge_uid": knowledge_uid,
            "user_uid": user_uid,
            "max_depth": max_depth,
        }

        # Start with knowledge unit
        cypher = """
        // Find starting knowledge unit
        MATCH (end:Entity {uid: $knowledge_uid})

        // Traverse prerequisite chain
        MATCH path = (end)<-[:REQUIRES_KNOWLEDGE*1..${max_depth}]-(start:Entity)
        """

        # Add property filters for prerequisites
        if property_filters:
            conditions = []
            for key, value in property_filters.items():
                param_name = f"prereq_{key}"
                conditions.append(f"start.{key} = ${param_name}")
                params[param_name] = value

            cypher += "\nWHERE " + " AND ".join(conditions)

        # Add mastery check
        if only_unmastered:
            if property_filters:
                cypher += "\n  AND NOT EXISTS {"
            else:
                cypher += "\nWHERE NOT EXISTS {"

            cypher += """
                MATCH (user:User {uid: $user_uid})-[:MASTERED]->(start)
            }
            """

        # Return with path details
        cypher += """

        RETURN
            start.uid as uid,
            start.title as title,
            length(path) as depth
        ORDER BY depth ASC
        """

        return cypher.replace("${max_depth}", str(max_depth)), params


# ============================================================================
# QUERY OPTIMIZATION PATTERNS
# ============================================================================


class QueryOptimizationPatterns:
    """
    Common query optimization patterns for Neo4j hybrid queries.

    These patterns demonstrate best practices for combining property filters
    and graph patterns for optimal performance.
    """

    @staticmethod
    def example_efficient_ready_to_learn() -> str:
        """
        Example of efficient 'ready to learn' query.

        **Pattern:** Filter by properties, then check prerequisites via graph
        """
        return """
        // ✅ EFFICIENT PATTERN
        MATCH (ku:Entity)
        WHERE ku.sel_category = $category -- Indexed property filter
          AND ku.learning_level = $level -- Indexed property filter
        WITH ku
        WHERE NOT EXISTS { -- Graph pattern on filtered set
            MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
            WHERE NOT EXISTS {
                MATCH (user:User {uid: $user_uid})-[:MASTERED]->(prereq)
            }
        }
        AND NOT EXISTS { -- Additional graph pattern
            MATCH (user:User {uid: $user_uid})-[:MASTERED]->(ku)
        }
        RETURN ku
        LIMIT 10
        """

    @staticmethod
    def example_inefficient_ready_to_learn() -> str:
        """
        Example of INEFFICIENT 'ready to learn' query (anti-pattern).

        **Anti-Pattern:** Check prerequisites first, then filter by properties
        """
        return """
        // ❌ INEFFICIENT ANTI-PATTERN
        MATCH (ku:Entity)
        WHERE NOT EXISTS { -- Graph traversal on ALL nodes
            MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq:Entity)
            WHERE NOT EXISTS {
                MATCH (user:User {uid: $user_uid})-[:MASTERED]->(prereq)
            }
        }
        WITH ku
        WHERE ku.sel_category = $category -- Filter after traversal
          AND ku.learning_level = $level -- Filter after traversal
        RETURN ku
        LIMIT 10
        """

    @staticmethod
    def example_efficient_goal_aligned() -> str:
        """
        Example of efficient goal-aligned knowledge query.

        **Pattern:** Filter goals by status, then find knowledge via graph
        """
        return """
        // ✅ EFFICIENT PATTERN
        MATCH (user:User {uid: $user_uid})-[:PURSUING_GOAL]->(goal:Goal)
        WHERE goal.status IN ['active', 'in_progress'] -- Filter goals first
        WITH user, collect(goal) as active_goals

        MATCH (goal)-[:REQUIRES_KNOWLEDGE]->(ku:Entity)
        WHERE goal IN active_goals
          AND ku.learning_level = $level -- Property filter
          AND NOT EXISTS { -- Graph pattern
            MATCH (user)-[:MASTERED]->(ku)
          }
        RETURN ku, collect(goal) as supporting_goals
        """

    @staticmethod
    def example_efficient_multi_pattern() -> str:
        """
        Example combining multiple property filters and graph patterns.

        **Pattern:** Staged filtering - properties first, then multiple graph patterns
        """
        return """
        // ✅ EFFICIENT MULTI-PATTERN
        MATCH (ku:Entity)
        WHERE ku.sel_category = $category -- Property filter (indexed)
          AND ku.learning_level = $level -- Property filter (indexed)
          AND ku.content_type = $content_type -- Property filter (indexed)
        WITH ku

        // Now apply graph patterns on filtered set
        WHERE NOT EXISTS { -- Pattern 1: Prerequisites met
            MATCH (ku)-[:REQUIRES_KNOWLEDGE]->(prereq)
            WHERE NOT EXISTS {
                MATCH (user:User {uid: $user_uid})-[:MASTERED]->(prereq)
            }
        }
        AND EXISTS { -- Pattern 2: Enabled by mastered
            MATCH (user:User {uid: $user_uid})-[:MASTERED]->(m)-[:ENABLES_LEARNING]->(ku)
        }
        AND EXISTS { -- Pattern 3: Supports goals
            MATCH (user)-[:PURSUING_GOAL]->(goal:Goal)-[:REQUIRES_KNOWLEDGE]->(ku)
            WHERE goal.status IN ['active', 'in_progress']
        }

        RETURN ku
        ORDER BY ku.created_at DESC
        LIMIT 10
        """
