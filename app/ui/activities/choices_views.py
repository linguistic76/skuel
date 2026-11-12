"""Choices UI view components.

Pure FastHTML components for rendering choice data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.choices_views import ChoiceList, ChoiceStatsBar
"""

import json
from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    A,
    Details,
    Div,
    Fieldset,
    Form,
    Legend,
    Li,
    Option,
    P,
    Small,
    Span,
    Summary,
    Ul,
)
from fasthtml.common import Button as HtmlButton

from core.constants import SatisfactionScale
from core.models.enums.choice_enums import ChoiceType
from core.models.enums.entity_enums import EntityStatus
from ui.activities._shared import (
    ActivityList,
    ConnectionRows,
    ConnectionsSection,
    MetadataField,
    PriorityBadgeDropdown,
    TagsBlock,
    safe_id,
    tag_badges,
)
from ui.components import (
    Button,
    ButtonT,
    Card,
    Icon,
    Input,
    Label,
    LabelSelect,
    LabelTextArea,
    Radio,
    TextArea,
)
from ui.feedback import Badge, BadgeT, PriorityBadge, StatusBadge
from ui.layout import Container, DivHStacked
from ui.patterns.format_date import format_date
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.primitives import section_label

if TYPE_CHECKING:
    from collections.abc import Mapping

    from fasthtml.common import FT

    from core.models.choice.choice import Choice
    from core.models.choice.choice_option import ChoiceOption
    from core.ports.query_types import EntityConnection


def ChoiceStatsBar(choices: list[Choice]) -> FT:
    """Quick stats bar showing choice counts."""
    total = len(choices)
    pending = sum(1 for c in choices if c.is_pending())
    decided = sum(1 for c in choices if c.is_decided())
    ratings = [
        c.satisfaction_score
        for c in choices
        if c.satisfaction_score is not None and c.satisfaction_score >= SatisfactionScale.LOWEST
    ]
    avg_satisfaction = sum(ratings) / len(ratings) if ratings else None

    stats = [
        StatItem(label="Total", value=total, href="/choices?status=all"),
        StatItem(
            label="Pending",
            value=pending,
            color="warning" if pending > 0 else None,
            href="/choices?status=pending",
        ),
        StatItem(label="Decided", value=decided, color="success", href="/choices?status=decided"),
        StatItem(
            label="Avg Satisfaction",
            value=(
                f"{avg_satisfaction:.1f}/{SatisfactionScale.HIGHEST}"
                if avg_satisfaction is not None
                else "-"
            ),
            color=(
                "primary"
                if avg_satisfaction is not None
                and avg_satisfaction >= SatisfactionScale.SATISFYING_MEAN
                else None
            ),
        ),
    ]
    return StatsGrid(stats, cols=4)


def ChoiceList(
    choices: list[Choice],
    connections_map: Mapping[str, list[EntityConnection]] | None = None,
) -> FT:
    """Render a list of choice cards. Returns a replaceable container for HTMX."""
    return ActivityList(choices, "choice", ChoiceCard, connections_map)


def ChoiceCard(
    choice: Choice,
    connections: list[EntityConnection] | None = None,
) -> FT:
    """Single choice card with type, deadline, decision status, and connections."""
    is_decided = choice.is_decided()

    # The card closes a choice and reopens it. Reopened, a choice with a decision
    # recorded is active again (it never goes back to draft); one closed without a
    # decision is a draft again, its options open.
    reopen_status = EntityStatus.ACTIVE if choice.decided_at is not None else EntityStatus.DRAFT
    toggle: tuple[str, EntityStatus, str]
    if choice.status == EntityStatus.COMPLETED:
        toggle = ("Reopen", reopen_status, "check")
    elif is_decided:
        toggle = ("Mark as completed", EntityStatus.COMPLETED, "check-circle")
    else:
        toggle = ("Mark as completed", EntityStatus.COMPLETED, "git-branch")
    toggle_title, toggle_status, toggle_icon = toggle
    toggle_btn = Button(
        Icon(toggle_icon, size=16, cls="inline text-success" if is_decided else "inline"),
        hx_post=f"/api/choices/{choice.uid}/status",
        hx_vals=json.dumps({"status": toggle_status.value}),
        hx_target=f"#choice-{safe_id(choice.uid)}",
        hx_swap="outerHTML",
        cls=(ButtonT.default, "rounded-sm"),
        size="sm",
        title=toggle_title,
        aria_label=toggle_title,
        data_choice_status=toggle_status.value,
    )

    # Title
    title_cls = "text-muted-foreground" if is_decided else ""
    title_el = A(
        choice.title or "Untitled",
        href=f"/choices/detail?uid={choice.uid}",
        cls=f"hover:underline {title_cls}",
    )

    # Badges
    badges: list[Any] = []
    if choice.choice_type:
        badges.append(Badge(str(choice.choice_type.value).title(), variant=BadgeT.primary))
    badges.append(
        PriorityBadgeDropdown(
            choice.uid,
            str(choice.priority) if choice.priority else None,
            domain="choices",
            singular="choice",
        )
    )
    if choice.status:
        badges.append(StatusBadge(str(choice.status)))
    if choice.options:
        badges.append(Badge(f"{len(choice.options)} options", variant=BadgeT.secondary))

    # Deadline
    deadline_el = Span()
    if choice.decision_deadline:
        overdue = choice.is_deadline_past()
        dl_str = format_date(choice.decision_deadline, "%Y-%m-%d")
        if overdue and not is_decided:
            dl_str += " (overdue)"
        dl_cls = "text-error font-bold" if overdue and not is_decided else "text-muted-foreground"
        deadline_el = Small(f"Deadline: {dl_str}", cls=dl_cls)

    # Satisfaction score for decided choices
    satisfaction_el = Span()
    rating = choice.satisfaction_score
    if is_decided and rating is not None and rating >= SatisfactionScale.LOWEST:
        satisfaction_el = Small(
            f"Satisfaction: {rating}/{SatisfactionScale.HIGHEST}",
            cls="text-muted-foreground ml-2",
        )

    # Tags
    tags_el = Span()
    if choice.tags:
        tags_el = Div(*tag_badges(choice.tags, limit=5), cls="mt-2")

    # Page links, one line per heading
    conn_el = ConnectionRows(connections or [])

    # Card assembly
    header = Div(
        toggle_btn,
        Div(
            DivHStacked(title_el, satisfaction_el, cls="flex-wrap"),
            DivHStacked(*badges, cls="flex-wrap mt-2") if badges else "",
            deadline_el,
            tags_el,
            conn_el,
            cls="ml-2 flex-1 min-w-0",
        ),
        cls="flex items-start",
    )

    opacity = "opacity-75" if is_decided else ""
    return Card(
        header,
        id=f"choice-{safe_id(choice.uid)}",
        cls=f"p-3 {opacity}",
    )


def ChoiceDetailView(
    choice: Choice,
    connections: list[EntityConnection],
) -> FT:
    """Full detail page for a single choice."""
    is_decided = choice.is_decided()

    # Subtitle
    subtitle_parts: list[str] = []
    if choice.status:
        subtitle_parts.append(str(choice.status).replace("_", " ").title())
    if choice.choice_type:
        subtitle_parts.append(str(choice.choice_type.value).title())
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else None

    header = PageHeader(choice.title or "Untitled Choice", subtitle=subtitle)

    # Badges
    badges: list[Any] = []
    if choice.choice_type:
        badges.append(Badge(str(choice.choice_type.value).title(), variant=BadgeT.primary))
    if choice.priority:
        badges.append(PriorityBadge(str(choice.priority)))
    if choice.status:
        badges.append(StatusBadge(str(choice.status)))

    # Description
    desc_el = Div()
    if choice.description:
        desc_el = Div(P(choice.description), cls="my-4")

    # Options section: shown while options can still be added or a decision made,
    # and on a decided choice that has options to show
    options_section = Div()
    if choice.options or choice.options_open() or choice.is_pending():
        options_section = OptionsSection(choice)

    # Decision section (context, criteria, constraints, rationale)
    decision_items: list[Any] = []
    if choice.decision_context:
        decision_items.append(MetadataField("Situation", P(choice.decision_context)))
    if choice.decision_rationale:
        decision_items.append(MetadataField("Rationale", P(choice.decision_rationale)))
    if choice.decision_criteria:
        criteria_list = Ul(
            *[Li(c) for c in choice.decision_criteria],
            cls="list-disc pl-6",
        )
        decision_items.append(MetadataField("Criteria", criteria_list))
    if choice.constraints:
        constraints_list = Ul(
            *[Li(c) for c in choice.constraints],
            cls="list-disc pl-6",
        )
        decision_items.append(MetadataField("Constraints", constraints_list))
    if choice.stakeholders:
        decision_items.append(MetadataField("Stakeholders", P(", ".join(choice.stakeholders))))
    decision_section = Div()
    if decision_items:
        decision_section = Div(
            section_label("Decision Framework"),
            *decision_items,
            cls="my-4",
        )

    # Outcome section: on a decided choice, open or closed
    outcome_section = OutcomeSection(choice) if is_decided else Div()

    # Timing
    timing_items: list[Any] = []
    if choice.decision_deadline:
        overdue = choice.is_deadline_past() and not is_decided
        dl_cls = "text-error font-bold" if overdue else ""
        timing_items.append(
            MetadataField(
                "Deadline", Span(format_date(choice.decision_deadline, "%Y-%m-%d"), cls=dl_cls)
            )
        )
    if choice.decided_at:
        timing_items.append(
            MetadataField("Decided", Span(format_date(choice.decided_at, "%Y-%m-%d")))
        )
    if choice.created_at:
        timing_items.append(
            MetadataField("Created", Span(format_date(choice.created_at, "%Y-%m-%d")))
        )
    timing_grid = Div()
    if timing_items:
        timing_grid = Div(
            *timing_items,
            cls="grid grid-cols-1 sm:grid-cols-3 gap-2 my-4",
        )

    # Tags
    tags_el = TagsBlock(choice.tags)

    # Connections
    conn_section = ConnectionsSection(connections)

    # Lateral relationships
    relationships = EntityRelationshipsSection(
        entity_uid=choice.uid,
        entity_type="choices",
        authoring=True,
    )

    return Container(
        header,
        DivHStacked(*badges, cls="flex-wrap mb-2") if badges else "",
        desc_el,
        options_section,
        decision_section,
        outcome_section,
        timing_grid,
        tags_el,
        conn_section,
        relationships,
        size="3xl",
        id=choice_detail_id(choice.uid),
    )


#: The decide form's confidence scale: one step in each band of the decision-pattern
#: handler's ``categorize_confidence``, the middle one chosen until the learner says.
DECISION_CONFIDENCE_LEVELS: tuple[tuple[str, str], ...] = (
    ("0.1", "Very unsure"),
    ("0.3", "Unsure"),
    ("0.5", "Somewhat sure"),
    ("0.7", "Sure"),
    ("0.9", "Very sure"),
)
DEFAULT_DECISION_CONFIDENCE = "0.5"


#: The outcome form's satisfaction levels, lowest to highest (``SatisfactionScale``).
SATISFACTION_LEVELS: tuple[tuple[int, str], ...] = (
    (1, "Very dissatisfied"),
    (2, "Dissatisfied"),
    (3, "Neither"),
    (4, "Satisfied"),
    (5, "Very satisfied"),
)


def choice_detail_id(choice_uid: str) -> str:
    """The detail view's element id: what the options and decision controls replace."""
    return f"choice-detail-{safe_id(choice_uid)}"


def OptionsSection(choice: Choice) -> FT:
    """A choice's options, and the controls its state allows.

    Pending (not decided, not archived) with two options or more: the decide form, one
    radio per option, an optional rationale and how sure the learner is. While options
    may change (``Choice.options_open``): a remove beside each option when removing
    leaves two, and the add-option form (not on a binary choice that has its two).
    Decided: the options, the selected one marked. Each control posts over HTMX and
    is answered with the whole detail view, so status, rationale and decided date move
    with it.
    """
    target = f"#{choice_detail_id(choice.uid)}"
    options = choice.options
    editable = choice.options_open()
    removable = editable and len(options) > 2
    deciding = choice.is_pending() and len(options) >= 2

    parts: list[FT] = [section_label("Options")]
    if deciding:
        parts.append(_DecideForm(choice, target, removable))
    elif options:
        parts.append(
            Ul(
                *[_OptionRow(choice, opt, removable, target, radio=None) for opt in options],
                cls="space-y-2",
            )
        )
    else:
        parts.append(P("No options yet.", cls="text-sm text-muted-foreground"))

    if choice.is_pending() and len(options) < 2:
        parts.append(
            P("Add at least two options to decide.", cls="text-sm text-muted-foreground mt-2")
        )
    binary_full = choice.choice_type == ChoiceType.BINARY and len(options) >= 2
    if editable and not binary_full:
        parts.append(_AddOptionForm(choice, target))

    return Div(*parts, cls="my-4", id=f"choice-options-{safe_id(choice.uid)}")


def _OptionRow(
    choice: Choice,
    opt: ChoiceOption,
    removable: bool,
    target: str,
    radio: FT | None,
) -> FT:
    """One option: its radio when deciding, its title and description, its remove."""
    is_selected = choice.selected_option_uid is not None and opt.uid == choice.selected_option_uid
    text: list[FT] = [Span(opt.title or opt.uid, cls="font-bold" if is_selected else "")]
    if is_selected:
        text.append(Small(" (selected)", cls="text-success"))
    if opt.description:
        text.append(Small(f" — {opt.description}", cls="text-muted-foreground"))

    lead: FT
    if radio is not None:
        lead = radio
    else:
        icon = "check-circle" if is_selected else "circle"
        icon_cls = "text-success" if is_selected else "text-muted-foreground"
        lead = Icon(icon, size=16, cls=f"shrink-0 mt-0.5 {icon_cls}")

    body: FT = (
        Label(
            lead,
            Span(*text, cls="min-w-0 break-words"),
            cls="flex items-start gap-2 flex-1 min-w-0 font-normal",
            fr=_radio_id(choice, opt),
        )
        if radio is not None
        else Div(
            lead,
            Span(*text, cls="min-w-0 break-words"),
            cls="flex items-start gap-2 flex-1 min-w-0",
        )
    )
    row: list[FT] = [body]
    if removable:
        row.append(
            HtmlButton(
                Icon("x", size=14),
                type="button",
                hx_post=f"/api/choices/{choice.uid}/options/{opt.uid}/remove",
                hx_target=target,
                hx_swap="outerHTML",
                hx_confirm=f'Remove "{opt.title or opt.uid}"?',
                hx_disabled_elt="this",
                cls=(
                    "inline-flex items-center justify-center w-9 h-9 shrink-0 rounded-full "
                    "text-muted-foreground hover:text-foreground hover:bg-accent "
                    "disabled:opacity-50"
                ),
                aria_label=f"Remove option {opt.title or opt.uid}",
                data_choice_option_remove=opt.uid,
            )
        )
    return Li(*row, cls="flex items-start gap-2")


def _radio_id(choice: Choice, opt: ChoiceOption) -> str:
    return f"decide-{safe_id(choice.uid)}-{safe_id(opt.uid)}"


def _DecideForm(choice: Choice, target: str, removable: bool) -> FT:
    """The decision: one option, an optional rationale, how sure. Posts ``/decide``."""
    rows = [
        _OptionRow(
            choice,
            opt,
            removable,
            target,
            radio=Radio(
                name="selected_option_uid",
                value=opt.uid,
                id=_radio_id(choice, opt),
                required=True,
                cls="mt-0.5 shrink-0",
            ),
        )
        for opt in choice.options
    ]
    form_id = safe_id(choice.uid)
    return Form(
        Fieldset(
            Legend("Which will you choose?", cls="text-sm font-medium mb-2"),
            Ul(*rows, cls="space-y-2"),
        ),
        LabelTextArea(
            "Why this one? (optional)",
            name="decision_rationale",
            id=f"decide-rationale-{form_id}",
            rows=2,
            maxlength=1000,
            cls="space-y-2 mt-4",
        ),
        LabelSelect(
            *[
                Option(label, value=value, selected=value == DEFAULT_DECISION_CONFIDENCE)
                for value, label in DECISION_CONFIDENCE_LEVELS
            ],
            label="How sure are you?",
            name="confidence",
            id=f"decide-confidence-{form_id}",
            cls="space-y-2 mt-4",
        ),
        Div(Button("Decide", type="submit", cls=ButtonT.primary), cls="mt-4"),
        hx_post=f"/api/choices/{choice.uid}/decide",
        hx_target=target,
        hx_swap="outerHTML",
        hx_disabled_elt="find button[type=submit]",
        data_choice_decide="1",
    )


def _AddOptionForm(choice: Choice, target: str) -> FT:
    """One more option: a title and an optional description. Posts ``/options``."""
    form_id = safe_id(choice.uid)
    return Form(
        Label("Add an option", fr=f"option-title-{form_id}", cls="block mb-2"),
        Div(
            Input(
                name="title",
                id=f"option-title-{form_id}",
                placeholder="Option",
                required=True,
                maxlength=200,
                cls="sm:flex-1",
            ),
            Input(
                name="description",
                placeholder="Description (optional)",
                maxlength=1000,
                aria_label="Option description",
                cls="sm:flex-1",
            ),
            Button("Add option", type="submit", cls=ButtonT.default, size="field"),
            cls="flex flex-col sm:flex-row gap-2",
        ),
        hx_post=f"/api/choices/{choice.uid}/options",
        hx_target=target,
        hx_swap="outerHTML",
        hx_disabled_elt="find button[type=submit]",
        cls="mt-4",
        data_choice_add_option="1",
    )


def OutcomeSection(choice: Choice) -> FT:
    """How a decided choice turned out: what the learner recorded, and the form that records it.

    With no outcome yet, the form stands open under "How did it turn out?". Once one is
    recorded it is shown, and the same form, filled in, updates it behind "Update the
    outcome". Closing the choice is separate (its card): an outcome can come before or
    after, or never. The form posts over HTMX and is answered with the whole detail view.
    """
    section_id = f"choice-outcome-{safe_id(choice.uid)}"
    form = _OutcomeForm(choice)
    recorded = choice.satisfaction_score is not None or bool(choice.actual_outcome)
    if not recorded:
        return Div(section_label("How did it turn out?"), form, cls="my-4", id=section_id)

    items: list[FT] = []
    if choice.satisfaction_score is not None:
        filled = int(choice.satisfaction_score)
        items.append(
            MetadataField(
                "Satisfaction",
                Span(
                    "★" * filled + "☆" * (SatisfactionScale.HIGHEST - filled),
                    cls="text-warning text-xl",
                    aria_hidden="true",
                ),
                Span(
                    f" {filled}/{SatisfactionScale.HIGHEST}",
                    cls="text-muted-foreground text-sm",
                ),
            )
        )
    if choice.actual_outcome:
        items.append(MetadataField("What happened", P(choice.actual_outcome)))
    if choice.lessons_learned:
        items.append(
            MetadataField(
                "Lessons learned",
                Ul(*[Li(lesson) for lesson in choice.lessons_learned], cls="list-disc pl-6"),
            )
        )
    return Div(
        section_label("Outcome"),
        *items,
        Details(
            Summary(
                "Update the outcome",
                cls="text-sm font-medium cursor-pointer select-none hover:underline",
            ),
            Div(form, cls="mt-3"),
            cls="mt-3",
        ),
        cls="my-4",
        id=section_id,
    )


def _OutcomeForm(choice: Choice) -> FT:
    """Satisfaction, what happened, and the lessons one per line, filled with what is
    recorded. Posts ``/outcome``."""
    form_id = safe_id(choice.uid)
    current = choice.satisfaction_score
    recorded = current is not None or bool(choice.actual_outcome)
    return Form(
        LabelSelect(
            Option("Choose one", value="", disabled=True, selected=current is None),
            *[
                Option(f"{level}: {label}", value=str(level), selected=level == current)
                for level, label in SATISFACTION_LEVELS
            ],
            label="How satisfied are you with how it turned out?",
            name="satisfaction_score",
            id=f"outcome-satisfaction-{form_id}",
            required=True,
        ),
        Div(
            Label("What happened?", fr=f"outcome-actual-{form_id}"),
            TextArea(
                choice.actual_outcome or "",
                name="actual_outcome",
                id=f"outcome-actual-{form_id}",
                rows=3,
                maxlength=1000,
                required=True,
            ),
            cls="space-y-2 mt-4",
        ),
        Div(
            Label("Lessons learned (optional, one per line)", fr=f"outcome-lessons-{form_id}"),
            TextArea(
                "\n".join(choice.lessons_learned),
                name="lessons_learned",
                id=f"outcome-lessons-{form_id}",
                rows=3,
            ),
            cls="space-y-2 mt-4",
        ),
        Div(
            Button(
                "Update outcome" if recorded else "Record outcome",
                type="submit",
                cls=ButtonT.primary,
            ),
            cls="mt-4",
        ),
        hx_post=f"/api/choices/{choice.uid}/outcome",
        hx_target=f"#{choice_detail_id(choice.uid)}",
        hx_swap="outerHTML",
        hx_disabled_elt="find button[type=submit]",
        data_choice_outcome="1",
    )
