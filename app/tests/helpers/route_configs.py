"""Every module-level ``DomainRouteConfig`` under ``adapters/inbound``.

Shared by the route-wiring guards that read each config against its factories.
A route module that will not import is reported, not skipped silently — it is
itself a defect.
"""

from __future__ import annotations

import importlib
import pkgutil

import adapters.inbound
from adapters.inbound.route_factories import DomainRouteConfig


def collect_module_configs() -> tuple[list[tuple[str, str, DomainRouteConfig]], list[str]]:
    """Return ``(module, attribute, config)`` triples and the modules that failed to import."""
    configs: list[tuple[str, str, DomainRouteConfig]] = []
    import_failures: list[str] = []
    for info in pkgutil.iter_modules(adapters.inbound.__path__, "adapters.inbound."):
        try:
            module = importlib.import_module(info.name)
        except ImportError as exc:
            import_failures.append(f"{info.name}: {exc}")
            continue
        for name, value in vars(module).items():
            if isinstance(value, DomainRouteConfig):
                configs.append((info.name, name, value))
    return configs, import_failures
