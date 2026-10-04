"""The learning path detail page — ``/lp/{uid}`` — and its step tree.

Shell-first: the shell echoes the uid into the ``/lp/{uid}/content`` fragment,
which is where the path is read. The body is the same for every viewer except
the panel beside the title: a signed-in learner sees their progress (enrolled)
or an Enroll button, an anonymous one a sign-in link.

The step tree is path → steps → Kus. The page renders the steps itself (it holds
the viewer's mastery); each step's Kus lazy-load from ``/api/lp/{uid}/children``.
Every row is read-only — the structure is vault-authored.
"""

from fasthtml.common import FT, H1, Div, Li, P, Span, Ul

from core.models.enums import EntityType
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.models.type_hints import EntityUID
from core.ports.query_types import UsedKuRow
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.feedback import Badge, BadgeT, Progress
from ui.layout import Size
from ui.pathways.components import difficulty_label
from ui.patterns.empty_state import EmptyState
from ui.patterns.entity_links import entity_detail_href
from ui.patterns.error_banner import render_error_banner
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.relationships import EntityRelationshipsSection
from ui.patterns.tree_view import TreeNode, TreeNodeList, TreeView
from ui.primitives import ButtonLink

#: The tree's lazy-load door: a path's steps, or a step's Kus.
LP_CHILDREN_ENDPOINT = "/api/lp/{uid}/children"

_CONTENT_ID = "lp-detail-content"


def lp_detail_shell(uid: str) -> FT:
    """/lp/{uid} shell — the body loads via HTMX."""
    return Div(
        content_loading_placeholder(f"/lp/{uid}/content", _CONTENT_ID),
        cls="container mx-auto px-4 py-6 max-w-4xl",
    )


def lp_detail_refusal(message: str) -> FT:
    """The body's slot when the path cannot be shown (not found, or a failed read)."""
    return Div(
        render_error_banner(message),
        ButtonLink("← All learning paths", href="/learning-paths", cls=ButtonT.ghost),
        id=_CONTENT_ID,
    )


def step_tree_nodes(steps: list[PathStep], mastered_uids: set[str]) -> list[TreeNode]:
    """A path's steps as tree rows, in path order — each links its page and lazy-loads
    its Kus; a step the viewer has mastered carries the badge."""
    return [
        {
            "uid": step.uid,
            "title": f"{index}. {step.title or step.uid}",
            "has_children": True,
            "href": entity_detail_href(EntityType.PATH_STEP.value, step.uid),
            "badge": (
                Badge("Mastered", variant=BadgeT.success, size=Size.sm)
                if step.uid in mastered_uids
                else None
            ),
        }
        for index, step in enumerate(steps, start=1)
    ]


def ku_tree_nodes(kus: list[UsedKuRow]) -> list[TreeNode]:
    """A step's Kus as leaf rows, each linking its page."""
    return [
        {
            "uid": ku["uid"],
            "title": ku["title"] or ku["uid"],
            "has_children": False,
            "href": entity_detail_href(EntityType.KU.value, ku["uid"]),
        }
        for ku in kus
    ]


def tree_rows(nodes: list[TreeNode], entity_type: str, parent_depth: int) -> FT:
    """Read-only tree rows — no drag-to-move, rename or actions menu."""
    return TreeNodeList(
        nodes=nodes,
        entity_type=entity_type,
        children_endpoint=LP_CHILDREN_ENDPOINT,
        parent_depth=parent_depth,
        draggable=False,
        editable=False,
    )


def lp_step_tree(path_uid: str, steps: list[PathStep], mastered_uids: set[str]) -> FT:
    """The path's step tree — the steps rendered here, their Kus on expand."""
    if not steps:
        return EmptyState(title="No steps defined for this path yet")
    return TreeView(
        root_uid=path_uid,
        entity_type="lp",
        children_endpoint=LP_CHILDREN_ENDPOINT,
        roots=tree_rows(step_tree_nodes(steps, mastered_uids), "ps", parent_depth=-1),
        draggable=False,
    )


def _viewer_panel(path_uid: str, signed_in: bool, is_enrolled: bool, progress: float) -> FT:
    """Progress for an enrolled learner, Enroll for a signed-in one, sign-in otherwise."""
    if not signed_in:
        return ButtonLink("Sign in to enroll", href="/login", cls=ButtonT.secondary, size="sm")
    if is_enrolled:
        return Div(
            P(f"{progress:.0f}% complete", cls="text-sm text-muted-foreground mb-1"),
            Progress(value=progress),
            cls="w-full sm:w-48",
        )
    return Button(
        "Enroll",
        cls=ButtonT.primary,
        hx_post=f"/api/pathways/enroll/{path_uid}",
        hx_target="#main-content",
    )


def lp_detail_content(
    path: LearningPath,
    *,
    signed_in: bool,
    is_enrolled: bool = False,
    progress: float = 0.0,
    mastered_uids: set[str] | None = None,
) -> FT:
    """HTMX fragment: the path's header, the viewer's panel, the step tree, outcomes,
    and the path's lateral relationships."""
    steps: list[PathStep] = path.metadata.get("steps", []) if path.metadata else []
    outcomes = path.outcomes or ()

    header = Div(
        Div(
            H1(path.title or path.uid, cls="text-2xl font-bold break-words"),
            P(path.description or "", cls="text-muted-foreground mt-2"),
            Div(
                Badge(difficulty_label(path.difficulty_rating).title(), variant=BadgeT.primary),
                Badge(f"{int(path.estimated_hours)}h", variant=BadgeT.secondary)
                if path.estimated_hours
                else None,
                Badge(f"{len(steps)} steps", variant=BadgeT.info),
                Badge(
                    str(path.path_type.value if path.path_type else "standard"),
                    variant=BadgeT.outline,
                ),
                cls="flex flex-wrap gap-2 mt-3",
            ),
            cls="flex-1 min-w-0",
        ),
        Div(
            _viewer_panel(path.uid, signed_in, is_enrolled, progress),
            cls="shrink-0",
        ),
        cls="flex flex-col sm:flex-row sm:items-start gap-4 mb-6",
    )

    return Div(
        header,
        Card(
            CardHeader(CardTitle("Steps")),
            CardBody(lp_step_tree(path.uid, steps, mastered_uids or set())),
            cls="mb-6",
        ),
        Card(
            CardHeader(CardTitle("Learning Outcomes")),
            CardBody(
                Ul(*[Li(Span(outcome)) for outcome in outcomes], cls="list-disc ml-4 space-y-1")
                if outcomes
                else EmptyState(title="No learning outcomes specified"),
            ),
            cls="mb-6",
        ),
        EntityRelationshipsSection(entity_uid=EntityUID(path.uid), entity_type="lp"),
        ButtonLink("← All learning paths", href="/learning-paths", cls=ButtonT.ghost),
        id=_CONTENT_ID,
    )
