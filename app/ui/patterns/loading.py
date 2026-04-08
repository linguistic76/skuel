"""Content loading placeholder — HTMX lazy-load trigger div.

Used by shell-first page route handlers to fire a fragment endpoint
after the page chrome has been painted.

See: docs/patterns/SHELL_FIRST_PAGE_PATTERN.md
"""

from fasthtml.common import Div, P


def content_loading_placeholder(
    fragment_url: str,
    target_id: str,
    *,
    loading_text: str = "Loading...",
    swap: str = "outerHTML",
) -> Div:
    """HTMX div that fires a fragment request on page load.

    Args:
        fragment_url: The URL to GET when the div loads (e.g. "/tasks/content").
        target_id: The ``id`` attribute set on the Div — HTMX replaces this
            element when the fragment returns.
        loading_text: Visible text while the fragment is in flight.
            Defaults to "Loading...". Use a domain-specific string like
            "Loading activity reports..." where appropriate.
        swap: HTMX swap strategy. Defaults to "outerHTML" (replaces entire Div).

    Returns:
        A Div that immediately triggers an HTMX GET and shows a loading
        indicator while waiting.
    """
    return Div(
        P(loading_text, cls="text-muted-foreground py-8 text-center text-sm"),
        id=target_id,
        hx_get=fragment_url,
        hx_trigger="load",
        hx_swap=swap,
    )
