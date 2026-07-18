"""PWA routes — serve manifest, service worker, and offline page from root scope."""

from pathlib import Path
from typing import Any

from starlette.responses import FileResponse

from adapters.inbound.fasthtml_types import Request

_static_dir = Path.cwd() / "static"


def create_pwa_routes(rt: Any) -> None:
    """Register PWA asset routes at root scope for installability."""

    @rt("/manifest.json")
    def pwa_manifest(request: Request) -> FileResponse:
        return FileResponse(_static_dir / "manifest.json", media_type="application/manifest+json")

    @rt("/service-worker.js")
    def pwa_service_worker(request: Request) -> FileResponse:
        return FileResponse(_static_dir / "service-worker.js", media_type="application/javascript")

    @rt("/offline.html")
    def pwa_offline(request: Request) -> FileResponse:
        return FileResponse(_static_dir / "offline.html", media_type="text/html")
