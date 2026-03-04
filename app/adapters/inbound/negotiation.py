"""Content negotiation for HTML vs HXML responses.

Detects whether a request comes from a Hyperview client or web browser.
Hyperview clients send a specific Accept header for HXML content.

Usage:
    from adapters.inbound.negotiation import is_hyperview_client

    if is_hyperview_client(request):
        return hxml_response(...)
    else:
        return html_response(...)

See: /docs/decisions/ADR-039-hyperview-mobile-strategy.md
"""

from starlette.requests import Request

HXML_CONTENT_TYPE = "application/vnd.hyperview+xml"


def is_hyperview_client(request: Request) -> bool:
    """Check if the request originates from a Hyperview (React Native) client.

    Hyperview clients include the HXML content type in their Accept header.
    Web browsers send text/html or similar.
    """
    accept = request.headers.get("accept", "")
    return HXML_CONTENT_TYPE in accept
