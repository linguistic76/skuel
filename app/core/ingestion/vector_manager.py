"""
Vector modeling for directional change and trajectories.

Vectors represent direction + magnitude in conceptual spaces,
perfect for modeling learning paths, goal progress, and life strategies.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class VectorSpace(StrEnum):
    """Conceptual spaces where vectors operate."""

    LIFE_STRATEGY = "life-strategy"
    LEARNING = "learning"
    GOALS = "goals"
    HABITS = "habits"
    WELLBEING = "wellbeing"
    CAREER = "career"
    FINANCE = "finance"


@dataclass(frozen=True)
class Vector:
    """
    A vector in a conceptual space.

    Vectors can be:
    1. First-class nodes - Named trajectories that can be referenced
    2. Edge properties - Transitions between states
    """

    uid: str
    title: str
    space: VectorSpace
    components: dict[str, float]  # Named axes with magnitudes
    magnitude: float | None = None  # Computed or provided
    origin: str | None = None  # Starting state/node UID
    target: str | None = None  # Target state/node UID
    timeframe_start: date | None = None
    timeframe_end: date | None = None
    notes: str | None = None
    connections: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Compute magnitude if not provided."""
        if self.magnitude is None and self.components:
            # Calculate Euclidean magnitude
            sum_squares = sum(v**2 for v in self.components.values())
            object.__setattr__(self, "magnitude", sum_squares**0.5)

    def dot_product(self, other: "Vector") -> float:
        """
        Calculate dot product with another vector.

        Useful for finding alignment between vectors.
        """
        if self.space != other.space:
            raise ValueError(
                f"Cannot compute dot product across different spaces: {self.space} vs {other.space}"
            )

        result = 0.0
        for axis, value in self.components.items():
            if axis in other.components:
                result += value * other.components[axis]
        return result

    def add(self, other: "Vector") -> "Vector":
        """
        Add two vectors to get resultant direction.

        Useful for combining multiple influences.
        """
        if self.space != other.space:
            raise ValueError(
                f"Cannot add vectors from different spaces: {self.space} vs {other.space}"
            )

        # Combine components
        combined = dict(self.components)
        for axis, value in other.components.items():
            combined[axis] = combined.get(axis, 0.0) + value

        return Vector(
            uid=f"{self.uid}+{other.uid}",
            title=f"{self.title} + {other.title}",
            space=self.space,
            components=combined,
            notes=f"Resultant of {self.uid} and {other.uid}",
        )

    def scale(self, factor: float) -> "Vector":
        """Scale vector by a factor."""
        scaled_components = {k: v * factor for k, v in self.components.items()}

        return Vector(
            uid=f"{self.uid}*{factor}",
            title=f"{self.title} (scaled {factor}x)",
            space=self.space,
            components=scaled_components,
            notes=f"Scaled version of {self.uid}",
        )

    def normalize(self) -> "Vector":
        """Create unit vector (magnitude = 1)."""
        if not self.magnitude or self.magnitude == 0:
            return self

        return self.scale(1.0 / self.magnitude)


class VectorManager:
    """
    Manages vector operations in Neo4j.

    Provides high-level operations for:
    - Creating and updating vectors
    - Computing resultant vectors
    - Tracking vector evolution
    - Finding aligned vectors
    """

    def __init__(self, driver) -> None:
        """Initialize with Neo4j driver."""
        self.driver = driver
        self.logger = get_logger(__name__)

    async def create_vector(self, vector: Vector) -> Result[str]:
        """
        Create a vector as a first-class node.

        Args:
            vector: Vector to create

        Returns:
            Result containing the vector UID
        """
        query = """
        MERGE (v:Vector {uid: $uid})
        SET v.title = $title,
            v.space = $space,
            v.components = $components,
            v.magnitude = $magnitude,
            v.origin = $origin,
            v.target = $target,
            v.timeframe_start = $timeframe_start,
            v.timeframe_end = $timeframe_end,
            v.notes = $notes,
            v.updated_at = datetime()
        ON CREATE SET v.created_at = datetime()

        // Create relationships if specified
        WITH v
        FOREACH (jid IN $mentions_in |
            MERGE (j:JournalEntry {uid: jid})
            MERGE (v)-[:MENTIONS_IN]->(j)
        )
        FOREACH (lpid IN $grounded_by |
            MERGE (lp:LifePrinciple {uid: lpid})
            MERGE (v)-[:GROUNDED_BY]->(lp)
        )

        // Link to origin/target states if provided
        WITH v
        FOREACH (_ IN CASE WHEN $origin IS NULL THEN [] ELSE [1] END |
            MERGE (o:State {uid: $origin})
            MERGE (v)-[:FROM]->(o)
        )
        FOREACH (_ IN CASE WHEN $target IS NULL THEN [] ELSE [1] END |
            MERGE (t:State {uid: $target})
            MERGE (v)-[:TO]->(t)
        )

        RETURN v.uid as uid
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "uid": vector.uid,
                        "title": vector.title,
                        "space": vector.space.value,
                        "components": vector.components,
                        "magnitude": vector.magnitude,
                        "origin": vector.origin,
                        "target": vector.target,
                        "timeframe_start": vector.timeframe_start.isoformat()
                        if vector.timeframe_start
                        else None,
                        "timeframe_end": vector.timeframe_end.isoformat()
                        if vector.timeframe_end
                        else None,
                        "notes": vector.notes,
                        "mentions_in": vector.connections.get("mentions_in", []),
                        "grounded_by": vector.connections.get("grounded_by", []),
                    },
                )

                record = await result.single()
                return Result.ok(record["uid"])

        except Exception as e:
            self.logger.error(f"Failed to create vector: {e}")
            return Result.fail(
                Errors.database(operation="create_vector", message=str(e), entity="vector")
            )

    async def create_vectorized_edge(
        self, origin_uid: str, target_uid: str, vector: Vector, relationship_type: str = "MOVES_TO"
    ) -> Result[bool]:
        """
        Create a vectorized relationship between nodes.

        Args:
            origin_uid: UID of origin node,
            target_uid: UID of target node,
            vector: Vector describing the transition,
            relationship_type: Type of relationship

        Returns:
            Result indicating success
        """
        query = f"""
        MERGE (a {{uid: $origin}})
        MERGE (b {{uid: $target}})
        MERGE (a)-[r:{relationship_type}]->(b)
        SET r.space = $space,
            r.components = $components,
            r.magnitude = $magnitude,
            r.timeframe_start = $timeframe_start,
            r.timeframe_end = $timeframe_end,
            r.notes = $notes,
            r.updated_at = datetime()
        RETURN r
        """

        try:
            async with self.driver.session() as session:
                await session.run(
                    query,
                    {
                        "origin": origin_uid,
                        "target": target_uid,
                        "space": vector.space.value,
                        "components": vector.components,
                        "magnitude": vector.magnitude,
                        "timeframe_start": vector.timeframe_start.isoformat()
                        if vector.timeframe_start
                        else None,
                        "timeframe_end": vector.timeframe_end.isoformat()
                        if vector.timeframe_end
                        else None,
                        "notes": vector.notes,
                    },
                )
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to create vectorized edge: {e}")
            return Result.fail(
                Errors.database(
                    operation="create_vectorized_edge", message=str(e), entity="relationship"
                )
            )

    async def compute_resultant(self, vector_uids: list[str], space: VectorSpace) -> Result[Vector]:
        """
        Compute the resultant vector from multiple influences.

        Args:
            vector_uids: UIDs of vectors to combine,
            space: The conceptual space

        Returns:
            Result containing the resultant vector
        """
        # Fetch vectors and aggregate in Python (no APOC dependency)
        query = """
        MATCH (v:Vector)
        WHERE v.uid IN $uids AND v.space = $space
        RETURN v.components as components
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"uids": vector_uids, "space": space.value})
                records = [record async for record in result]

                if not records:
                    return Result.fail(
                        Errors.not_found(f"No vectors found with UIDs: {vector_uids}")
                    )

                # Sum components across all vectors in Python
                resultant_components: dict[str, float] = {}
                for record in records:
                    components = record["components"] or {}
                    for key, value in components.items():
                        resultant_components[key] = resultant_components.get(key, 0.0) + float(
                            value
                        )

                resultant = Vector(
                    uid=f"resultant-{datetime.now().isoformat()}",
                    title=f"Resultant of {len(records)} vectors",
                    space=space,
                    components=resultant_components,
                    notes=f"Computed from vectors: {', '.join(vector_uids)}",
                )

                return Result.ok(resultant)

        except Exception as e:
            self.logger.error(f"Failed to compute resultant: {e}")
            return Result.fail(
                Errors.database(operation="compute_resultant", message=str(e), entity="vector")
            )

    async def find_aligned_vectors(
        self, reference_vector: Vector, threshold: float = 0.7, limit: int = 10
    ) -> Result[list[dict[str, Any]]]:
        """
        Find vectors aligned with a reference vector.

        Uses cosine similarity to find alignment.

        Args:
            reference_vector: The reference vector,
            threshold: Minimum cosine similarity (0-1),
            limit: Maximum number of results

        Returns:
            Result containing list of aligned vectors with scores
        """
        # Normalize reference vector for cosine similarity
        ref_normalized = reference_vector.normalize()

        query = """
        MATCH (v:Vector)
        WHERE v.space = $space AND v.uid <> $ref_uid
        WITH v, v.components as components

        // Calculate dot product with reference
        WITH v,
             reduce(dot = 0.0, k IN keys($ref_components) |
                 dot + toFloat(coalesce(components[k], 0)) * toFloat($ref_components[k])
             ) as dot_product,
             sqrt(reduce(s = 0.0, val IN [x IN keys(components) | toFloat(components[x])] |
                 s + val * val
             )) as magnitude

        WHERE magnitude > 0
        WITH v, dot_product / magnitude as cosine_similarity
        WHERE cosine_similarity >= $threshold

        RETURN v.uid as uid,
               v.title as title,
               v.components as components,
               cosine_similarity as alignment_score
        ORDER BY alignment_score DESC
        LIMIT $limit
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "space": reference_vector.space.value,
                        "ref_uid": reference_vector.uid,
                        "ref_components": ref_normalized.components,
                        "threshold": threshold,
                        "limit": limit,
                    },
                )

                aligned = [
                    {
                        "uid": record["uid"],
                        "title": record["title"],
                        "components": dict(record["components"]),
                        "alignment_score": record["alignment_score"],
                    }
                    async for record in result
                ]

                return Result.ok(aligned)

        except Exception as e:
            self.logger.error(f"Failed to find aligned vectors: {e}")
            return Result.fail(
                Errors.database(operation="find_aligned_vectors", message=str(e), entity="vector")
            )

    async def track_vector_progress(
        self, vector_uid: str, current_position: dict[str, float]
    ) -> Result[dict[str, Any]]:
        """
        Track progress along a vector trajectory.

        Args:
            vector_uid: UID of the vector being tracked,
            current_position: Current position in the vector space

        Returns:
            Result containing progress metrics
        """
        query = """
        MATCH (v:Vector {uid: $uid})

        // Calculate projection of current position onto vector
        WITH v,
             reduce(dot = 0.0, k IN keys(v.components) |
                 dot + toFloat(coalesce($current[k], 0)) * toFloat(v.components[k])
             ) / (v.magnitude * v.magnitude) as projection_scalar

        RETURN v.uid as uid,
               v.title as title,
               v.components as vector_components,
               projection_scalar as progress,
               v.magnitude as vector_magnitude,
               v.target as target
        """

        try:
            async with self.driver.session() as session:
                result = await session.run(query, {"uid": vector_uid, "current": current_position})

                record = await result.single()
                if not record:
                    return Result.fail(Errors.not_found(f"Vector not found: {vector_uid}"))

                return Result.ok(
                    {
                        "vector_uid": record["uid"],
                        "vector_title": record["title"],
                        "progress_percentage": min(100, max(0, record["progress"] * 100)),
                        "projection_scalar": record["progress"],
                        "target": record["target"],
                    }
                )

        except Exception as e:
            self.logger.error(f"Failed to track vector progress: {e}")
            return Result.fail(
                Errors.database(operation="track_vector_progress", message=str(e), entity="vector")
            )
