"""Progress metric pattern for displaying named progress bars.

Shows a labeled progress bar with automatic color coding based on
configurable thresholds. Used for ZPD scores, alignment percentages,
streaks, and system health metrics.
"""

from typing import Any

from fasthtml.common import Div, Span

from ui.feedback import Progress, ProgressT


def ProgressMetric(
    name: str,
    value: float,
    max_value: float = 1.0,
    show_percentage: bool = True,
    color_threshold_fn: Any = None,
) -> Div:
    """Named progress bar with automatic color coding.

    Args:
        name: Metric name/label
        value: Current value (0.0 to max_value)
        max_value: Maximum value (default 1.0 for percentages)
        show_percentage: Display percentage next to name
        color_threshold_fn: Optional function(value) -> ProgressT variant

    Returns:
        Div with labeled progress bar

    Example:
        ProgressMetric("Data Quality", 0.88)
        ProgressMetric("Tasks Complete", 12, max_value=20)
    """
    percentage = (value / max_value) * 100 if max_value > 0 else 0

    if color_threshold_fn:
        progress_variant = color_threshold_fn(value)
    else:
        progress_variant = (
            ProgressT.success
            if percentage >= 80
            else ProgressT.warning
            if percentage >= 60
            else ProgressT.error
        )

    return Div(
        Div(
            Span(name, cls="font-medium"),
            Span(f"{percentage:.0f}%", cls="text-sm text-muted-foreground")
            if show_percentage
            else None,
            cls="flex justify-between mb-1",
        ),
        Progress(value=int(percentage), variant=progress_variant),
        cls="mb-4",
    )
