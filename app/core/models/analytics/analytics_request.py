"""
Analytics Request Models (Tier 1 - External)
=============================================

Pydantic models for analytics API validation and serialization.
Handles input validation at the API boundary for analytics tracking and monitoring.
"""

from typing import Any

from pydantic import BaseModel, Field


class TrackQueryRequest(BaseModel):
    """Request to track a query execution."""

    query: str = Field(..., description="Query text that was executed")

    execution_time: float = Field(..., description="Execution time in seconds")

    result_count: int = Field(..., description="Number of results returned")

    intent: str | None = Field(
        None, description="Detected query intent (e.g., 'search', 'filter', 'aggregate')"
    )

    cache_hit: bool = Field(False, description="Whether the query result was served from cache")

    results_metadata: dict[str, Any] | None = Field(
        default_factory=dict,
        description="Additional metadata about query results (domains, relationships, etc.)",
    )


# Future analytics request models can be added here:
# - MetricsFilterRequest
# - TrendAnalysisRequest
# - GapAnalysisRequest
# etc.
