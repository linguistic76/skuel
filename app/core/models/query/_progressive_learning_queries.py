"""
Progressive Learning & Curriculum Query Builders
=================================================

Query builders that leverage difficulty_gap and typical_learning_order fields
for progressive learning paths and curriculum-aware sequencing.

Quick Win #5 Enhancement (November 23, 2025):
- Added difficulty_gap filtering for progressive learning
- Added typical_learning_order sorting for curriculum sequencing
- Leverages already-defined EdgeMetadata fields

See: /docs/improvement_proposals/EDGEMETADATA_UTILIZATION_SUMMARY.md
"""

from typing import Any


class ProgressiveLearningQueries:
    """
    Pure Cypher query builders for progressive learning operations.

    Uses EdgeMetadata.difficulty_gap and EdgeMetadata.typical_learning_order
    to build pedagogically-sound learning paths.

    Key Insights:
    - difficulty_gap: Positive = target harder, Negative = target easier, Zero = same level
    - typical_learning_order: 1-indexed sequence (1, 2, 3, ...)
    - Progressive paths avoid "difficulty walls" (too-hard jumps)
    """

    @staticmethod
    def build_progressive_learning_path_query(
        start_uid: str,
        end_uid: str,
        relationship_type: str = "REQUIRES",
        max_difficulty_jump: float = 2.0,
        min_difficulty_jump: float = 0.1,
        max_depth: int = 5,
    ) -> tuple[str, dict[str, Any]]:
        """
        Build learning path with gradual difficulty progression.

        Finds paths where each step is progressively harder, but not TOO much harder.
        Avoids "difficulty walls" that frustrate learners.

        Args:
            start_uid: Starting concept UID (easier)
            end_uid: Target concept UID (harder)
            relationship_type: Relationship type to traverse (default "REQUIRES")
            max_difficulty_jump: Maximum difficulty increase per step (default 2.0)
            min_difficulty_jump: Minimum difficulty increase per step (default 0.1)
            max_depth: Maximum path length (default 5)

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # Find smooth learning path from basics to advanced
            query, params = ProgressiveLearningQueries.build_progressive_learning_path_query(
                start_uid="ku.python_basics",
                end_uid="ku.python_advanced",
                max_difficulty_jump=2.0,  # No huge jumps
                min_difficulty_jump=0.1   # Must increase difficulty
            )

            # Returns path like:
            # python_basics (difficulty: 1.0)
            #   → oop_concepts (difficulty: 2.2, gap: 1.2) ✅ Smooth
            #   → decorators (difficulty: 3.8, gap: 1.6) ✅ Smooth
            #   → metaclasses (difficulty: 5.5, gap: 1.7) ✅ Smooth
            #   → python_advanced (difficulty: 7.0, gap: 1.5) ✅ Smooth
            #
            # NOT:
            # python_basics (difficulty: 1.0)
            #   → python_advanced (difficulty: 7.0, gap: 6.0) ❌ Too hard!
        """
        cypher = f"""
        MATCH path = shortestPath(
            (start {{uid: $start_uid}})-[rs:{relationship_type}*1..{max_depth}]->(end {{uid: $end_uid}})
        )

        // Filter: ALL steps must have gradual difficulty increase
        WHERE all(r IN relationships(path) WHERE
            r.difficulty_gap IS NOT NULL
            AND r.difficulty_gap >= $min_difficulty_jump  // Must increase
            AND r.difficulty_gap <= $max_difficulty_jump  // But not too much
        )

        // Calculate total difficulty progression
        WITH path, relationships(path) as chain,
             reduce(total_difficulty = 0.0, r IN relationships(path) |
                 total_difficulty + coalesce(r.difficulty_gap, 0.0)
             ) as total_difficulty_gain

        RETURN
            [n IN nodes(path) | {{
                uid: n.uid,
                title: n.title
            }}] as path_nodes,
            [r IN chain | {{
                type: type(r),
                difficulty_gap: r.difficulty_gap,
                typical_order: r.typical_learning_order
            }}] as path_steps,
            length(path) as steps,
            total_difficulty_gain,
            total_difficulty_gain / length(path) as avg_difficulty_per_step

        ORDER BY
            total_difficulty_gain ASC,  // Smoothest progression first
            length(path) ASC            // Shortest path within same difficulty
        """

        return cypher.strip(), {
            "start_uid": start_uid,
            "end_uid": end_uid,
            "max_difficulty_jump": max_difficulty_jump,
            "min_difficulty_jump": min_difficulty_jump,
        }

    @staticmethod
    def build_curriculum_sequenced_prerequisites_query(
        target_uid: str,
        relationship_type: str = "REQUIRES",
        depth: int = 3,
        include_unordered: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        """
        Get prerequisites ordered by typical learning sequence.

        Returns prerequisites sorted by pedagogical order (how they're typically taught).

        Args:
            target_uid: Target concept UID
            relationship_type: Relationship type (default "REQUIRES")
            depth: Maximum prerequisite depth (default 3)
            include_unordered: Include prerequisites without typical_learning_order (default False)

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # Get prerequisites in pedagogical order
            query, params = ProgressiveLearningQueries.build_curriculum_sequenced_prerequisites_query(
                target_uid="ku.web_development"
            )

            # Returns ordered sequence:
            # 1. HTML Basics (order: 1)
            # 2. CSS Fundamentals (order: 2)
            # 3. JavaScript Basics (order: 3)
            # 4. DOM Manipulation (order: 4)
            # 5. Async JavaScript (order: 5)
            #
            # NOT randomly ordered:
            # - Async JavaScript
            # - HTML Basics
            # - DOM Manipulation
            # - CSS Fundamentals
        """
        unordered_filter = "" if include_unordered else "AND r.typical_learning_order IS NOT NULL"

        cypher = f"""
        MATCH path = (target {{uid: $target_uid}})<-[r:{relationship_type}*1..{depth}]-(prereq)
        WHERE NOT (prereq)<-[:{relationship_type}]-()  // Leaf prerequisites only
          {unordered_filter}

        // Get the relationship order (from the direct relationship to target)
        WITH prereq, relationships(path)[0] as direct_rel, length(path) as depth

        RETURN
            prereq.uid as uid,
            prereq.title as title,
            coalesce(direct_rel.typical_learning_order, 999) as learning_order,
            coalesce(direct_rel.difficulty_gap, 0.0) as difficulty_gap,
            depth

        ORDER BY
            learning_order ASC,  // Curriculum order first
            depth ASC,           // Then by prerequisite depth
            difficulty_gap ASC   // Then by difficulty
        """

        return cypher.strip(), {
            "target_uid": target_uid,
        }

    @staticmethod
    def build_difficulty_aware_next_steps_query(
        user_uid: str,
        current_difficulty_level: float,
        max_difficulty_jump: float = 1.5,
        domain: str | None = None,
        limit: int = 10,
    ) -> tuple[str, dict[str, Any]]:
        """
        Find next learning steps appropriate for user's current difficulty level.

        Returns concepts that are slightly harder than current level (progressive challenge).

        Args:
            user_uid: User UID
            current_difficulty_level: User's current difficulty level (0-10 scale)
            max_difficulty_jump: Maximum difficulty increase from current level (default 1.5)
            domain: Optional domain filter (e.g., "TECH")
            limit: Maximum results (default 10)

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # User at difficulty level 3.0, find next challenges
            query, params = ProgressiveLearningQueries.build_difficulty_aware_next_steps_query(
                user_uid="user.mike",
                current_difficulty_level=3.0,
                max_difficulty_jump=1.5
            )

            # Returns concepts with difficulty 3.1-4.5:
            # ku.decorators (difficulty: 3.8, gap: 0.8) - Appropriate challenge
            # ku.generators (difficulty: 4.2, gap: 1.2) - Good stretch
            # (EXCLUDES: ku.metaclasses (difficulty: 6.0, gap: 3.0) - Too hard!)
        """
        domain_filter = "AND target.domain = $domain" if domain else ""

        cypher = f"""
        MATCH (user:User {{uid: $user_uid}})

        // Find concepts user has mastered
        MATCH (user)-[:MASTERED]->(mastered)

        // Find next concepts requiring mastered prerequisites
        MATCH (mastered)<-[r:REQUIRES]-(target)
        WHERE r.difficulty_gap IS NOT NULL
          // Progressive challenge: harder but not too much harder
          AND r.difficulty_gap > 0
          AND r.difficulty_gap <= $max_difficulty_jump
          // User hasn't mastered target yet
          AND NOT (user)-[:MASTERED]->(target)
          {domain_filter}

        // Calculate target's estimated difficulty
        WITH DISTINCT target, r.difficulty_gap as difficulty_gap,
             $current_difficulty_level + r.difficulty_gap as estimated_difficulty

        RETURN
            target.uid as uid,
            target.title as title,
            estimated_difficulty,
            difficulty_gap,
            CASE
                WHEN difficulty_gap <= 0.5 THEN 'easy_next_step'
                WHEN difficulty_gap <= 1.0 THEN 'moderate_challenge'
                ELSE 'significant_challenge'
            END as challenge_level

        ORDER BY
            difficulty_gap ASC,  // Easiest progression first
            estimated_difficulty ASC
        LIMIT $limit
        """

        params: dict[str, Any] = {
            "user_uid": user_uid,
            "current_difficulty_level": current_difficulty_level,
            "max_difficulty_jump": max_difficulty_jump,
            "limit": limit,
        }

        if domain:
            params["domain"] = domain

        return cypher.strip(), params

    @staticmethod
    def build_difficulty_distribution_query(
        domain: str | None = None,
        min_difficulty: float | None = None,
        max_difficulty: float | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Analyze difficulty distribution of prerequisite relationships.

        Returns statistics on difficulty gaps across the knowledge graph.

        Args:
            domain: Optional domain filter
            min_difficulty: Optional minimum difficulty gap filter
            max_difficulty: Optional maximum difficulty gap filter

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # Analyze difficulty distribution in TECH domain
            query, params = ProgressiveLearningQueries.build_difficulty_distribution_query(
                domain="TECH",
                min_difficulty=0.0,
                max_difficulty=5.0
            )

            # Returns:
            # {
            #   "avg_difficulty_gap": 1.2,
            #   "max_difficulty_gap": 4.8,
            #   "difficulty_ranges": {
            #     "gentle (0-1)": 45,
            #     "moderate (1-2)": 32,
            #     "steep (2-3)": 15,
            #     "very_steep (3+)": 8
            #   }
            # }
        """
        domain_filter = "AND target.domain = $domain" if domain else ""
        difficulty_filters = []

        if min_difficulty is not None:
            difficulty_filters.append("r.difficulty_gap >= $min_difficulty")
        if max_difficulty is not None:
            difficulty_filters.append("r.difficulty_gap <= $max_difficulty")

        difficulty_where = f"AND {' AND '.join(difficulty_filters)}" if difficulty_filters else ""

        cypher = f"""
        MATCH (prereq)-[r:REQUIRES]->(target)
        WHERE r.difficulty_gap IS NOT NULL
          {domain_filter}
          {difficulty_where}

        WITH r.difficulty_gap as gap

        RETURN
            avg(gap) as avg_difficulty_gap,
            min(gap) as min_difficulty_gap,
            max(gap) as max_difficulty_gap,
            stdev(gap) as difficulty_gap_stddev,
            percentileCont(gap, 0.25) as p25_difficulty_gap,
            percentileCont(gap, 0.50) as median_difficulty_gap,
            percentileCont(gap, 0.75) as p75_difficulty_gap,
            count(DISTINCT CASE WHEN gap <= 1.0 THEN gap END) as gentle_count,
            count(DISTINCT CASE WHEN gap > 1.0 AND gap <= 2.0 THEN gap END) as moderate_count,
            count(DISTINCT CASE WHEN gap > 2.0 AND gap <= 3.0 THEN gap END) as steep_count,
            count(DISTINCT CASE WHEN gap > 3.0 THEN gap END) as very_steep_count
        """

        params: dict[str, Any] = {}

        if domain:
            params["domain"] = domain
        if min_difficulty is not None:
            params["min_difficulty"] = min_difficulty
        if max_difficulty is not None:
            params["max_difficulty"] = max_difficulty

        return cypher.strip(), params

    @staticmethod
    def build_learning_velocity_query(
        user_uid: str,
        time_window_days: int = 30,
    ) -> tuple[str, dict[str, Any]]:
        """
        Calculate user's learning velocity (difficulty conquered per day).

        Measures how fast user is progressing through difficulty levels.

        Args:
            user_uid: User UID
            time_window_days: Days to analyze (default 30)

        Returns:
            Tuple of (cypher_query, parameters)

        Example:
            # Calculate user's learning velocity over last 30 days
            query, params = ProgressiveLearningQueries.build_learning_velocity_query(
                user_uid="user.mike",
                time_window_days=30
            )

            # Returns:
            # {
            #   "total_difficulty_conquered": 12.5,
            #   "concepts_mastered": 8,
            #   "avg_difficulty_per_concept": 1.56,
            #   "velocity_per_day": 0.42,  // 0.42 difficulty units/day
            #   "trend": "accelerating"
            # }
        """
        cypher = """
        MATCH (user:User {uid: $user_uid})

        // Find concepts mastered in time window
        MATCH (user)-[m:MASTERED]->(ku:Ku)
        WHERE m.achieved_at >= datetime() - duration({days: $time_window_days})

        // Get the difficulty gaps from prerequisites
        OPTIONAL MATCH (ku)<-[r:REQUIRES]-(prereq)
        WHERE r.difficulty_gap IS NOT NULL

        WITH user, ku, m,
             coalesce(avg(r.difficulty_gap), 0.0) as avg_prerequisite_difficulty

        WITH user,
             count(DISTINCT ku) as concepts_mastered,
             sum(avg_prerequisite_difficulty) as total_difficulty_conquered,
             min(m.achieved_at) as first_mastery,
             max(m.achieved_at) as last_mastery

        // Calculate velocity
        WITH user, concepts_mastered, total_difficulty_conquered,
             duration.between(first_mastery, last_mastery).days as days_active

        RETURN
            concepts_mastered,
            total_difficulty_conquered,
            total_difficulty_conquered / CASE WHEN concepts_mastered > 0 THEN concepts_mastered ELSE 1 END as avg_difficulty_per_concept,
            total_difficulty_conquered / CASE WHEN days_active > 0 THEN days_active ELSE 1 END as velocity_per_day,
            days_active,
            CASE
                WHEN velocity_per_day > 0.5 THEN 'fast'
                WHEN velocity_per_day > 0.2 THEN 'moderate'
                ELSE 'slow'
            END as pace
        """

        return cypher.strip(), {
            "user_uid": user_uid,
            "time_window_days": time_window_days,
        }
