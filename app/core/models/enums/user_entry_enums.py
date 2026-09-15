"""
Reports Enums - Processing and Scheduling
===========================================

Enums for report processing pipelines, LLM configuration,
and scheduling scope.
"""

from enum import StrEnum


class SubmissionModality(StrEnum):
    """
    Format of submission expected by an Exercise or used by a UserEntry.

    FILE_UPLOAD: Student uploads a file (audio, PDF, document, image)
    STRUCTURED_FORM: Student fills out an inline form defined by Exercise.form_schema
    """

    FILE_UPLOAD = "file_upload"
    STRUCTURED_FORM = "structured_form"


class ExerciseScope(StrEnum):
    """
    Scope of an exercise (instruction template) — who the template is for, and who owns it.

    PERSONAL: User's own AI feedback template (default) — always OWNS-linked to a real user
    ASSIGNED: Teacher-created, assigned to a group (ADR-040)
    ASSESSMENT: Formal test/exam with scoring rubric and pass/fail criteria
    CURRICULUM: Owned by the curriculum itself, for everyone — authored in the content
        vault, no user OWNS edge. Anchored to PathSteps via HAS_EXERCISE
        (``exercise_uids`` in PathStep YAML frontmatter). Not creatable via the API.
    """

    PERSONAL = "personal"
    ASSIGNED = "assigned"
    ASSESSMENT = "assessment"
    CURRICULUM = "curriculum"


class EnrichmentMode(StrEnum):
    """Processing strategy for journal LLM enrichment.

    ACTIVITY_TRACKING: Extract and structure daily activities (default)
    IDEA_ARTICULATION: Develop and refine ideas from raw thoughts
    CRITICAL_THINKING: Explore topics with analytical depth
    """

    ACTIVITY_TRACKING = "activity_tracking"
    IDEA_ARTICULATION = "idea_articulation"
    CRITICAL_THINKING = "critical_thinking"


class ParseDoor(StrEnum):
    """Which door parsed an activity line out of a note — one vocabulary per line.

    A line carrying ``@context(...)`` is a DSL line (``ActivityDSLParser.parse_line``):
    schedule and priority come from ``@when()`` / ``@priority()``, and the
    obsidian-tasks metadata emoji stay literal text. Any other checkbox line is an
    obsidian-tasks line (``obsidian_task_line_to_parsed``): ``📅`` due, ``⏳``
    scheduled, priority emoji and ``#tags`` are interpreted. The ``🆔 sk_*`` join key
    is read on both. DSL_USAGE_GUIDE § The Parse Contract is the authority; a consumer
    acting on the obsidian-tasks fields — the vault reconciler — acts on them only for a
    line this door produced.
    """

    DSL = "dsl"
    OBSIDIAN_TASKS = "obsidian_tasks"

    @property
    def interprets_task_metadata(self) -> bool:
        """Whether 📅 / ⏳ / priority emoji / ``#tags`` on the line are fields, not text."""
        return self is ParseDoor.OBSIDIAN_TASKS


class CheckboxVerdict(StrEnum):
    """What a recognised vault line's checkbox asked of its task (ADR-070 Decision 3, R4).

    The three-way merge of the checkbox — base (the line as SKUEL last saw it),
    theirs (the line now), ours (the task) — lands on exactly one of these:

    UNCHANGED: the vault did not touch the box; SKUEL's state stands, and the
        outbound pass writes it back (a completion made in SKUEL keeps its
        ``[x] ✅``, a reopen made in SKUEL un-checks the line).
    COMPLETED: the vault checked an open (or cancelled) task — completed on the
        line's ``✅`` date, today when the tick carries none.
    REDATED: both sides completed and the vault's ``✅`` date is the later one,
        or the vault alone moved the date of a completion — the task is re-dated,
        no completion event fires.
    REOPENED: the vault un-checked a completed task.
    STANDS: the vault touched the box but SKUEL's state stands — a tie or an
        earlier vault date on a completion both sides made, a dateless tick on a
        task SKUEL already completed, or ``[ ]`` on a cancelled task (a cancel is
        SKUEL's decision; the line diverges visibly until the user acts on it).
    """

    UNCHANGED = "unchanged"
    COMPLETED = "completed"
    REDATED = "redated"
    REOPENED = "reopened"
    STANDS = "stands"


class ReportPeriodKind(StrEnum):
    """How an activity report's window is anchored.

    TRAILING windows end now (``7d`` … ``90d``); WEEK and MONTH are calendar
    periods addressed by a period key (``2026-W37``, ``2026-09``) — their end is
    fixed, and a report generated before it is partial.
    """

    TRAILING = "trailing"
    WEEK = "week"
    MONTH = "month"

    @property
    def is_calendar(self) -> bool:
        """A period with a fixed end — the one kind a report can be partial for."""
        return self is not ReportPeriodKind.TRAILING


class ProgressDepth(StrEnum):
    """Level of detail in generated progress reports."""

    SUMMARY = "summary"
    STANDARD = "standard"
    DETAILED = "detailed"

    def get_display_name(self) -> str:
        """Get human-readable display name."""
        return {
            ProgressDepth.SUMMARY: "Summary (counts only)",
            ProgressDepth.STANDARD: "Standard (counts + examples)",
            ProgressDepth.DETAILED: "Detailed (full breakdown)",
        }[self]
