"""
UserEntry Submit Form (ADR-054 Step 9)
=======================================

Rewritten from ``ui/submissions/forms.py::render_upload_form`` with two
first-class additions:

- **Audience section** — students declare who sees the entry at submit
  time (teacher, group, peer, public). No implicit role-based inference.
- **Pipeline selector** — drives the processing dispatcher. Hidden and
  forced to ``TEACHER_REVIEW`` when reached from an exercise context;
  visible ``<select>`` on the general ``/user-entries/new`` page; forced
  to ``TRANSCRIBE_AND_STRUCTURE`` for the journal audio surface.

Client-side validation (Alpine.js) prevents silent no-audience turn-ins:
when ``pipeline == TEACHER_REVIEW``, at least one audience must be
selected or ``visibility`` must be ``PUBLIC``.

Posts to the new ``POST /api/user-entries/upload`` endpoint — the multipart
boundary that accepts audience + pipeline fields.

See: /home/mike/.claude/plans/woolly-weaving-hejlsberg.md § Step 9
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

# ---------------------------------------------------------------------------
# Pipeline option labels (shown in the general-page <select>)
# ---------------------------------------------------------------------------

_PIPELINE_LABELS: dict[Pipeline, str] = {
    Pipeline.NONE: "None — store only",
    Pipeline.TRANSCRIBE: "Transcribe (audio \u2192 text)",
    Pipeline.TRANSCRIBE_AND_STRUCTURE: "Transcribe + structure (journal)",
    Pipeline.LLM_SUMMARY: "LLM summary",
    Pipeline.TEACHER_REVIEW: "Submit for teacher review",
}


def render_upload_form(
    assigned_exercises: list[Any] | None = None,
    selected_exercise_uid: str | None = None,
    from_ps: str | None = None,
    user_groups: list[Any] | None = None,
    force_pipeline: Pipeline | None = None,
) -> Any:
    """Render the UserEntry upload form card.

    Args:
        assigned_exercises: Exercises the user can link to. When non-empty,
            a dropdown is rendered. When empty but ``selected_exercise_uid``
            is set, a hidden field carries the UID through.
        selected_exercise_uid: Pre-selected exercise (deep-link from an
            exercise page). Also forces the pipeline to ``TEACHER_REVIEW``
            unless ``force_pipeline`` overrides it.
        from_ps: PathStep UID for the ``Interaction`` audit record.
        user_groups: The user's groups (from ``UserContext.groups``).
            Rendered in the group-share dropdown when present.
        force_pipeline: Lock the pipeline to a specific value and hide the
            selector. Used by the exercise-context and journal-audio pages.

    The form posts to ``POST /api/user-entries/upload`` (multipart) — the
    new UserEntry boundary introduced in Step 7.
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

    # PathStep context carried through as the Interaction anchor
    from_ps_field: Any = (
        Input(type="hidden", name="about_path_step_uid", value=from_ps) if from_ps else ""
    )

    # -- Pipeline selector -------------------------------------------------
    if hide_pipeline_selector:
        pipeline_section: Any = Input(
            type="hidden",
            name="pipeline",
            value=effective_pipeline.value,
            **{"x-ref": "pipelineField"},
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
                **{"x-model": "pipeline"},
            ),
            P(
                "Choose what happens to this entry after upload",
                cls="text-xs text-muted-foreground mt-1",
            ),
            cls="mb-4",
        )

    # -- Audience section --------------------------------------------------
    group_options: list[Any] = [Option("\u2014 select a group \u2014", value="")]
    if user_groups:
        for g in user_groups:
            guid = getattr(g, "uid", None) or getattr(g, "group_uid", None)
            if not guid:
                continue
            gname = getattr(g, "name", None) or getattr(g, "title", None) or guid
            group_options.append(Option(gname, value=guid))

    audience_section = Div(
        P("Audience", cls="text-sm font-semibold mb-2"),
        # Submit to teacher (auto-share to exercise groups on the server)
        Div(
            Label(
                Input(
                    type="checkbox",
                    cls="mr-2",
                    **{"x-model": "sendToTeacher"},
                ),
                "Submit to teacher",
                cls="flex items-center cursor-pointer",
            ),
            P(
                "Shares with the exercise's assigned groups.",
                cls="text-xs text-muted-foreground ml-6",
            ),
            cls="mb-2",
        ),
        # Share with group
        Div(
            Label(
                Input(
                    type="checkbox",
                    cls="mr-2",
                    **{"x-model": "shareGroup"},
                ),
                "Share with group\u2026",
                cls="flex items-center cursor-pointer",
            ),
            Div(
                Select(
                    *group_options,
                    cls="mt-1",
                    **{"x-model": "shareGroupUid", "x-show": "shareGroup"},
                ),
                cls="ml-6",
            )
            if user_groups
            else Div(
                Input(
                    type="text",
                    placeholder="Group UID",
                    cls="mt-1",
                    **{"x-model": "shareGroupUid", "x-show": "shareGroup"},
                ),
                cls="ml-6",
            ),
            cls="mb-2",
        ),
        # Share with peer
        Div(
            Label(
                Input(
                    type="checkbox",
                    cls="mr-2",
                    **{"x-model": "sharePeer"},
                ),
                "Share with a peer\u2026",
                cls="flex items-center cursor-pointer",
            ),
            Div(
                Input(
                    type="text",
                    placeholder="Peer user UID",
                    cls="mt-1",
                    **{"x-model": "sharePeerUid", "x-show": "sharePeer"},
                ),
                cls="ml-6",
            ),
            cls="mb-2",
        ),
        # Publish publicly
        Div(
            Label(
                Input(
                    type="checkbox",
                    cls="mr-2",
                    **{"x-model": "publishPublic"},
                ),
                "Publish publicly",
                cls="flex items-center cursor-pointer",
            ),
            P(
                "Visible to everyone on your public portfolio.",
                cls="text-xs text-muted-foreground ml-6",
            ),
            cls="mb-2",
        ),
        # Validation banner — only shown when the submit handler refused
        Div(
            "Select at least one audience before submitting for teacher review.",
            cls=(
                "text-xs text-destructive mt-2 p-2 rounded bg-destructive/10 "
                "border border-destructive/30"
            ),
            **{"x-show": "validationError", "x-cloak": True},
        ),
        # Hidden fields bound to Alpine state — consumed by the upload route.
        # ``auto_share_to_exercise_groups`` is an explicit boolean: the server
        # resolves the exercise's assigned groups instead of trusting a
        # client-synthesized sentinel value.
        Input(
            type="hidden",
            name="share_with_groups",
            **{"x-bind:value": "shareGroup && shareGroupUid ? shareGroupUid : ''"},
        ),
        Input(
            type="hidden",
            name="share_with_users",
            **{"x-bind:value": "sharePeer && sharePeerUid ? sharePeerUid : ''"},
        ),
        Input(
            type="hidden",
            name="auto_share_to_exercise_groups",
            **{"x-bind:value": "sendToTeacher ? 'true' : 'false'"},
        ),
        Input(
            type="hidden",
            name="visibility",
            **{"x-bind:value": "publishPublic ? 'public' : 'private'"},
        ),
        cls="mb-4 p-3 border border-border rounded-lg bg-muted/30",
    )

    # -- Alpine component state --------------------------------------------
    alpine_data = (
        "{ "
        f"pipeline: '{effective_pipeline.value}', "
        f"sendToTeacher: {str(from_exercise_context).lower()}, "
        "shareGroup: false, shareGroupUid: '', "
        "sharePeer: false, sharePeerUid: '', "
        "publishPublic: false, "
        "validationError: false, "
        "get audienceOk() { "
        "  if (this.pipeline !== 'teacher_review') return true; "
        "  return this.sendToTeacher || "
        "    (this.shareGroup && this.shareGroupUid) || "
        "    (this.sharePeer && this.sharePeerUid) || "
        "    this.publishPublic; "
        "}, "
        "validate(ev) { "
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
    """HTMX UX polish for the user-entry upload form.

    Disables the submit button while the request is in flight and resets
    the form on success. Paired with the Alpine component in
    ``render_upload_form``.
    """
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
