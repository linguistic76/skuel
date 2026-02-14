"""
SKUEL GraphQL Schema
====================

Clean GraphQL schema integrated with SKUEL service architecture.

This provides:
- Complex nested queries (solve N+1 problems)
- Flexible field selection (avoid over-fetching)
- Real-time subscriptions (future: learning progress)
- Type-safe API with code generation support
"""

from __future__ import annotations

from collections.abc import (
    AsyncIterator,  # noqa: TC003 - Strawberry evaluates return types at runtime
)
from typing import TYPE_CHECKING, Any

import strawberry
from strawberry.extensions import MaxTokensLimiter, QueryDepthLimiter

from core.constants import ConfidenceLevel, QueryLimit
from core.models.enums import Domain
from routes.graphql.config import get_graphql_config, validate_list_limit

if TYPE_CHECKING:
    from strawberry.types import Info

    from core.models.ku import Ku
    from core.utils.result_simplified import Result
    from routes.graphql.context import GraphQLContext
    from routes.graphql.protocols import KnowledgeUnitLike, LearningStepLike
from routes.graphql.types import (
    Blocker,
    CrossDomainOpportunity,
    DashboardData,
    DependencyGraph,
    KnowledgeNode,
    LearningPath,
    LearningPathContext,
    LearningStep,
    PrerequisiteGraph,
    SearchInput,
    SearchResult,
    Task,
)

# ============================================================================
# HELPER FUNCTIONS USING STRUCTURAL PROTOCOLS (Solution 3)
# ============================================================================


def build_missing_prerequisite_blocker(
    step: LearningStepLike,
    step_ku_uid: str,
    unmet_prereqs: list[Any],
) -> Blocker:
    """
    Build blocker for missing prerequisites using structural typing.

    Args:
        step: Any object satisfying LearningStepLike protocol (has uid, title)
        step_ku_uid: Knowledge unit UID for the step
        unmet_prereqs: List of unmet prerequisite knowledge units

    Returns:
        Blocker indicating missing prerequisites

    Type Safety:
        Protocol guarantees step.title exists - no hasattr() needed
    """
    prereq_titles = [p.title for p in unmet_prereqs[:3]]
    prereq_list = ", ".join(prereq_titles)
    if len(unmet_prereqs) > 3:
        prereq_list += f" (+{len(unmet_prereqs) - 3} more)"

    return Blocker(
        blocker_type="missing_prerequisite",
        knowledge_uid=step_ku_uid,
        knowledge_title=step.title,  # ✅ Protocol guarantees .title exists
        severity="warning",
        description=f"{len(unmet_prereqs)} prerequisite(s) not yet mastered: {prereq_list}",
        recommended_action="Master prerequisites before starting this step",
    )


def build_low_progress_blocker(
    step: LearningStepLike,
    step_ku_uid: str,
    progress: float,
) -> Blocker:
    """
    Build blocker for low progress using structural typing.

    Args:
        step: Any object satisfying LearningStepLike protocol (has uid, title)
        step_ku_uid: Knowledge unit UID for the step
        progress: Current progress (0.0 - 1.0)

    Returns:
        Blocker indicating low progress

    Type Safety:
        Protocol guarantees step.title exists - no hasattr() needed
    """
    return Blocker(
        blocker_type="low_progress",
        knowledge_uid=step_ku_uid,
        knowledge_title=step.title,  # ✅ Protocol guarantees .title exists
        severity="info",
        description=f"Low progress ({progress:.0%}) on this step",
        recommended_action="Consider revisiting fundamentals or seeking additional resources",
    )


def check_deprecated_content(ku: KnowledgeUnitLike) -> tuple[bool, bool]:
    """
    Check if knowledge unit is deprecated or outdated using structural typing.

    Args:
        ku: Any object satisfying KnowledgeUnitLike protocol (has uid, title, metadata)

    Returns:
        Tuple of (is_deprecated, is_outdated)

    Type Safety:
        Protocol guarantees ku.metadata exists (can be None) - no hasattr() needed
    """
    if ku.metadata:
        is_deprecated = ku.metadata.get("deprecated", False)
        is_outdated = ku.metadata.get("outdated", False)
        return (is_deprecated, is_outdated)
    return (False, False)


@strawberry.type
class Query:
    """
    GraphQL queries for SKUEL data.

    All queries use DataLoaders to prevent N+1 problems.
    """

    @strawberry.field
    async def knowledge_unit(
        self, info: Info[GraphQLContext, Any], uid: str
    ) -> KnowledgeNode | None:
        """
        Get a single knowledge unit by UID.

        Uses DataLoader for batching if called multiple times in one request.
        """
        context: GraphQLContext = info.context

        # Use DataLoader for automatic batching
        ku = await context.knowledge_loader.load(uid)

        if not ku:
            return None

        return KnowledgeNode(
            uid=ku.uid,
            title=ku.title,
            summary=ku.summary or "",
            domain=ku.domain.value,
            tags=ku.tags or [],
            quality_score=ku.quality_score,
        )

    @strawberry.field
    async def knowledge_units(
        self,
        info: Info[GraphQLContext, Any],
        domain: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[KnowledgeNode]:
        """
        List knowledge units with optional filtering.

        Supports nested queries - clients can request prerequisites, etc.

        Guardrails:
        - limit is capped at 100 (configured max)
        - Default limit is 20 if not specified
        """
        context: GraphQLContext = info.context

        # GraphQL uses direct backend access for flexible querying
        # Protocol-typed services don't expose backend operations
        if not context.knowledge_backend:
            return []

        # GUARDRAIL: Validate list limit
        safe_limit = validate_list_limit(limit)

        # Build filter based on domain
        filters = {}
        if domain:
            try:
                filters["domain"] = Domain[domain.upper()]
            except KeyError:
                # Invalid domain, return empty
                return []

        # Get knowledge units using universal backend's find_by()
        # NOTE: Cypher query is in repository/backend, not here (guardrail #1)
        # GraphQL bypasses service layer for flexible backend queries
        result = await context.knowledge_backend.find_by(limit=safe_limit, **filters)

        if result.is_error or not result.value:
            return []

        # Convert to GraphQL types
        return [
            KnowledgeNode(
                uid=ku.uid,
                title=ku.title,
                summary=ku.summary or "",
                domain=ku.domain.value,
                tags=ku.tags or [],
                quality_score=ku.quality_score,
            )
            for ku in result.value
        ]

    @strawberry.field
    async def search_knowledge(
        self, info: Info[GraphQLContext, Any], input: SearchInput
    ) -> list[SearchResult]:
        """
        Semantic search for knowledge units using SearchRouter.

        Returns ranked results with relevance scores.

        Guardrails:
        - Search limit is validated and capped
        - Uses SearchRouter (One Path Forward, January 2026)
        """
        from core.models.search_request import SearchRequest

        context: GraphQLContext = info.context

        if not context.search_router:
            return []

        # GUARDRAIL: Validate search limit
        safe_limit = validate_list_limit(input.limit)

        # Build search request
        search_request = SearchRequest(
            query_text=input.query,
            domain=Domain.KNOWLEDGE,  # Search only knowledge domain
            limit=safe_limit,
            offset=0,
            include_facet_counts=False,  # GraphQL doesn't need facets
        )

        # Perform search using SearchRouter (One Path Forward)
        result = await context.search_router.faceted_search(search_request, context.user_uid)

        if result.is_error or not result.value.results:
            return []

        # Convert SearchResponse results to GraphQL SearchResult format
        return [
            SearchResult(
                knowledge=KnowledgeNode(
                    uid=item.get("uid", ""),
                    title=item.get("title", ""),
                    summary=item.get("summary", ""),
                    domain=item.get("_domain", "knowledge"),
                    tags=item.get("tags", []),
                    quality_score=item.get("quality_score", 0.5),
                ),
                relevance=item.get("_score", 1.0),
                explanation=item.get("explanation", ""),
            )
            for item in result.value.results
        ]

    @strawberry.field
    async def task(self, info: Info[GraphQLContext, Any], uid: str) -> Task | None:
        """
        Get a single task by UID with optional nested knowledge units.

        Uses DataLoader for batching.
        """
        context: GraphQLContext = info.context

        # Use DataLoader
        task = await context.task_loader.load(uid)

        if not task:
            return None

        return Task(
            uid=task.uid,
            title=task.title,
            description=task.description or "",
            status=task.status.value,
            priority=task.priority.value,
        )

    @strawberry.field
    async def tasks(
        self,
        info: Info[GraphQLContext, Any],
        include_completed: bool = False,
        limit: int | None = None,
    ) -> list[Task]:
        """
        List tasks for the authenticated user.

        Authentication:
        - Uses authenticated user from context (REQUIRED)
        - No user_uid parameter - prevents spoofing

        Clients can nest knowledge units to avoid N+1 queries.
        """
        context: GraphQLContext = info.context

        # AUTHENTICATION: Require authenticated user
        if not context.user_uid:
            raise Exception("Authentication required. Please log in to view tasks.")

        if not context.services.tasks:
            return []

        safe_limit = validate_list_limit(limit)

        # Get tasks
        result = await context.services.tasks.get_user_tasks(user_uid=context.user_uid)

        if result.is_error or not result.value:
            return []

        # Filter and limit tasks
        filtered_tasks = result.value
        if not include_completed:
            from core.models.enums import KuStatus

            filtered_tasks = [t for t in filtered_tasks if t.status != KuStatus.COMPLETED]
        filtered_tasks = filtered_tasks[:safe_limit]

        # Convert to GraphQL types
        # GRAPH-NATIVE: knowledge_uid removed from Task type
        # Use the knowledge() resolver instead to get related KUs
        return [
            Task(
                uid=task.uid,
                title=task.title,
                description=task.description or "",
                status=task.status.value,
                priority=task.priority.value,
            )
            for task in filtered_tasks
        ]

    @strawberry.field
    async def learning_path(self, info: Info[GraphQLContext, Any], uid: str) -> LearningPath | None:
        """
        Get a learning path with nested steps and knowledge units.

        This solves the N+1 problem of fetching path -> steps -> knowledge.
        """
        context: GraphQLContext = info.context

        # Use DataLoader
        path = await context.learning_path_loader.load(uid)

        if not path:
            return None

        return LearningPath(
            uid=path.uid,
            name=path.name,
            goal=path.goal or "",
            total_steps=len(path.steps),
            estimated_hours=path.estimated_hours or 0.0,
        )

    @strawberry.field
    async def discover_cross_domain(
        self,
        info: Info[GraphQLContext, Any],
        user_knowledge: list[str],
        target_domains: list[str] | None = None,
        max_opportunities: int = 10,
    ) -> list[CrossDomainOpportunity]:
        """
        Discover cross-domain learning opportunities.

        This is a complex query that would require many REST calls.
        With GraphQL, it's a single request.

        Guardrails:
        - max_opportunities is validated and capped
        - Logic is in service layer (not here)
        """
        context: GraphQLContext = info.context

        # Get cross-domain service from bootstrap (circular import resolved)
        cross_domain_service = context.services.cross_domain
        if not cross_domain_service:
            raise ValueError("Cross-domain service not available")

        # GUARDRAIL: Validate max opportunities limit
        safe_max = validate_list_limit(max_opportunities, default=10)

        # Parse target domains
        parsed_domains = None
        if target_domains:
            parsed_domains = []
            for domain_str in target_domains:
                try:
                    parsed_domains.append(Domain[domain_str.upper()])
                except KeyError:
                    # Skip invalid domains
                    continue

        # Build knowledge state from user knowledge
        knowledge_state = {
            "applied_knowledge": set(user_knowledge),
            "mastered_concepts": set(user_knowledge),  # Simplification for now
        }

        # Get cross-domain opportunities
        result = await cross_domain_service.discover_cross_domain_opportunities(
            user_uid=context.user_uid or "anonymous",
            knowledge_state=knowledge_state,
            min_confidence=ConfidenceLevel.LOW,
        )

        if result.is_error or not result.value:
            return []

        # Convert to GraphQL types
        opportunities = []
        for opp in result.value[:safe_max]:
            # Create placeholder KnowledgeNodes from opportunity data
            # Note: In production, we would fetch actual KU data via DataLoader
            source_node = KnowledgeNode(
                uid=f"ku.{opp.source_domain.value}",
                title=f"{opp.source_domain.value} Knowledge",
                summary=f"Knowledge from {opp.source_domain.value} domain",
                domain=opp.source_domain.value,
                tags=[],
                quality_score=1.0,
            )

            target_node = KnowledgeNode(
                uid=f"ku.{opp.target_domain.value}",
                title=f"{opp.target_domain.value} Opportunity",
                summary=f"Opportunity in {opp.target_domain.value} domain",
                domain=opp.target_domain.value,
                tags=[],
                quality_score=1.0,
            )

            opportunities.append(
                CrossDomainOpportunity(
                    source=source_node,
                    target=target_node,
                    bridgeType=opp.application_type,
                    transferability=opp.skill_transfer_potential,
                    effortRequired=f"Difficulty: {opp.estimated_difficulty}/10",
                    reasoning=opp.description,
                    practical_projects=opp.practical_projects if opp.practical_projects else None,
                    success_patterns=opp.success_patterns if opp.success_patterns else None,
                    supporting_examples=opp.supporting_examples
                    if opp.supporting_examples
                    else None,
                )
            )

        return opportunities

    @strawberry.field
    async def learning_paths(
        self, info: Info[GraphQLContext, Any], limit: int | None = None, all_paths: bool = False
    ) -> list[LearningPath]:
        """
        List learning paths.

        Authentication:
        - Default: Returns authenticated user's paths
        - If all_paths=True: Returns all paths (for discovery)

        Guardrails:
        - limit is validated and capped
        - Cypher queries are in LearningPathBackend (not here)
        """
        context: GraphQLContext = info.context

        if not context.services.lp:
            return []

        safe_limit = validate_list_limit(limit)

        # Get user-specific or all paths
        if all_paths:
            # Discovery mode - list all paths
            result = await context.services.lp.list_all_paths(limit=safe_limit)
        else:
            # User mode - require authentication
            if not context.user_uid:
                raise Exception(
                    "Authentication required. Please log in to view your learning paths."
                )

            result = await context.services.lp.list_user_paths(
                user_uid=context.user_uid, limit=safe_limit
            )

        if result.is_error or not result.value:
            return []

        # Convert to GraphQL types
        return [
            LearningPath(
                uid=path.uid,
                name=path.name,
                goal=path.goal or "",
                total_steps=len(path.steps),
                estimated_hours=path.estimated_hours or 0.0,
            )
            for path in result.value
        ]

    # ========================================================================
    # PHASE 2: Complex Graph Queries (GraphQL's Strength)
    # ========================================================================

    @strawberry.field
    async def learning_path_with_context(
        self, info: Info[GraphQLContext, Any], path_uid: str, user_uid: str | None = None
    ) -> LearningPathContext | None:
        """
        Get learning path with rich context: progress, blockers, recommendations.

        This demonstrates GraphQL's power - combining data from multiple services
        that would require 5+ REST calls into a single query.

        Returns:
            Complete learning path context with progress tracking
        """
        context: GraphQLContext = info.context

        # Use authenticated user or provided user_uid
        target_user_uid = user_uid or context.user_uid
        if not target_user_uid:
            raise Exception("Authentication required or user_uid parameter needed")

        if not context.services.lp:
            return None

        # Load the learning path
        path = await context.learning_path_loader.load(path_uid)
        if not path:
            return None

        # Get path steps with type safety
        steps_result: Result[list[Ku]] = await context.services.lp.get_steps(path_uid)
        steps: list[Ku] = steps_result.value if steps_result.is_ok else []

        # Calculate progress from steps
        # Note: unified_progress DELETED (January 2026) - steps_completed now derived from user mastery
        total_steps = len(steps)
        completed_steps = 0

        if context.services.user_progress:
            # Count steps where user has mastered the associated knowledge
            profile_result = await context.services.user_progress.build_user_knowledge_profile(
                target_user_uid
            )
            if profile_result.is_ok:
                mastered_uids = {m.knowledge_uid for m in profile_result.value.mastered}
                for step in steps:
                    # Step is completed if user mastered associated KUs
                    if (
                        hasattr(step, "knowledge_uids")
                        and step.knowledge_uids
                        and all(uid in mastered_uids for uid in step.knowledge_uids)
                    ):
                        completed_steps += 1

        current_step_number = completed_steps + 1 if completed_steps < total_steps else total_steps

        # Calculate completion percentage
        completion_percentage = (completed_steps / total_steps * 100.0) if total_steps > 0 else 0.0

        # Get blockers by checking prerequisites and mastery
        blockers: list[Blocker] = []

        if context.services.user_progress:
            # Build user knowledge profile to check mastery
            profile_result = await context.services.user_progress.build_user_knowledge_profile(
                target_user_uid
            )

            if profile_result.is_ok:
                profile = profile_result.value
                mastered_uids = profile.mastered_uids

                # Check each step for blockers
                for step in steps:
                    step_ku_uid = (
                        step.primary_knowledge_uids[0] if step.primary_knowledge_uids else ""
                    )
                    if not step_ku_uid:
                        continue  # Skip steps with no knowledge UID

                    # Get prerequisites for this step's knowledge
                    if context.services.ku:
                        prereqs_result = await context.services.ku.get_prerequisites(step_ku_uid)

                        if prereqs_result.is_ok and prereqs_result.value:
                            # Check for unmet prerequisites
                            unmet_prereqs = [
                                p for p in prereqs_result.value if p.uid not in mastered_uids
                            ]

                            if unmet_prereqs:
                                # Use protocol-based helper function (Solution 3)
                                blocker = build_missing_prerequisite_blocker(
                                    step=step,  # Ls satisfies LearningStepLike protocol
                                    step_ku_uid=step_ku_uid,
                                    unmet_prereqs=unmet_prereqs,
                                )
                                blockers.append(blocker)

                    # Check for low mastery on current step (if in progress)
                    if step_ku_uid in profile.in_progress_uids:
                        # Find the progress entry
                        in_progress = [
                            ip
                            for ip in profile.in_progress_knowledge
                            if ip.knowledge_uid == step_ku_uid
                        ]

                        if in_progress and in_progress[0].progress < 0.3:
                            # Use protocol-based helper function (Solution 3)
                            blocker = build_low_progress_blocker(
                                step=step,  # Ls satisfies LearningStepLike protocol
                                step_ku_uid=step_ku_uid,
                                progress=in_progress[0].progress,
                            )
                            blockers.append(blocker)

        # Get next recommended steps (simplified - return next 3 incomplete steps)
        # Use from_domain() for explicit DTO conversion
        next_steps = []
        for i, step in enumerate(steps[completed_steps : completed_steps + 3]):
            next_steps.append(LearningStep.from_domain(step, completed_steps + i + 1))

        # Check if prerequisites are met (simplified)
        prerequisites_met = len(blockers) == 0

        return LearningPathContext(
            path=LearningPath(
                uid=path.uid,
                name=path.name,
                goal=path.goal or "",
                total_steps=total_steps,
                estimated_hours=path.estimated_hours or 0.0,
            ),
            current_step_number=current_step_number,
            completed_steps=completed_steps,
            completion_percentage=completion_percentage,
            blockers=blockers,
            next_recommended_steps=next_steps,
            prerequisites_met=prerequisites_met,
        )

    @strawberry.field
    async def prerequisite_chain(
        self,
        info: Info[GraphQLContext, Any],
        knowledge_uid: str,
        max_depth: int = 5,
        user_uid: str | None = None,
    ) -> PrerequisiteGraph | None:
        """
        Get full prerequisite dependency tree for a knowledge unit.

        This solves "what do I need to learn first?" by traversing the entire
        prerequisite chain in a single GraphQL query.

        Args:
            knowledge_uid: Target knowledge unit
            max_depth: Maximum traversal depth (default 5, max 10)
            user_uid: User for mastery status (optional)

        Returns:
            Complete prerequisite tree with mastery status
        """
        from routes.graphql.types import PrerequisiteNode

        context: GraphQLContext = info.context

        # Validate max_depth
        safe_max_depth = min(max_depth, 10)

        if not context.services.ku:
            return None

        # Load target knowledge unit
        ku = await context.knowledge_loader.load(knowledge_uid)
        if not ku:
            return None

        # Get user's mastery profile if user_uid provided
        target_user_uid = user_uid or context.user_uid
        mastered_uids: set[str] = set()

        if target_user_uid and context.services.user_progress:
            profile_result = await context.services.user_progress.build_user_knowledge_profile(
                target_user_uid
            )
            if profile_result.is_ok:
                mastered_uids = profile_result.value.mastered_uids

        # Recursive helper to build prerequisite tree
        async def build_prerequisite_tree(
            ku_uid: str, current_depth: int, visited: set[str]
        ) -> tuple[list[PrerequisiteNode], int, float]:
            """
            Recursively build prerequisite tree.

            Args:
                ku_uid: Knowledge unit to get prerequisites for
                current_depth: Current depth in tree
                visited: Set of already-visited UIDs to prevent cycles

            Returns:
                Tuple of (prerequisite_nodes, total_count, total_hours)
            """
            # Stop if max depth reached or already visited (cycle detection)
            if current_depth >= safe_max_depth or ku_uid in visited:
                return ([], 0, 0.0)

            visited.add(ku_uid)

            # Get prerequisites for this knowledge unit
            if not context.services.ku:
                return ([], 0, 0.0)

            prereqs_result = await context.services.ku.get_prerequisites(ku_uid)
            if prereqs_result.is_error or not prereqs_result.value:
                return ([], 0, 0.0)

            prereq_nodes = []
            total_count = 0
            total_hours = 0.0

            for prereq_ku in prereqs_result.value:
                # Check mastery status using user's knowledge profile
                is_mastered = prereq_ku.uid in mastered_uids

                # Estimated hours for this prerequisite
                prereq_hours = 2.0  # Simplified estimate
                total_hours += prereq_hours
                total_count += 1

                # Recursively get children (deeper prerequisites)
                children, child_count, child_hours = await build_prerequisite_tree(
                    prereq_ku.uid, current_depth + 1, visited
                )

                # Accumulate totals from children
                total_count += child_count
                total_hours += child_hours

                # Build node
                prereq_nodes.append(
                    PrerequisiteNode(
                        knowledge=KnowledgeNode(
                            uid=prereq_ku.uid,
                            title=prereq_ku.title,
                            summary=prereq_ku.summary or "",
                            domain=prereq_ku.domain.value,
                            tags=prereq_ku.tags or [],
                            quality_score=prereq_ku.quality_score,
                        ),
                        depth=current_depth + 1,
                        is_mastered=is_mastered,
                        children=children,
                    )
                )

            return (prereq_nodes, total_count, total_hours)

        # Build prerequisite tree recursively starting at depth 0
        visited_nodes: set[str] = set()
        (
            prerequisite_tree,
            total_prerequisites,
            estimated_total_hours,
        ) = await build_prerequisite_tree(knowledge_uid, 0, visited_nodes)

        # Count mastered prerequisites using actual user mastery data
        def count_mastered_in_tree(nodes: list) -> int:
            """Recursively count mastered prerequisites in tree."""
            count = 0
            for node in nodes:
                if node.is_mastered:
                    count += 1
                # Recursively count mastered children
                count += count_mastered_in_tree(node.children)
            return count

        prerequisites_mastered = count_mastered_in_tree(prerequisite_tree)

        return PrerequisiteGraph(
            target=KnowledgeNode(
                uid=ku.uid,
                title=ku.title,
                summary=ku.summary or "",
                domain=ku.domain.value,
                tags=ku.tags or [],
                quality_score=ku.quality_score,
            ),
            prerequisite_tree=prerequisite_tree,
            total_prerequisites=total_prerequisites,
            prerequisites_mastered=prerequisites_mastered,
            estimated_total_hours=estimated_total_hours,
        )

    @strawberry.field
    async def knowledge_dependencies(
        self, info: Info[GraphQLContext, Any], knowledge_uid: str, depth: int = 2
    ) -> DependencyGraph | None:
        """
        Get knowledge dependency graph showing all relationships.

        This visualizes the knowledge structure: what connects to what,
        how knowledge units relate to each other.

        Args:
            knowledge_uid: Center node of the graph
            depth: Traversal depth (default 2, max 3)

        Returns:
            Complete dependency graph with nodes and edges
        """
        from routes.graphql.types import DependencyEdge

        context: GraphQLContext = info.context

        # Validate depth
        safe_depth = min(depth, 3)

        if not context.services.ku:
            return None

        # Load center knowledge unit
        ku = await context.knowledge_loader.load(knowledge_uid)
        if not ku:
            return None

        # Get all relationships (prerequisites + enables)
        prerequisites_result = await context.services.ku.get_prerequisites(knowledge_uid)
        enables_result = await context.services.ku.get_enables(knowledge_uid)

        prerequisites = prerequisites_result.value if prerequisites_result.is_ok else []
        enables = enables_result.value if enables_result.is_ok else []

        # Build nodes list (center + prerequisites + enables)
        nodes = [
            KnowledgeNode(
                uid=ku.uid,
                title=ku.title,
                summary=ku.summary or "",
                domain=ku.domain.value,
                tags=ku.tags or [],
                quality_score=ku.quality_score,
            )
        ]

        # Build edges list
        edges = []

        # Add prerequisite edges
        for prereq in prerequisites:
            nodes.append(
                KnowledgeNode(
                    uid=prereq.uid,
                    title=prereq.title,
                    summary=prereq.summary or "",
                    domain=prereq.domain.value,
                    tags=prereq.tags or [],
                    quality_score=prereq.quality_score,
                )
            )
            edges.append(
                DependencyEdge(
                    from_knowledge=nodes[-1],
                    to_knowledge=nodes[0],
                    relationship_type="REQUIRES",
                    strength=1.0,
                )
            )

        # Add enables edges
        for enabled in enables:
            nodes.append(
                KnowledgeNode(
                    uid=enabled.uid,
                    title=enabled.title,
                    summary=enabled.summary or "",
                    domain=enabled.domain.value,
                    tags=enabled.tags or [],
                    quality_score=enabled.quality_score,
                )
            )
            edges.append(
                DependencyEdge(
                    from_knowledge=nodes[0],
                    to_knowledge=nodes[-1],
                    relationship_type="ENABLES",
                    strength=1.0,
                )
            )

        return DependencyGraph(
            center=nodes[0],
            nodes=nodes,
            edges=edges,
            depth=safe_depth,
        )

    @strawberry.field
    async def learning_path_blockers(
        self, info: Info[GraphQLContext, Any], path_uid: str, user_uid: str | None = None
    ) -> list[Blocker]:
        """
        Identify all blockers preventing progress in a learning path.

        Types of blockers detected:
        - Missing prerequisites (knowledge gaps)
        - Low mastery scores (insufficient understanding)
        - Circular dependencies (path design issues)
        - Deprecated content (outdated knowledge units)

        This is perfect for GraphQL - it would require multiple REST calls
        to check prerequisites, mastery, and path integrity.

        Args:
            path_uid: Learning path to analyze
            user_uid: User for mastery/progress checks (optional)

        Returns:
            List of blockers with severity and recommended actions
        """
        context: GraphQLContext = info.context

        # Use authenticated user or provided user_uid
        target_user_uid = user_uid or context.user_uid

        if not context.services.lp or not context.services.ku:
            return []

        # Load the learning path
        path = await context.learning_path_loader.load(path_uid)
        if not path:
            return []

        # Get path steps
        steps_result = await context.services.lp.get_steps(path_uid)
        if steps_result.is_error:
            return []

        steps = steps_result.value

        # Analyze each step for blockers
        blockers = []

        for i, step in enumerate(steps):
            # GRAPH-NATIVE: Use primary_knowledge_uids instead of knowledge_uid
            step_ku_uid = step.primary_knowledge_uids[0] if step.primary_knowledge_uids else None
            if not step_ku_uid:
                continue  # Skip steps with no knowledge UID

            # Check if knowledge unit exists
            ku = await context.knowledge_loader.load(step_ku_uid)
            if not ku:
                blockers.append(
                    Blocker(
                        blocker_type="missing_content",
                        knowledge_uid=step_ku_uid,
                        knowledge_title=f"Step {i + 1}",
                        severity="critical",
                        description=f"Knowledge unit {step_ku_uid} does not exist",
                        recommended_action="Remove this step or replace with valid knowledge unit",
                    )
                )
                continue

            # Check prerequisites and mastery status
            prereqs_result = await context.services.ku.get_prerequisites(step_ku_uid)
            if prereqs_result.is_ok and prereqs_result.value:
                # Check user mastery for each prerequisite
                unmet_prereqs = []
                mastery_threshold = 0.7  # Mastery threshold for prerequisites

                for prereq_ku in prereqs_result.value:
                    is_mastered = False

                    # Check mastery if user_uid is provided and user_service is available
                    if target_user_uid and context.services.user_service:
                        mastery_result = await context.services.user_service.get_user_mastery(
                            user_uid=target_user_uid, concept_uid=prereq_ku.uid
                        )

                        if mastery_result.is_ok:
                            mastery_score = mastery_result.value
                            is_mastered = mastery_score >= mastery_threshold
                        else:
                            # No mastery data means not mastered
                            is_mastered = False
                    else:
                        # No user context - assume not mastered
                        is_mastered = False

                    if not is_mastered:
                        unmet_prereqs.append(prereq_ku.title)

                # Only create blocker if there are unmet prerequisites
                if unmet_prereqs:
                    prereq_list = ", ".join(unmet_prereqs[:3])  # Show first 3
                    if len(unmet_prereqs) > 3:
                        prereq_list += f" (+{len(unmet_prereqs) - 3} more)"

                    blockers.append(
                        Blocker(
                            blocker_type="missing_prerequisite",
                            knowledge_uid=ku.uid,
                            knowledge_title=ku.title,
                            severity="warning",
                            description=f"{len(unmet_prereqs)} prerequisite(s) not yet mastered: {prereq_list}",
                            recommended_action=f"Complete prerequisites before attempting {ku.title}",
                        )
                    )

            # Check for circular dependencies in path
            # A step has a circular dependency if it requires knowledge from a later step
            for j, later_step in enumerate(steps[i + 1 :], start=i + 1):
                # GRAPH-NATIVE: Use primary_knowledge_uids instead of knowledge_uid
                later_ku_uid = (
                    later_step.primary_knowledge_uids[0]
                    if later_step.primary_knowledge_uids
                    else None
                )
                if not later_ku_uid:
                    continue

                # Check if current step requires the later step's knowledge
                if prereqs_result.is_ok and prereqs_result.value:
                    prereq_uids = [p.uid for p in prereqs_result.value]

                    if later_ku_uid in prereq_uids:
                        blockers.append(
                            Blocker(
                                blocker_type="circular_dependency",
                                knowledge_uid=step_ku_uid,
                                knowledge_title=ku.title,
                                severity="critical",
                                description=f"Step {i + 1} requires Step {j + 1} ({later_ku_uid}), creating a circular dependency",
                                recommended_action="Reorder learning path steps to resolve circular dependencies",
                            )
                        )

            # Check for deprecated/outdated content using protocol-based helper (Solution 3)
            # Knowledge units can have metadata indicating deprecation or last_updated
            is_deprecated, is_outdated = check_deprecated_content(
                ku
            )  # Ku satisfies KnowledgeUnitLike protocol

            if is_deprecated:
                blockers.append(
                    Blocker(
                        blocker_type="deprecated_content",
                        knowledge_uid=ku.uid,
                        knowledge_title=ku.title,
                        severity="warning",
                        description="Knowledge unit is marked as deprecated",
                        recommended_action="Replace with updated knowledge unit or remove from path",
                    )
                )
            elif is_outdated:
                blockers.append(
                    Blocker(
                        blocker_type="outdated_content",
                        knowledge_uid=ku.uid,
                        knowledge_title=ku.title,
                        severity="info",
                        description="Knowledge unit may contain outdated information",
                        recommended_action="Review and update content or verify accuracy",
                    )
                )

        return blockers

    @strawberry.field
    async def user_dashboard(self, info: Info[GraphQLContext, Any]) -> DashboardData:
        """
        Get complete dashboard data for the authenticated user in ONE query.

        This demonstrates GraphQL's power - fetching related data that would
        require 5+ REST calls in a single request.

        Authentication:
        - REQUIRED: Uses authenticated user from context
        - Users can ONLY view their own dashboard

        Returns:
        - tasks (with nested knowledge units)
        - learning_paths (with nested steps)
        - habits
        - Recent activity
        """
        context: GraphQLContext = info.context

        # AUTHENTICATION: Require authenticated user
        if not context.user_uid:
            raise Exception("Authentication required. Please log in to view your dashboard.")

        target_user_uid = context.user_uid

        # Fetch all user data in parallel using DataLoaders
        tasks_count = 0
        paths_count = 0
        habits_count = 0

        # Get tasks (limit 10 recent)
        if context.services.tasks:
            tasks_result = await context.services.tasks.get_user_tasks(target_user_uid)
            if tasks_result.is_ok:
                # Limit to 10 most recent
                tasks = tasks_result.value[:10] if tasks_result.value else []
                tasks_count = len(tasks)

        # Get learning paths (limit 5)
        if context.services.lp:
            paths_result = await context.services.lp.list_user_paths(
                user_uid=target_user_uid, limit=QueryLimit.PREVIEW
            )
            if paths_result.is_ok:
                paths_count = len(paths_result.value) if paths_result.value else 0

        # Get habits count
        if context.services.habits:
            habits_result = await context.services.habits.get_user_habits(target_user_uid)
            if habits_result.is_ok:
                habits_count = len(habits_result.value) if habits_result.value else 0

        return DashboardData(
            tasks_count=tasks_count, paths_count=paths_count, habits_count=habits_count
        )


@strawberry.type
class Mutation:
    """
    GraphQL mutations - CURRENTLY DISABLED.

    Following hybrid approach:
    - GraphQL is READ-ONLY for complex nested queries
    - Use REST API for all mutations (create, update, delete)

    This keeps mutations in one place (REST) and leverages
    GraphQL's strength: flexible, composable reads.
    """

    @strawberry.mutation
    async def placeholder(self) -> str:
        """
        Placeholder mutation to satisfy GraphQL schema requirements.

        All actual mutations should use REST endpoints.
        """
        return "Use REST API for mutations (POST, PUT, DELETE)"


@strawberry.type
class Subscription:
    """
    GraphQL subscriptions for real-time updates.

    Note: Requires WebSocket support in FastHTML integration.
    """

    @strawberry.subscription
    async def learning_progress(
        self, info: Info[GraphQLContext, Any], user_uid: str, path_uid: str
    ) -> AsyncIterator[float]:
        """
        Subscribe to learning progress updates via event bus.

        Listens to LearningPathProgressUpdated events and yields
        progress values (0.0-1.0) for the specified user and path.

        Args:
            info: GraphQL context with services
            user_uid: User identifier to filter events
            path_uid: Learning path identifier to filter events

        Yields:
            Progress values (0.0 to 1.0) when updates occur
        """
        import asyncio

        from core.events.learning_events import LearningPathProgressUpdated

        # Get event bus from services
        event_bus = info.context.services.event_bus if info.context.services else None

        if not event_bus:
            # Fallback: No event bus available, yield initial progress
            # This ensures subscription doesn't fail during development
            yield 0.0
            return

        # Create queue for this subscription
        progress_queue: asyncio.Queue[float] = asyncio.Queue()

        # Event handler that filters by user_uid and path_uid
        def handle_progress_update(event: LearningPathProgressUpdated) -> None:
            """Filter and queue progress updates for this subscription."""
            if event.user_uid == user_uid and event.path_uid == path_uid:
                # Put new progress value in queue (non-blocking)
                try:
                    progress_queue.put_nowait(event.new_progress)
                except asyncio.QueueFull:
                    pass  # Skip if queue is full

        # Subscribe to learning progress events
        event_bus.subscribe(LearningPathProgressUpdated, handle_progress_update)

        try:
            # Yield progress updates as they arrive
            while True:
                # Wait for next progress update (with timeout for keepalive)
                try:
                    progress = await asyncio.wait_for(progress_queue.get(), timeout=30.0)
                    yield progress
                except TimeoutError:
                    # No updates in 30 seconds - yield current progress as keepalive
                    # This prevents connection timeout
                    continue

        finally:
            # Cleanup: Unsubscribe when subscription ends
            try:
                event_bus.unsubscribe(LearningPathProgressUpdated, handle_progress_update)
            except Exception:
                pass  # Ignore cleanup errors


def create_graphql_schema() -> strawberry.Schema:
    """
    Create the SKUEL GraphQL schema with security extensions.

    Security Extensions:
    - QueryDepthLimiter: Prevents deeply nested queries (max depth: 5)
    - MaxTokensLimiter: Prevents huge queries (max tokens: 1000)

    Returns:
        Configured Strawberry schema ready for FastHTML integration
    """
    config = get_graphql_config()

    return strawberry.Schema(
        query=Query,
        mutation=Mutation,
        subscription=Subscription,
        extensions=[
            # Prevent deeply nested queries (depth bombs)
            QueryDepthLimiter(
                max_depth=config.max_query_depth,
            ),
            # Prevent huge queries (token limit)
            MaxTokensLimiter(
                max_token_count=config.max_query_tokens,
            ),
        ],
    )
