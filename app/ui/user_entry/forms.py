"""
UserEntry Submit Form (ADR-054)
================================

Intent-driven upload form for ``/submit``. The student picks what they want
to accomplish — not which internal pipeline to run.

Three intent tiles (shown when no exercise is pre-selected):

- **Submit for Review**  → pipeline=TEACHER_REVIEW, audience=teachers/group
- **Get AI Feedback**    → pipeline=LLM_SUMMARY, audience=private
- **Log**                → pipeline=NONE, audience=private or public (portfolio)

When an exercise is pre-selected the tile picker is hidden and the form is
locked to TEACHER_REVIEW with the exercise's groups as the implied audience.

The ``POST /api/user-entries/upload`` endpoint translates the ``pipeline`` and
``audience`` hidden fields into the existing service-layer fields.

See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
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


def _intent_tile(
    value: str,
    label: str,
    description: str,
    hint: str | None = None,
) -> Any:
    """One intent selection tile."""
    return Label(
        Div(
            Input(
                type="radio",
                name="intent_choice",
                value=value,
                cls="mt-1 shrink-0",
                **{"x-model": "intent"},  # type: ignore[arg-type]
            ),
            Div(
                P(label, cls="text-sm font-semibold"),
                P(description, cls="text-xs text-muted-foreground mt-0.5"),
                P(hint, cls="text-xs text-amber-600 mt-1") if hint else None,
                cls="ml-3",
            ),
            cls="flex items-start",
        ),
        cls=(
            "block p-3 rounded-lg border border-border cursor-pointer "
            "hover:bg-muted/40 transition-colors"
            "[:has(input:checked)]:border-primary [:has(input:checked)]:bg-primary/5"
        ),
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
        force_pipeline: Lock the pipeline (exercise-context pages).
    """
    # The intent picker is locked only when a specific exercise is deep-linked
    # (selected_exercise_uid) or the caller forces a pipeline (force_pipeline).
    # Merely having assignments in the dropdown does NOT lock the form.
    hide_intent_picker = force_pipeline is not None or bool(selected_exercise_uid)
    effective_pipeline = force_pipeline or (
        Pipeline.TEACHER_REVIEW if selected_exercise_uid else Pipeline.NONE
    )

    # -- Exercise section --------------------------------------------------
    exercise_section: Any = ""
    if assigned_exercises:
        exercise_options = [Option("None — standalone entry", value="")]

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

    # -- Audience options (computed before intent tiles reference them) -----
    # "Submit to teacher" maps to auto_share_to_exercise_groups=True in the API,
    # which only works when an exercise is selected. Without one it shares with
    # nothing, so only offer it when a specific exercise was deep-linked.
    teacher_audience_options: list[Any] = []
    if selected_exercise_uid:
        teacher_audience_options.append(
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
            teacher_audience_options.append(
                _audience_radio(
                    value=f"group:{guid}",
                    label=f"Share with {gname}",
                    description="Visible to members of this group.",
                    model="audience",
                )
            )

    # Show the Review intent tile only when there is a reachable recipient.
    show_review_intent = bool(selected_exercise_uid) or bool(teacher_audience_options)

    # -- Intent picker or locked pipeline ----------------------------------
    if hide_intent_picker:
        intent_section: Any = Input(
            type="hidden",
            name="pipeline",
            value=effective_pipeline.value,
            **{"x-ref": "pipelineField"},  # type: ignore[arg-type]
        )
        default_intent = "review"
    else:
        review_tile = (
            _intent_tile(
                "review",
                "Submit for Review",
                "Send to your teacher for feedback.",
            )
            if show_review_intent
            else None
        )
        intent_section = Div(
            P("What do you want to do with this entry?", cls="text-sm font-semibold mb-3"),
            Div(
                review_tile,
                _intent_tile(
                    "ai",
                    "Get AI Feedback",
                    "An AI will read and respond to your entry.",
                    hint="Works best with text or document files.",
                ),
                _intent_tile(
                    "log",
                    "Log",
                    "Save privately or add to your public portfolio.",
                ),
                cls="space-y-2",
            ),
            # Hidden field carries resolved pipeline to server
            Input(
                type="hidden",
                name="pipeline",
                **{"x-bind:value": "resolvedPipeline"},  # type: ignore[arg-type]
            ),
            cls="mb-4",
        )
        default_intent = "log"

    # Safe default audience for the $watch reset when switching to review intent.
    # "teachers" only if an exercise is selected; first group otherwise; 'private'
    # as a fallback (validation will block submit and surface the error).
    _first_group = next(
        (
            g
            for g in (user_groups or [])
            if (getattr(g, "uid", None) or getattr(g, "group_uid", None))
        ),
        None,
    )
    if selected_exercise_uid:
        _default_review_audience = "teachers"
    elif _first_group is not None:
        _fg_uid = getattr(_first_group, "uid", None) or getattr(_first_group, "group_uid", None)
        _default_review_audience = f"group:{_fg_uid}"
    else:
        _default_review_audience = "private"

    review_audience_section = Div(
        P("Send to", cls="text-sm font-semibold mb-2"),
        Div(*teacher_audience_options, cls="space-y-1"),
        Div(
            "Choose a recipient before submitting.",
            cls=(
                "text-xs text-destructive mt-2 p-2 rounded bg-destructive/10 "
                "border border-destructive/30"
            ),
            **{"x-show": "intent === 'review' && validationError", "x-cloak": True},
        ),
        cls="mb-4 p-3 border border-border rounded-lg bg-muted/30",
        **{"x-show": "intent === 'review'", "x-cloak": True},
    )

    # -- Audience section (log path: private vs portfolio) -----------------
    log_audience_section = Div(
        P("Visibility", cls="text-sm font-semibold mb-2"),
        Div(
            _audience_radio(
                value="private",
                label="Keep to myself",
                description="Only you can see this entry.",
                model="audience",
            ),
            _audience_radio(
                value="public",
                label="Add to my portfolio",
                description="Appears on your public profile.",
                model="audience",
            ),
            cls="space-y-1",
        ),
        cls="mb-4 p-3 border border-border rounded-lg bg-muted/30",
        **{"x-show": "intent === 'log'", "x-cloak": True},
    )

    # When locked to exercise context, audience is always "teachers" — single static input.
    # Otherwise: one hidden input bound to resolvedAudience (not per-section) so that
    # x-show sections in the DOM don't each submit a duplicate name="audience" field.
    if hide_intent_picker:
        audience_block: Any = Input(type="hidden", name="audience", value="teachers")
        audience_hidden: Any = ""
    else:
        audience_block = Div(
            review_audience_section,
            log_audience_section,
        )
        # Single source of truth for the submitted "audience" value.
        # resolvedAudience ensures AI intent always sends 'private' regardless of
        # which radio the user may have touched before switching intents.
        audience_hidden = Input(
            type="hidden",
            name="audience",
            **{"x-bind:value": "resolvedAudience"},  # type: ignore[arg-type]
        )

    teacher_review_pipeline = Pipeline.TEACHER_REVIEW.value
    llm_summary_pipeline = Pipeline.LLM_SUMMARY.value

    alpine_data = (
        "{ "
        f"intent: '{default_intent}', "
        f"audience: '{'teachers' if hide_intent_picker else 'private'}', "
        "validationError: false, "
        f"get resolvedPipeline() {{ "
        f"  if (this.intent === 'review') return '{teacher_review_pipeline}'; "
        f"  if (this.intent === 'ai') return '{llm_summary_pipeline}'; "
        "  return 'none'; "
        "}, "
        # AI always private; other intents use the selected radio value.
        "get resolvedAudience() { "
        "  if (this.intent === 'ai') return 'private'; "
        "  return this.audience; "
        "}, "
        # Reset audience to a valid default when the user switches intent, so a
        # stale 'public' from Log or 'teachers' from Review doesn't leak across.
        "init() { "
        "  this.$watch('intent', (val) => { "
        f"    if (val === 'review') this.audience = '{_default_review_audience}'; "
        "    else this.audience = 'private'; "
        "  }); "
        "}, "
        "validate(ev) { "
        # 'private' means no recipient was actively chosen in the review section.
        "  if (this.intent === 'review' && this.audience === 'private') { "
        "    this.validationError = true; ev.preventDefault(); return false; "
        "  } "
        "  this.validationError = false; return true; "
        "} "
        "}"
    )

    return Card(
        CardBody(
            Form(
                exercise_section,
                from_ps_field,
                intent_section,
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
                audience_block,
                audience_hidden,
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
