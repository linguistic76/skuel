"""
UserEntry Submit Form (ADR-054 Step 9)
=======================================

Single-screen upload form backing ``/submit``. One radio group — the
**audience selector** — replaces the previous four-checkbox matrix so a
student can complete a turn-in in one deliberate choice rather than three
interacting toggles.

The selector emits a single hidden ``audience`` field with one of:

- ``teachers``            — auto-share to the exercise's assigned groups
                            (shown only when an exercise is in context)
- ``group:<group_uid>``   — share with a specific group the student is in
- ``public``              — publish publicly (``visibility=PUBLIC``)
- ``private``             — keep to self (default when no exercise context)

``POST /api/user-entries/upload`` translates ``audience`` into the existing
``share_with_groups`` / ``auto_share_to_exercise_groups`` / ``visibility``
fields on ``UserEntryCreateRequest``. Client-side validation blocks submit
when the student has picked no option *and* the pipeline is
``TEACHER_REVIEW`` — a defense-in-depth layer above the service's ADR §3
guard and post-persist compensation.

See: /home/mike/.claude/plans/user-entry-audience-selection.md
"""

from typing import Any

from fasthtml.common import (
    Div,
    Form,
    NotStr,
    Option,
    P,
    Script,
)

from core.models.enums.pipeline import Pipeline
from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody
from ui.forms import Input, Label, Select

_PIPELINE_LABELS: dict[Pipeline, str] = {
    Pipeline.NONE: "None — store only",
    Pipeline.TRANSCRIBE: "Transcribe (audio \u2192 text)",
    Pipeline.TRANSCRIBE_AND_STRUCTURE: "Transcribe + structure (journal)",
    Pipeline.LLM_SUMMARY: "LLM summary",
    Pipeline.TEACHER_REVIEW: "Submit for teacher review",
}


def _audience_radio(value: str, label: str, description: str, model: str) -> Any:
    """One row in the audience radio group — label, sublabel, hit area."""
    return Label(
        Div(
            Input(
                type="radio",
                name="audience_choice",
                value=value,
                cls="mr-3 mt-1",
                x_model=model,
            ),
            Div(
                P(label, cls="text-sm font-medium"),
                P(description, cls="text-xs text-muted-foreground"),
            ),
            cls="flex items-start",
        ),
        cls="block p-2 rounded cursor-pointer hover:bg-muted/50",
    )


def render_upload_form(
    assigned_exercises: list[Any] | None = None,
    selected_exercise_uid: str | None = None,
    from_ps: str | None = None,
    user_groups: list[Any] | None = None,
    force_pipeline: Pipeline | None = None,
) -> Any:
    """Render the UserEntry upload form.

    Args:
        assigned_exercises: Exercises the user can link to. When non-empty,
            a dropdown is rendered.
        selected_exercise_uid: Pre-selected exercise (deep-link). Also
            forces the pipeline to ``TEACHER_REVIEW`` unless overridden.
        from_ps: PathStep UID for the ``Interaction`` audit record.
        user_groups: The user's groups (pre-loaded by the route handler).
            Each element may be a ``Group`` dataclass or duck-typed object
            with ``.uid`` and ``.name``.
        force_pipeline: Lock the pipeline (exercise-context + journal pages).
    """
    from_exercise_context = bool(selected_exercise_uid) or bool(assigned_exercises)
    effective_pipeline = force_pipeline or (
        Pipeline.TEACHER_REVIEW if from_exercise_context else Pipeline.NONE
    )
    hide_pipeline_selector = force_pipeline is not None or from_exercise_context

    # -- Exercise section --------------------------------------------------
    exercise_section: Any = ""
    if assigned_exercises:
        exercise_options = [Option("None \u2014 standalone entry", value="")]

        def _exercise_option(p: Any) -> Any:
            uid = p.uid
            label = getattr(p, "title", None) or getattr(p, "name", None) or uid
            return Option(label, value=uid, selected=(uid == selected_exercise_uid))

        exercise_options.extend(_exercise_option(p) for p in assigned_exercises)
        exercise_section = Div(
            Label("Exercise (optional)", cls="label"),
            Select(*exercise_options, name="fulfills_exercise_uid"),
            P(
                "Link this entry to a teacher exercise",
                cls="text-xs text-muted-foreground mt-1",
            ),
            cls="mb-4",
        )
    elif selected_exercise_uid:
        exercise_section = Input(
            type="hidden",
            name="fulfills_exercise_uid",
            value=selected_exercise_uid,
        )

    from_ps_field: Any = (
        Input(type="hidden", name="about_path_step_uid", value=from_ps) if from_ps else ""
    )

    # -- Pipeline selector -------------------------------------------------
    if hide_pipeline_selector:
        pipeline_section: Any = Input(
            type="hidden",
            name="pipeline",
            value=effective_pipeline.value,
            x_ref="pipelineField",
        )
    else:
        pipeline_options = [
            Option(
                _PIPELINE_LABELS[p],
                value=p.value,
                selected=(p == effective_pipeline),
            )
            for p in Pipeline
        ]
        pipeline_section = Div(
            Label("Pipeline", cls="label"),
            Select(
                *pipeline_options,
                name="pipeline",
                x_model="pipeline",
            ),
            P(
                "Choose what happens to this entry after upload",
                cls="text-xs text-muted-foreground mt-1",
            ),
            cls="mb-4",
        )

    # -- Audience radio group ---------------------------------------------
    #
    # Options are ordered for the dominant use case: from an exercise page
    # the student nearly always wants "Submit to teacher", so it's first +
    # pre-selected. From a standalone /submit page "Keep to myself" wins.
    audience_options: list[Any] = []

    if from_exercise_context:
        audience_options.append(
            _audience_radio(
                value="teachers",
                label="Submit to teacher",
                description="Shares with the exercise's assigned groups.",
                model="audience",
            )
        )

    if user_groups:
        for g in user_groups:
            guid = getattr(g, "uid", None) or getattr(g, "group_uid", None)
            if not guid:
                continue
            gname = getattr(g, "name", None) or getattr(g, "title", None) or guid
            audience_options.append(
                _audience_radio(
                    value=f"group:{guid}",
                    label=f"Share with {gname}",
                    description="Visible to members of this group.",
                    model="audience",
                )
            )

    audience_options.append(
        _audience_radio(
            value="public",
            label="Publish publicly",
            description="Visible to everyone on your public portfolio.",
            model="audience",
        )
    )
    audience_options.append(
        _audience_radio(
            value="private",
            label="Keep to myself",
            description="Only you can see this entry.",
            model="audience",
        )
    )

    audience_section = Div(
        P("Audience", cls="text-sm font-semibold mb-2"),
        Div(*audience_options, cls="space-y-1"),
        Div(
            "Choose who sees this entry before submitting.",
            cls=(
                "text-xs text-destructive mt-2 p-2 rounded bg-destructive/10 "
                "border border-destructive/30"
            ),
            **{"x-show": "validationError", "x-cloak": True},
        ),
        # One hidden field carries the choice to the server.
        Input(
            type="hidden",
            name="audience",
            **{"x-bind:value": "audience"},  # type: ignore[arg-type]  # fasthtml dynamic-attr splat
        ),
        cls="mb-4 p-3 border border-border rounded-lg bg-muted/30",
        # Pipeline.allows_sharing() mirrored client-side: journal (TRANSCRIBE_AND_STRUCTURE)
        # is PRIVATE by policy (ADR-054 §5), so the picker is hidden when selected.
        **{"x-show": "allowsSharing", "x-cloak": True},
    )

    default_audience = "teachers" if from_exercise_context else "private"
    non_sharing_pipeline = Pipeline.TRANSCRIBE_AND_STRUCTURE.value

    alpine_data = (
        "{ "
        f"pipeline: '{effective_pipeline.value}', "
        f"audience: '{default_audience}', "
        "validationError: false, "
        f"get allowsSharing() {{ return this.pipeline !== '{non_sharing_pipeline}'; }}, "
        "get audienceOk() { "
        "  if (!this.allowsSharing) return true; "
        "  if (this.pipeline !== 'teacher_review') return true; "
        "  return !!this.audience; "
        "}, "
        "validate(ev) { "
        "  if (!this.allowsSharing) { this.audience = 'private'; } "
        "  if (!this.audienceOk) { this.validationError = true; ev.preventDefault(); return false; } "
        "  this.validationError = false; return true; "
        "} "
        "}"
    )

    return Card(
        CardBody(
            Form(
                exercise_section,
                from_ps_field,
                pipeline_section,
                Div(
                    Label(
                        Div(
                            P("Select File", cls="text-center mb-0"),
                            P(
                                "Click to browse for files (audio, text, PDF, images, video)",
                                cls="text-sm text-muted-foreground text-center mt-0",
                            ),
                            cls=(
                                "p-4 text-center bg-muted rounded-lg cursor-pointer "
                                "border-2 border-dashed border-border"
                            ),
                        ),
                        Input(
                            type="file",
                            name="file",
                            accept="audio/*,text/*,.pdf,.doc,.docx,image/*,video/*",
                            cls="hidden",
                        ),
                        cls="w-full cursor-pointer",
                    ),
                    cls="mb-4",
                ),
                audience_section,
                Div(
                    Button(
                        "Submit",
                        variant=ButtonT.primary,
                        type="submit",
                    ),
                    cls="text-center",
                ),
                Div(id="upload-status", cls="mt-4 text-center"),
                hx_post="/api/user-entries/upload",
                hx_target="#upload-status",
                hx_swap="innerHTML",
                hx_encoding="multipart/form-data",
                id="user-entry-upload-form",
                **{
                    "x-data": alpine_data,
                    "@submit": "validate($event)",
                },
            ),
        ),
        cls="bg-background shadow-sm hover:shadow-md transition-shadow",
    )


def upload_form_script() -> Any:
    """HTMX UX polish — disable-while-submitting + form reset on success."""
    return Script(
        NotStr("""
        document.body.addEventListener('htmx:beforeRequest', function(evt) {
            var form = evt.detail.elt;
            if (form && form.id === 'user-entry-upload-form') {
                var btn = form.querySelector('button[type="submit"]');
                if (btn) { btn.disabled = true; btn.textContent = 'Uploading...'; }
            }
        });

        document.body.addEventListener('htmx:afterRequest', function(evt) {
            var form = evt.detail.elt;
            if (form && form.id === 'user-entry-upload-form') {
                if (evt.detail.successful) { form.reset(); }
                var btn = form.querySelector('button[type="submit"]');
                if (btn) { btn.disabled = false; btn.textContent = 'Submit'; }
                var grid = document.getElementById('submissions-grid-container');
                if (grid) { htmx.trigger(grid, 'load'); }
            }
        });
    """)
    )
