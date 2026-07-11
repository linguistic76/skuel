"""
Prerequisite-Edge Suggestion Queue Components
=============================================

UI for /admin/prereq-suggestions (Discovery Analytics PR 4): an interactive
admin queue — generate suggestions on demand, review each candidate pair,
approve into an Edge YAML file in the content vault, or reject client-side
(stateless v1: a rejected suggestion simply reappears on regeneration).

FULL tier: rows arrive pre-classified by the LLM judge (verdict + one-line
rationale) with the judged direction preselected. CORE tier: undirected
pairs — the admin chooses relation + direction himself before approving.

Usage:
    from ui.admin.prereq_views import AdminPrereqComponents
"""

from typing import Any

from fasthtml.common import Div, Form, Input, Option, P, Span

from core.services.prereq_suggestion_service import (
    JudgeVerdict,
    PrereqSuggestion,
    PrereqSuggestionRun,
)
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle, Loading
from ui.forms import Select

#: Queue-form choice values → human labels. The route maps these to
#: (from_uid, to_uid, relationship) — see admin_dashboard_ui.APPROVE_CHOICES.
CHOICE_PREREQ_A_TO_B = "prereq_a_to_b"
CHOICE_PREREQ_B_TO_A = "prereq_b_to_a"
CHOICE_RELATED = "related"
CHOICE_COMPLEMENTARY = "complementary"


class AdminPrereqComponents:
    """Components for the prerequisite-edge suggestion queue."""

    @staticmethod
    def render_page(judge_available: bool) -> Div:
        """The queue page shell: explanation, generate button, empty queue target."""
        judge_line = (
            "Each pair is classified by the LLM judge (prerequisite direction, "
            "related, or skip) with a one-line rationale — review and approve below."
            if judge_available
            else "LLM judge unavailable (CORE tier) — pairs are undirected; choose "
            "the relation and direction yourself before approving."
        )
        return Div(
            Card(
                CardHeader(CardTitle("Prerequisite-Edge Suggestions")),
                CardBody(
                    P(
                        "Candidate Ku pairs from mid-band embedding similarity "
                        "(unedged, not transitively covered by an authored path). "
                        "Approving writes ONE Edge YAML file into the content vault's "
                        "edges/ directory — the edge lands in the graph on the next "
                        "content-vault sync. Nothing here writes to the graph directly.",
                        cls="text-sm text-muted-foreground mb-2",
                    ),
                    P(judge_line, cls="text-sm text-muted-foreground mb-4"),
                    Form(
                        Button("Generate suggestions", type="submit", cls=ButtonT.primary),
                        Loading(size="sm", id="prereq-spinner", cls="htmx-indicator ml-3"),
                        Span(
                            "Computed on demand — the LLM judge can take a minute.",
                            cls="text-xs text-muted-foreground ml-3",
                        ),
                        hx_post="/admin/prereq-suggestions/generate",
                        hx_target="#prereq-queue",
                        hx_swap="innerHTML",
                        hx_indicator="#prereq-spinner",
                        cls="flex items-center gap-2",
                    ),
                ),
                cls="mb-6",
            ),
            Div(id="prereq-queue"),
        )

    @staticmethod
    def render_queue(run: PrereqSuggestionRun) -> Div:
        """The generated suggestion list (HTMX fragment for #prereq-queue)."""
        if not run.suggestions:
            detail = (
                f"{run.candidate_count} candidate pair(s) generated; "
                f"{run.skipped_by_judge} skipped by the judge, "
                f"{run.judge_failures} lost to judge failures."
                if run.judged
                else "No candidate pairs in the similarity band."
            )
            return Div(
                P("No suggestions to review.", cls="text-sm font-medium"),
                P(detail, cls="text-sm text-muted-foreground"),
            )

        summary = (
            f"{len(run.suggestions)} suggestion(s) from {run.candidate_count} candidate pair(s)"
        )
        if run.judged:
            summary += (
                f" — LLM-judged ({run.skipped_by_judge} skipped"
                + (f", {run.judge_failures} judge failures" if run.judge_failures else "")
                + ")"
            )
        else:
            summary += " — unjudged: choose relation + direction per row"

        return Div(
            P(summary, cls="text-sm text-muted-foreground mb-3"),
            *(
                AdminPrereqComponents.render_suggestion_row(s, i)
                for i, s in enumerate(run.suggestions)
            ),
        )

    @staticmethod
    def render_suggestion_row(suggestion: PrereqSuggestion, index: int) -> Any:
        """One reviewable pair: titles, similarity, rationale, approve form, reject."""
        s = suggestion
        preselect = (
            {
                JudgeVerdict.PREREQ_A_TO_B: CHOICE_PREREQ_A_TO_B,
                JudgeVerdict.PREREQ_B_TO_A: CHOICE_PREREQ_B_TO_A,
                JudgeVerdict.RELATED: CHOICE_RELATED,
            }.get(s.verdict)
            if s.verdict
            else None
        )

        # Unjudged row (CORE mode or judge skip): a disabled placeholder keeps
        # the browser from silently submitting the first option — approving
        # without an explicit choice would write an arbitrary DIRECTED edge.
        placeholder = (
            [Option("Choose relation…", value="", selected=True, disabled=True)]
            if preselect is None
            else []
        )
        options = placeholder + [
            Option(
                f"Prerequisite: {s.a_title} → {s.b_title}",
                value=CHOICE_PREREQ_A_TO_B,
                selected=preselect == CHOICE_PREREQ_A_TO_B,
            ),
            Option(
                f"Prerequisite: {s.b_title} → {s.a_title}",
                value=CHOICE_PREREQ_B_TO_A,
                selected=preselect == CHOICE_PREREQ_B_TO_A,
            ),
            Option(
                "Related (undirected)",
                value=CHOICE_RELATED,
                selected=preselect == CHOICE_RELATED,
            ),
            Option("Complementary (undirected)", value=CHOICE_COMPLEMENTARY),
        ]

        rationale_line = (
            P(f"Judge: {s.rationale}", cls="text-sm italic text-muted-foreground mt-1")
            if s.rationale
            else None
        )

        return Div(
            Div(
                Span(s.a_title, cls="font-medium"),
                Span(" ↔ ", cls="text-muted-foreground"),
                Span(s.b_title, cls="font-medium"),
                Span(f" (cosine {s.similarity:.2f})", cls="text-xs text-muted-foreground ml-2"),
            ),
            P(f"{s.a_uid} ↔ {s.b_uid}", cls="text-xs text-muted-foreground"),
            rationale_line,
            Div(
                Form(
                    Input(type="hidden", name="a_uid", value=s.a_uid),
                    Input(type="hidden", name="b_uid", value=s.b_uid),
                    Input(type="hidden", name="a_title", value=s.a_title),
                    Input(type="hidden", name="b_title", value=s.b_title),
                    Input(type="hidden", name="rationale", value=s.rationale or ""),
                    Select(*options, name="choice", required=True, full_width=False, cls="text-sm"),
                    Button("Approve", type="submit", cls=(ButtonT.primary, "ml-2")),
                    hx_post="/admin/prereq-suggestions/approve",
                    hx_target="closest .prereq-row",
                    hx_swap="outerHTML",
                    cls="flex items-center gap-2",
                ),
                Button(
                    "Reject",
                    type="button",
                    cls=ButtonT.ghost,
                    **{"@click": "gone = true"},  # fasthtml dynamic-attr splat
                ),
                cls="flex items-center gap-3 mt-2",
            ),
            id=f"prereq-row-{index}",
            cls="prereq-row border border-border rounded-lg p-3 mb-2",
            x_data="{gone: false}",
            x_show="!gone",
        )

    @staticmethod
    def render_approved_row(filename: str, a_title: str, b_title: str) -> Div:
        """Replacement row after a successful approve (file written, not yet synced)."""
        return Div(
            P(
                Span("✅ Written ", cls="font-medium"),
                Span(f"edges/{filename}", cls="font-mono text-sm"),
                Span(f" — {a_title} / {b_title}. ", cls=""),
                Span(
                    "Lands in the graph on the next content-vault sync.",
                    cls="text-muted-foreground",
                ),
                cls="text-sm",
            ),
            cls="prereq-row border border-success/40 bg-success/5 rounded-lg p-3 mb-2",
        )

    @staticmethod
    def render_row_error(message: str, a_title: str = "", b_title: str = "") -> Div:
        """Replacement row on approve failure — regenerate to retry the pair."""
        pair = f"{a_title} / {b_title} — " if a_title or b_title else ""
        return Div(
            P(f"⚠ {pair}{message}", cls="text-sm text-destructive"),
            P(
                "Regenerate suggestions to retry this pair.",
                cls="text-xs text-muted-foreground",
            ),
            cls="prereq-row border border-destructive/40 rounded-lg p-3 mb-2",
        )
