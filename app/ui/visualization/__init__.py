"""Visualization adapters — transform domain data to library-specific formats.

Re-exports VisualizationService and its data structures for convenient import.
"""

from ui.visualization.visualization_service import (
    ChartConfig,
    ChartData,
    ChartDataset,
    GanttData,
    GanttTask,
    VisTimelineData,
    VisTimelineGroup,
    VisTimelineItem,
    VisualizationService,
)

__all__ = [
    "ChartConfig",
    "ChartData",
    "ChartDataset",
    "GanttData",
    "GanttTask",
    "VisualizationService",
    "VisTimelineData",
    "VisTimelineGroup",
    "VisTimelineItem",
]
