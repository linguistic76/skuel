"""Content loading placeholder — HTMX lazy-load trigger div.

Used by shell-first page route handlers to fire a fragment endpoint
after the page chrome has been painted.

See: docs/patterns/SHELL_FIRST_PAGE_PATTERN.md
"""

from fasthtml.common import Div, Span


def content_loading_placeholder(
    fragment_url: str,
    target_id: str,
    *,
    loading_text: str = "Loading...",
    swap: str = "outerHTML",
) -> Div:
    """HTMX div that fires a fragment request on page load.

    Renders an animated skeleton shimmer (``animate-pulse`` bars) while the
    fragment is in flight.  ``loading_text`` is retained as a screen-reader
    label only — it does not appear visually.

    Args:
        fragment_url: The URL to GET when the div loads (e.g. "/tasks/content").
        target_id: The ``id`` attribute set on the Div — HTMX replaces this
            element when the fragment returns.
        loading_text: Accessible label for screen readers while loading.
            Defaults to "Loading...".
        swap: HTMX swap strategy. Defaults to "outerHTML" (replaces entire Div).

    Returns:
        A Div that immediately triggers an HTMX GET and shows a skeleton
        shimmer while waiting.
    """
    skeleton = Div(
        Span(loading_text, cls="sr-only"),
        Div(
            Div(cls="h-4 bg-muted rounded-sm w-3/4"),
            Div(cls="h-4 bg-muted rounded-sm w-full"),
            Div(cls="h-4 bg-muted rounded-sm w-5/6"),
            Div(cls="h-4 bg-muted rounded-sm w-2/3"),
            cls="animate-pulse space-y-3 py-6 px-1",
        ),
    )
    return Div(
        skeleton,
        id=target_id,
        hx_get=fragment_url,
        hx_trigger="load",
        hx_swap=swap,
    )
