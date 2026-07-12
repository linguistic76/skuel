"""Journals UI — DNWF workflow page and HTMX stage fragments."""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    A,
    Button,
    Div,
    Form,
    Input,
    Label,
    P,
    Span,
    Textarea,
)

from ui.canon import CanonSourcesBlock
from ui.components import Button as StyledButton
from ui.components import ButtonT, Card, CardBody, CardHeader, CardTitle

if TYPE_CHECKING:
    from core.models.enums.user_enums import JournalMode
    from core.services.canon import CanonSource
    from core.services.journal.suggestion import SuggestedActivity

# ------------------------------------------------------------------
# Page (GET /journals)
# ------------------------------------------------------------------


def _LoadingIndicator() -> Any:
    return Div(
        P("Processing…", cls="text-sm text-muted-foreground mt-3"),
        id="journal-loading",
        cls="htmx-indicator",
    )


# ------------------------------------------------------------------
# Private chat helpers
# ------------------------------------------------------------------


def _UserBubble(text: str) -> Any:
    """Right-aligned user message bubble appended to #journal-thread."""
    return Div(
        Div(
            text,
            cls=(
                "max-w-[80%] bg-muted rounded-[20px] px-[18px] py-3"
                " text-[15px] leading-[1.6] text-foreground whitespace-pre-wrap"
            ),
        ),
        cls="flex justify-end py-2",
    )


def _AiBubble(label: str, text: str) -> Any:
    """Left-aligned AI response bubble with avatar, prose, and copy action.

    Each bubble carries its own Alpine copy-state scope — multiple bubbles
    in the same thread each manage their own clipboard toggle independently.
    """
    import json as _json

    from ui.components import Icon

    alpine_data = (
        "{ copied: false,"
        f" responseText: {_json.dumps(text)},"
        "  copy() { navigator.clipboard.writeText(this.responseText)"
        "    .then(() => { this.copied = true;"
        "      setTimeout(() => this.copied = false, 2000); }); } }"
    )

    return Div(
        # Avatar
        Div(
            "J",
            cls=(
                "w-[30px] h-[30px] rounded-full bg-foreground text-background"
                " flex items-center justify-center text-sm font-bold flex-shrink-0"
            ),
        ),
        # Content
        Div(
            Span(label, cls="text-[13px] font-semibold text-muted-foreground"),
            P(
                text,
                cls="text-[15px] leading-[1.75] text-foreground whitespace-pre-wrap mt-1",
            ),
            # Copy action
            Div(
                Button(
                    Icon("copy", size=15),
                    type="button",
                    aria_label="Copy response",
                    cls=(
                        "w-[30px] h-[30px] flex items-center justify-center rounded-[7px]"
                        " text-muted-foreground hover:bg-muted hover:text-foreground"
                        " transition-colors"
                    ),
                    **{"@click": "copy()"},  # boundary: fasthtml-elements
                ),
                Span(
                    "Copied!",
                    cls="text-xs text-green-600",
                    **{"x-show": "copied", "x-cloak": True},  # boundary: fasthtml-elements
                ),
                cls="flex items-center gap-2 mt-3",
            ),
            cls="flex-1 min-w-0",
        ),
        cls="flex gap-4 py-4",
        **{"x-data": alpine_data},
    )


def _Composer(
    original_entry: str,
    ai_response: str,
    title: str,
    mode_value: str,
    is_founder: bool = False,
) -> Any:
    """Sticky follow-up form pinned at the bottom of #journal-workspace.

    Hidden inputs carry IDs so the follow-up route can update them via
    HTMX out-of-band swaps without resetting the textarea.

    ``is_founder`` renders the "Summon the canon shelf" dial — the quote-on-demand
    surface (ADR-076). Because the composer form is never reset between turns
    (only the textarea is cleared), a checked box persists across follow-ups, so
    a summoned conversation stays summoned without any OOB re-render.
    """
    from ui.components import Icon

    return Form(
        Input(
            id="journal-original-entry",
            type="hidden",
            name="original_entry",
            value=original_entry,
        ),
        Input(
            id="journal-ai-response",
            type="hidden",
            name="ai_response",
            value=ai_response,
        ),
        Input(type="hidden", name="title", value=title),
        Input(type="hidden", name="journal_mode", value=mode_value),
        Div(
            Textarea(
                placeholder="Follow up on this response…",
                name="user_reply",
                rows="3",
                required=True,
                cls=(
                    "w-full border-none outline-none bg-transparent resize-none"
                    " text-[15px] leading-[1.6] text-foreground"
                    " placeholder:text-muted-foreground"
                ),
            ),
            Div(
                # FOUNDER grounding dials: canon (ADR-076) → this follow-up may
                # quote + cite the shelf; vault (canon P3) → may quote + cite
                # the user's own non-private notes. Unchecked/absent → FastHTML
                # binds the flag False (a normal follow-up). A plain Span
                # placeholder when not FOUNDER keeps the send button
                # right-aligned.
                (
                    Div(
                        Label(
                            Input(
                                type="checkbox",
                                name="summon_canon",
                                value="true",
                                cls="mr-1.5 align-middle",
                            ),
                            "Summon the canon shelf",
                            cls=(
                                "flex items-center text-[13px] text-muted-foreground"
                                " cursor-pointer select-none"
                            ),
                        ),
                        Label(
                            Input(
                                type="checkbox",
                                name="summon_vault",
                                value="true",
                                cls="mr-1.5 align-middle",
                            ),
                            "Draw on my vault",
                            cls=(
                                "flex items-center text-[13px] text-muted-foreground"
                                " cursor-pointer select-none"
                            ),
                        ),
                        cls="flex items-center gap-4",
                    )
                    if is_founder
                    else Span()
                ),
                Div(
                    P(
                        "Thinking…",
                        id="journal-reply-loading",
                        cls="text-sm text-muted-foreground htmx-indicator",
                    ),
                    Button(
                        Icon("arrow-up", size=16, cls="text-white"),
                        type="submit",
                        aria_label="Send follow-up",
                        cls=(
                            "w-[34px] h-[34px] rounded-full flex items-center justify-center"
                            " bg-foreground hover:bg-foreground/80 transition-colors"
                        ),
                    ),
                    cls="flex items-center gap-3",
                ),
                cls="flex items-center justify-between gap-3 mt-2",
            ),
            cls=("border border-border rounded-[25px] px-[18px] pt-3 pb-3 bg-background shadow-sm"),
        ),
        id="journal-composer",
        hx_post="/journals/follow-up",
        hx_target="#journal-thread",
        hx_swap="beforeend",
        hx_indicator="#journal-reply-loading",
        # Clear textarea and scroll thread to bottom after each exchange.
        # Do NOT call form.reset() — that would clobber the OOB-updated hidden inputs.
        hx_on__after_request=(
            "this.querySelector('textarea').value='';"
            "var s=document.getElementById('journal-thread');"
            "if(s){s.scrollTop=s.scrollHeight;}"
        ),
        cls="border-t border-border px-6 py-4 bg-background flex-shrink-0",
    )


# ------------------------------------------------------------------
# Stage fragments (returned as HTMX swaps to #journal-workspace)
# ------------------------------------------------------------------


def TranscriptReviewFragment(transcript: str, title: str) -> Any:
    """FOUNDER tier: transcript review card shown after audio transcription.

    The user reviews the transcript, then clicks "Scribe →" to begin the
    DNWF interactive workflow (Stage 1 → review → Stage 2 → review → Stage 3).
    """
    return Div(
        Card(
            CardHeader(CardTitle("Transcript")),
            CardBody(
                P(
                    transcript or "(empty transcript)",
                    cls="text-sm whitespace-pre-wrap leading-relaxed font-mono",
                ),
            ),
            cls="mb-6",
        ),
        Form(
            Input(type="hidden", name="raw_entry", value=transcript),
            Input(type="hidden", name="title", value=title),
            StyledButton(
                "Scribe →",
                cls=ButtonT.default,
                hx_post="/journals/stage1",
                hx_target="#journal-workspace",
                hx_swap="outerHTML",
                hx_include="closest form",
                hx_indicator="#journal-loading",
            ),
            _LoadingIndicator(),
        ),
        id="journal-workspace",
        cls="p-6",
    )


def Stage1Fragment(raw_entry: str, title: str, scribe_output: str) -> Any:
    """Fragment returned after Stage 1 — Scribe completes."""
    return Div(
        Card(
            CardHeader(CardTitle("Stage 1 — Scribe")),
            CardBody(
                P(
                    scribe_output,
                    cls="text-sm whitespace-pre-wrap leading-relaxed",
                ),
            ),
            cls="mb-6",
        ),
        _ReviewGate(
            stage_target=2,
            hidden_fields={
                "raw_entry": raw_entry,
                "title": title,
                "scribe_output": scribe_output,
            },
            post_url="/journals/stage2",
            next_label="Thought Partner →",
            review_placeholder="Add notes for the Thought Partner (optional)…",
        ),
        id="journal-workspace",
        cls="p-6",
    )


def Stage2Fragment(
    raw_entry: str,
    title: str,
    scribe_output: str,
    thought_partner_output: str,
) -> Any:
    """Fragment returned after Stage 2 — Thought Partner completes."""
    return Div(
        Card(
            CardHeader(CardTitle("Stage 2 — Thought Partner")),
            CardBody(
                P(
                    thought_partner_output,
                    cls="text-sm whitespace-pre-wrap leading-relaxed",
                ),
            ),
            cls="mb-6",
        ),
        _ReviewGate(
            stage_target=3,
            hidden_fields={
                "raw_entry": raw_entry,
                "title": title,
                "scribe_output": scribe_output,
                "thought_partner_output": thought_partner_output,
            },
            post_url="/journals/stage3",
            next_label="What Is Related →",
            review_placeholder="Reactions or corrections before Stage 3 (optional)…",
        ),
        id="journal-workspace",
        cls="p-6",
    )


def Stage3Fragment(
    raw_entry: str,
    title: str,
    related_output: str,
    is_founder: bool = False,
) -> Any:
    """Fragment returned after Stage 3 — What Is Related completes.

    Now includes a follow-up composer so the user can continue the conversation
    after the DNWF completes. Context: original entry + Stage 3 output.
    ``is_founder`` gates the composer's canon "summon" dial (ADR-076).
    """
    from core.models.enums.user_enums import JournalMode

    resolved = JournalMode.default()

    return Div(
        Div(
            _AiBubble("Stage 3 — What Is Related", related_output),
            SuggestedActivitiesContainer(raw_entry),
            id="journal-thread",
            cls="flex-1 overflow-y-auto p-6 space-y-6",
        ),
        Div(
            A(
                "Process another file",
                href="/journals",
                cls=(
                    "text-[13px] text-muted-foreground hover:text-foreground"
                    " transition-colors no-underline"
                ),
            ),
            _Composer(raw_entry, related_output, title, resolved.value, is_founder=is_founder),
            cls="flex-shrink-0",
        ),
        id="journal-workspace",
        cls="flex flex-col h-full",
    )


def StandardResponseFragment(
    raw_entry: str,
    title: str,
    response_output: str,
    mode: "JournalMode | None" = None,
    is_founder: bool = False,
) -> Any:
    """Growing chat thread — initial AI response with sticky composer.

    Replaces the single-swap pattern: the workspace is now a flex column with
    a scrollable #journal-thread and a sticky #journal-composer. Follow-ups
    append new bubbles via hx-swap="beforeend" on #journal-thread.
    ``is_founder`` gates the composer's canon "summon" dial (ADR-076).
    """
    from core.models.enums.user_enums import JournalMode

    resolved = mode or JournalMode.default()
    label = (
        "Daily Notes Workflow" if mode is None else f"Journal Response — {resolved.display_label()}"
    )

    return Div(
        Div(
            _AiBubble(label, response_output),
            SuggestedActivitiesContainer(raw_entry),
            id="journal-thread",
            cls="flex-1 overflow-y-auto p-6 space-y-6",
        ),
        _Composer(raw_entry, response_output, title, resolved.value, is_founder=is_founder),
        id="journal-workspace",
        cls="flex flex-col h-full",
    )


def FileOutputFragment(
    title: str,
    output_filename: str,
    response_output: str,
    is_founder: bool = False,
) -> Any:
    """Shown after a compiled journal file is processed and saved to je_out/.

    The user downloads the file and opens it in Obsidian. The prose is NOT
    displayed inline (it can be very long). The copy button copies to clipboard.
    je_out/ is excluded from vault sync — users decide what enters their vault.

    Includes a follow-up composer for in-session questions about the output.
    """
    import json as _json
    import urllib.parse

    from core.models.enums.user_enums import JournalMode
    from ui.components import Icon

    safe_href = urllib.parse.quote(output_filename, safe="")
    resolved_mode = JournalMode.default()

    alpine_data = (
        "{ copied: false,"
        f" responseText: {_json.dumps(response_output)},"
        "  copy() { navigator.clipboard.writeText(this.responseText)"
        "    .then(() => { this.copied = true;"
        "      setTimeout(() => this.copied = false, 2000); }); } }"
    )

    return Div(
        Div(
            # Saved banner + download
            Div(
                Div(
                    Icon("file-check", size=18, cls="text-green-600 flex-shrink-0"),
                    Div(
                        P(
                            "Your file is automatically saved in your Journal Output folder.",
                            cls="text-sm font-semibold",
                        ),
                        cls="flex-1 min-w-0",
                    ),
                    Button(
                        Icon("download", size=14),
                        Span("Download"),
                        type="button",
                        cls=(
                            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-[8px]"
                            " text-sm font-medium bg-foreground text-background"
                            " hover:bg-foreground/85 transition-colors border-0 cursor-pointer"
                        ),
                        **{
                            "@click": f"window.location.href='/journals/je-out/{safe_href}'"
                        },  # boundary: fasthtml-elements
                    ),
                    cls="flex items-center gap-3",
                ),
                cls="rounded-xl border border-border bg-muted/40 px-4 py-3 mb-5",
            ),
            # Avatar + mode label + copy action (no prose — file is the artifact)
            Div(
                Div(
                    "J",
                    cls=(
                        "w-[30px] h-[30px] rounded-full bg-foreground text-background"
                        " flex items-center justify-center text-sm font-bold flex-shrink-0"
                    ),
                ),
                Div(
                    Span(
                        "Daily Notes Workflow",
                        cls="text-[13px] font-semibold text-muted-foreground",
                    ),
                    Div(
                        Button(
                            Icon("copy", size=15),
                            type="button",
                            aria_label="Copy output",
                            cls=(
                                "w-[30px] h-[30px] flex items-center justify-center rounded-[7px]"
                                " text-muted-foreground hover:bg-muted hover:text-foreground"
                                " transition-colors"
                            ),
                            **{"@click": "copy()"},  # boundary: fasthtml-elements
                        ),
                        Span(
                            "Copied!",
                            cls="text-xs text-green-600",
                            **{"x-show": "copied", "x-cloak": True},  # boundary: fasthtml-elements
                        ),
                        cls="flex items-center gap-2 mt-2",
                    ),
                    cls="flex-1 min-w-0",
                ),
                cls="flex gap-4 py-2",
                **{"x-data": alpine_data},
            ),
            id="journal-thread",
            cls="flex-1 overflow-y-auto p-6",
        ),
        _Composer(title, response_output, title, resolved_mode.value, is_founder=is_founder),
        id="journal-workspace",
        cls="flex flex-col h-full",
    )


def FollowUpFragment(
    user_reply: str,
    ai_text: str,
    combined: str,
    title: str,
    mode: "JournalMode",
    sources: "tuple[CanonSource, ...] | None" = None,
) -> Any:
    """Returned by the follow-up route — appended to #journal-thread via beforeend.

    Returns a tuple: the chat bubbles (main swap) plus two OOB inputs that update
    the hidden context fields in #journal-composer without a full replacement.
    ``sources`` (canon draws) render as a clickable citation block after the reply.
    """
    label = f"Journal Response — {mode.display_label()}"
    return (
        _UserBubble(user_reply),
        _AiBubble(label, ai_text),
        # Canon sources render aligned under the AI response (past the avatar).
        *((CanonSourcesBlock(sources, cls="ml-[46px] mt-1 mb-3"),) if sources else ()),
        # OOB: update accumulated conversation context in the sticky composer
        Input(
            id="journal-original-entry",
            type="hidden",
            name="original_entry",
            value=combined,
            hx_swap_oob="true",
        ),
        Input(
            id="journal-ai-response",
            type="hidden",
            name="ai_response",
            value=ai_text,
            hx_swap_oob="true",
        ),
    )


def FollowUpErrorFragment(message: str) -> Any:
    """Error notification appended to #journal-thread when a follow-up call fails.

    Unlike ErrorFragment, this carries no id and no workspace-level swap — it is
    appended via hx-swap="beforeend" and sits inline in the conversation thread.
    """
    from ui.components import Icon

    return Div(
        Icon("alert-circle", size=15, cls="text-destructive flex-shrink-0"),
        P(message, cls="text-sm text-destructive"),
        cls="flex items-center gap-2 py-3 px-1 text-destructive",
    )


def ErrorFragment(message: str) -> Any:
    """Error state fragment for any stage failure."""
    return Div(
        Card(
            CardBody(
                P("Something went wrong.", cls="text-sm font-semibold text-destructive mb-1"),
                P(message, cls="text-xs text-muted-foreground"),
            ),
        ),
        StyledButton(
            "Start over",
            cls=ButtonT.ghost,
            hx_get="/journals",
            hx_target="#journal-workspace",
            hx_swap="outerHTML",
            cls_="mt-4",
        ),
        id="journal-workspace",
        cls="p-6",
    )


def PeriodicNoteFragment(entry_uid: str, title: str, content: str) -> Any:
    """Editable periodic note (daily / weekly / monthly).

    Mirrors the Obsidian Calendar plugin's periodic-note UX: open the note for
    a day, week, or month, read what is already there, edit it, and save. The
    existing ``content`` prefills the textarea; the Save button POSTs to
    ``/journals/{uid}/note`` via HTMX. The CSRF token rides the request header
    (attached by ``static/js/skuel.js``), matching the other journal HTMX forms.
    """
    return Div(
        Div(
            P(title or "Note", cls="text-[20px] font-bold text-foreground mb-4"),
            Form(
                Textarea(
                    content,
                    name="content",
                    placeholder="Write your note for this period…",
                    rows="18",
                    cls=(
                        "w-full border border-border rounded-[16px] px-[18px] py-4"
                        " bg-background text-[15px] leading-[1.7] text-foreground"
                        " resize-y outline-none focus:border-foreground/30"
                    ),
                ),
                Div(
                    P("", id="note-save-status", cls="text-[13px] text-green-600"),
                    Button(
                        "Save",
                        type="submit",
                        cls=(
                            "inline-flex items-center px-4 py-2 rounded-[10px]"
                            " bg-foreground text-background text-sm font-semibold"
                            " hover:bg-foreground/85 transition-colors border-0 cursor-pointer"
                        ),
                    ),
                    cls="flex items-center justify-end gap-3 mt-3",
                ),
                hx_post=f"/journals/{entry_uid}/note",
                hx_target="#note-save-status",
                hx_swap="outerHTML",
            ),
            cls="max-w-[760px] mx-auto w-full px-6 py-8",
        ),
        id="journal-workspace",
        cls="flex-1 overflow-y-auto",
    )


# ------------------------------------------------------------------
# Shared helpers
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Suggested activities panel (prose + suggestions model)
# ------------------------------------------------------------------


def SuggestedActivitiesContainer(content: str) -> Any:
    """Lazy-loading placeholder for the "Suggested activities" panel.

    Posts the reflection *content* to ``/journals/suggest-activities`` on load;
    the endpoint runs the bridge and returns the rendered panel, swapped into
    this container's innerHTML. Zero-persistence (ADR-073): there is no stored
    entry — the text travels in the request body. The CSRF token rides the HTMX
    request header (attached by ``static/js/skuel.js``).
    """
    import json as _json

    return Div(
        P("Finding activities…", cls="text-[13px] text-muted-foreground"),
        id="suggested-activities",
        cls="mt-2 rounded-[12px] border border-border bg-slate-50 px-4 py-3",
        hx_post="/journals/suggest-activities",
        hx_trigger="load",
        hx_vals=_json.dumps({"content": content}),
        hx_swap="innerHTML",
    )


def SuggestedActivitiesPanel(
    items: "list[SuggestedActivity] | None" = None,
    *,
    unavailable: bool = False,
    error: bool = False,
) -> Any:
    """Inner content of the suggestions panel — copyable, domain-tagged DSL lines.

    States: bridge-unavailable note (CORE tier, or FULL without an OpenAI key),
    error, empty, or a list of suggestion rows. The panel is inert — copying a
    line creates nothing; entities exist only after the user pastes a line into
    a synced folder.
    """
    items = items or []

    header = Div(
        P("Suggested activities", cls="text-[14px] font-semibold text-foreground"),
        P(
            "Copy any line into a Periodic Note or your activity notes folder. "
            "Nothing is saved automatically.",
            cls="text-[12px] text-muted-foreground mt-1 leading-snug",
        ),
        cls="mb-3",
    )

    if unavailable:
        body: Any = P(
            "Suggestions aren't available right now. You can still type @context() "
            'lines yourself, e.g. "- [ ] Call hosting provider @context(task) '
            '@priority(2)" — types: task, habit, goal, event, principle, choice.',
            cls="text-[12.5px] text-muted-foreground leading-snug",
        )
    elif error:
        body = P(
            "Couldn't generate suggestions just now — your reflection is unaffected.",
            cls="text-[12.5px] text-muted-foreground leading-snug",
        )
    elif not items:
        body = P(
            "No activities recognised yet — write a bit more, or tag them yourself.",
            cls="text-[12.5px] text-muted-foreground leading-snug",
        )
    else:
        body = Div(*[_suggestion_row(item) for item in items], cls="space-y-2")

    return Div(header, body)


def _suggestion_row(item: "SuggestedActivity") -> Any:
    """One copyable suggestion: domain chip + copy button + the canonical DSL line."""
    import json as _json

    from ui.components import Icon

    alpine_data = (
        "{ copied: false,"
        f" line: {_json.dumps(item.dsl_line)},"
        "  copy() { navigator.clipboard.writeText(this.line)"
        "    .then(() => { this.copied = true;"
        "      setTimeout(() => this.copied = false, 2000); }); } }"
    )

    return Div(
        Div(
            Span(
                item.domain,
                cls=(
                    "text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5"
                    " rounded-[4px] bg-foreground/10 text-foreground/70 flex-shrink-0"
                ),
            ),
            Button(
                Icon("copy", size=13),
                Span(
                    "Copied!",
                    cls="text-[10px] text-green-600",
                    **{"x-show": "copied", "x-cloak": True},  # boundary: fasthtml-elements
                ),
                type="button",
                aria_label="Copy activity line",
                cls=(
                    "ml-auto inline-flex items-center gap-1 px-1.5 py-0.5 rounded-[6px]"
                    " text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                ),
                **{"@click": "copy()"},  # boundary: fasthtml-elements
            ),
            cls="flex items-center gap-2 mb-1",
        ),
        P(
            item.dsl_line,
            cls="text-[12px] font-mono leading-snug text-foreground/80 break-words",
        ),
        cls="rounded-[10px] border border-border bg-background px-3 py-2",
        **{"x-data": alpine_data},  # boundary: fasthtml-elements
    )


def _ReviewGate(
    stage_target: int,
    hidden_fields: dict[str, str],
    post_url: str,
    next_label: str,
    review_placeholder: str,
) -> Any:
    hidden_inputs = [Input(type="hidden", name=k, value=v) for k, v in hidden_fields.items()]
    return Form(
        *hidden_inputs,
        Div(
            Label("Review notes", cls="text-sm font-medium"),
            Textarea(
                name="review_notes",
                placeholder=review_placeholder,
                rows="4",
                cls="w-full mt-1 text-sm resize-y",
            ),
            cls="mb-4",
        ),
        # Grounding dials: unchecked → the param is omitted from the POST and
        # FastHTML binds the flag False (a normal, ungrounded stage). Canon →
        # curated book passages voice-infuse the response (ADR-076); vault →
        # the user's own non-private notes do (canon P3). hx_include="closest
        # form" (on the button below) carries them. Wired once here for both stages.
        Label(
            Input(
                type="checkbox",
                name="summon_canon",
                value="true",
                cls="mr-2 align-middle",
            ),
            "Summon the canon shelf",
            cls="flex items-center text-sm text-muted-foreground mb-2 cursor-pointer",
        ),
        Label(
            Input(
                type="checkbox",
                name="summon_vault",
                value="true",
                cls="mr-2 align-middle",
            ),
            "Draw on my vault",
            cls="flex items-center text-sm text-muted-foreground mb-4 cursor-pointer",
        ),
        StyledButton(
            next_label,
            cls=ButtonT.default,
            hx_post=post_url,
            hx_target="#journal-workspace",
            hx_swap="outerHTML",
            hx_include="closest form",
            hx_indicator="#journal-loading",
        ),
        _LoadingIndicator(),
        cls="mb-4",
    )
