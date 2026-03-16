"""Curriculum landing page — card grid for curriculum domains.

No sidebar. Shows 4 Curriculum domain cards at a glance.
Each card links to its top-level route.
"""

from fasthtml.common import H2, A, Div, P, Span

_CURRICULUM_DOMAINS: list[tuple[str, str, str, str]] = [
    ("📖", "Lessons", "/lessons", "Units for learning that compose atomic knowledge."),
    ("🧩", "Learning Steps", "/learning-steps", "Collections of lessons grouped by theme."),
    ("🗺️", "Learning Paths", "/learning-paths", "Ordered sequences of learning step collections."),
    ("🏋️", "Exercises", "/exercises", "Practice templates linked to lessons and knowledge units."),
]


def CurriculumLandingView() -> Div:
    """Landing page content for /curriculum.

    Shows a card grid with 4 Curriculum domain cards.
    """
    header = Div(
        H2("Curriculum", cls="text-xl font-semibold text-foreground"),
        P("Browse and manage curriculum content.", cls="text-sm text-muted-foreground mt-0.5"),
        cls="mb-6",
    )

    cards = []
    for icon, name, href, description in _CURRICULUM_DOMAINS:
        cards.append(
            A(
                Div(
                    Div(
                        Span(icon, cls="text-xl"),
                        Span(name, cls="text-base font-semibold text-foreground"),
                        cls="flex items-center gap-2",
                    ),
                    cls="mb-3",
                ),
                P(description, cls="text-sm text-muted-foreground"),
                href=href,
                cls="bg-background rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow block",
            )
        )

    grid = Div(
        *cards,
        cls="grid grid-cols-1 sm:grid-cols-2 gap-4 lg:gap-5",
    )

    return Div(header, grid)
