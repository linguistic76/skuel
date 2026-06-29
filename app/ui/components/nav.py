from typing import Any

import fasthtml.common as fh
from fasthtml.common import Div

from ui.components._util import _cls

__all__ = ["TabContainer"]


def TabContainer(
    *tabs: Any,
    cls: str = "",
    active_tab: int = 0,
    **kwargs: Any,
) -> Any:
    """Alpine.js-driven tab container. No UIkit dependency.

    Each positional argument should be a (label, content) tuple.

    Args:
        *tabs: (label, content) pairs. Label is shown in the tab bar;
               content is rendered in the panel below.
        cls: Additional Tailwind classes for the outer wrapper.
        active_tab: Zero-based index of the initially active tab.
        **kwargs: Any HTML attribute passes through to the outer wrapper.

    Example::

        TabContainer(
            ("Overview", overview_panel),
            ("Details", details_panel),
            active_tab=0,
        )
    """
    buttons = []
    panels = []

    for i, tab in enumerate(tabs):
        if isinstance(tab, (tuple, list)) and len(tab) >= 2:
            label: Any = tab[0]
            content: Any = tab[1]
        else:
            label = str(tab)
            content = ""

        is_active = f"activeTab === {i}"
        buttons.append(
            fh.Button(
                label,
                cls="px-4 py-2 text-sm font-medium border-b-2 transition-colors",
                **{
                    "@click": f"activeTab = {i}",
                    ":class": (
                        f"{is_active} "
                        f"? 'border-primary text-primary' "
                        f": 'border-transparent text-muted-foreground"
                        f" hover:text-foreground hover:border-border'"
                    ),
                },
            )
        )
        panels.append(
            Div(content, **{"x-show": is_active, "x-transition": ""}),
        )

    return Div(
        Div(*buttons, cls="flex border-b border-border"),
        Div(*panels, cls="mt-4"),
        cls=_cls(cls),
        **{"x-data": f"{{activeTab: {active_tab}}}"},
        **kwargs,
    )
