"""
Prerequisite-Edge Suggestion Queue Components
=============================================

UI for /admin/prereq-suggestions (Discovery Analytics PR 4): an interactive
admin queue — generate suggestions on demand, review each candidate pair, and
copy the ready Edge YAML file for the chosen relation into the content vault,
or reject client-side (a rejected suggestion simply reappears on
regeneration). The page writes nothing (ADR-091 N3).

FULL tier: rows arrive pre-classified by the LLM judge (verdict + one-line
rationale) with the judged direction preselected. CORE tier: undirected
pairs — the admin chooses relation + direction himself before copying.

Usage:
    from ui.admin.prereq_views import AdminPrereqComponents
"""

import json
from typing import Any

from fasthtml.common import Div, Form, Option, P, Pre, Span

from core.services.prereq_suggestion_service import (
    EdgeChoice,
    JudgeVerdict,
    PrereqSuggestion,
    PrereqSuggestionRun,
    ready_edge_files,
)
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle, Loading
from ui.forms import Select

#: The judge's verdict → the relation the row opens on.
_PRESELECT: dict[JudgeVerdict, EdgeChoice] = {
    JudgeVerdict.PREREQ_A_TO_B: EdgeChoice.PREREQ_A_TO_B,
    JudgeVerdict.PREREQ_B_TO_A: EdgeChoice.PREREQ_B_TO_A,
    JudgeVerdict.RELATED: EdgeChoice.RELATED,
}


class AdminPrereqComponents:
    """Components for the prerequisite-edge suggestion queue."""

    @staticmethod
    def render_page(judge_available: bool) -> Div:
        """The queue page shell: explanation, generate button, empty queue target."""
        judge_line = (
            "Each pair is classified by the LLM judge (prerequisite direction, "
            "related, or skip) with a one-line rationale — review and copy below."
            if judge_available
            else "LLM judge unavailable (CORE tier) — pairs are undirected; choose "
            "the relation and direction yourself before copying."
        )
        return Div(
            Card(
                CardHeader(CardTitle("Prerequisite-Edge Suggestions")),
                CardBody(
                    P(
                        "Candidate Ku pairs from mid-band embedding similarity "
                        "(unedged, not transitively covered by an authored path). "
                        "Each row shows the Edge YAML file for the relation you choose: "
                        "copy it into the content vault's edges/ folder, and the edge "
                        "lands in the graph on the next content-vault sync. This page "
                        "writes nothing.",
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
        """One reviewable pair: titles, similarity, rationale, the ready file, copy, reject."""
        s = suggestion
        preselect = _PRESELECT.get(s.verdict) if s.verdict else None

        # Unjudged row (CORE mode or judge skip): a disabled placeholder keeps
        # the row from opening on an arbitrary DIRECTED edge — no file shows,
        # and copy stays off, until the admin chooses.
        placeholder = (
            [Option("Choose relation…", value="", selected=True, disabled=True)]
            if preselect is None
            else []
        )
        labels = {
            EdgeChoice.PREREQ_A_TO_B: f"Prerequisite: {s.a_title} → {s.b_title}",
            EdgeChoice.PREREQ_B_TO_A: f"Prerequisite: {s.b_title} → {s.a_title}",
            EdgeChoice.RELATED: "Related (undirected)",
            EdgeChoice.COMPLEMENTARY: "Complementary (undirected)",
        }
        options = [
            *placeholder,
            *(
                Option(label, value=choice.value, selected=preselect == choice)
                for choice, label in labels.items()
            ),
        ]

        files = ready_edge_files(s)
        alpine_data = (
            "{ gone: false, copied: false,"
            f" choice: {json.dumps(preselect.value if preselect else '')},"
            f" files: {json.dumps({f.choice.value: f.content for f in files})},"
            "  copy() { navigator.clipboard.writeText(this.files[this.choice])"
            "    .then(() => { this.copied = true;"
            "      setTimeout(() => this.copied = false, 2000); }); } }"
        )

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
                Select(
                    *options,
                    name="choice",
                    x_model="choice",
                    full_width=False,
                    cls="text-sm",
                ),
                Button(
                    "Copy file",
                    type="button",
                    cls=ButtonT.primary,
                    **{"@click": "copy()", ":disabled": "!choice"},  # fasthtml dynamic-attr splat
                ),
                Span(
                    "Copied!",
                    cls="text-xs text-success",
                    **{"x-show": "copied", "x-cloak": True},  # boundary: fasthtml-elements
                ),
                Button(
                    "Reject",
                    type="button",
                    cls=ButtonT.ghost,
                    **{"@click": "gone = true"},  # fasthtml dynamic-attr splat
                ),
                cls="flex flex-wrap items-center gap-3 mt-2",
            ),
            *(
                Div(
                    P(f"edges/{f.filename}", cls="font-mono text-xs mt-2"),
                    Pre(
                        f.content,
                        cls="font-mono text-xs whitespace-pre-wrap bg-muted rounded p-2 mt-1",
                    ),
                    **{
                        "x-show": f"choice === '{f.choice.value}'",
                        "x-cloak": True,
                    },  # boundary: fasthtml-elements
                )
                for f in files
            ),
            id=f"prereq-row-{index}",
            cls="prereq-row border border-border rounded-lg p-3 mb-2",
            x_data=alpine_data,
            x_show="!gone",
        )
