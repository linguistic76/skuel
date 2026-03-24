"""
Completion Export Formatters
============================

Pure data-formatting functions for exporting HabitCompletion records
to CSV and JSON. Separated from domain logic per SoC.
"""

import csv
import json
from io import StringIO

from core.models.habit.completion import HabitCompletion


def export_completions_csv(completions: list[HabitCompletion]) -> str:
    """Format completions as a CSV string."""
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(
        [
            "Completion ID",
            "Habit ID",
            "Completed At",
            "Quality",
            "Duration (min)",
            "Notes",
            "Created At",
        ]
    )

    for c in completions:
        writer.writerow(
            [
                c.uid,
                c.habit_uid,
                c.completed_at.isoformat(),
                c.quality or "",
                c.duration_actual or "",
                c.notes or "",
                c.created_at.isoformat(),
            ]
        )

    return output.getvalue()


def export_completions_json(completions: list[HabitCompletion]) -> str:
    """Format completions as a JSON string."""
    data = [
        {
            "uid": c.uid,
            "habit_uid": c.habit_uid,
            "completed_at": c.completed_at.isoformat(),
            "quality": c.quality,
            "duration_actual": c.duration_actual,
            "notes": c.notes,
            "created_at": c.created_at.isoformat(),
        }
        for c in completions
    ]

    return json.dumps(data, indent=2)
