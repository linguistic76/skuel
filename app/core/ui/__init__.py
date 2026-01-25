"""
UI utilities and helpers for SKUEL.

Modules:
- daisy_components: DaisyUI component wrappers (Button, Card, Alert, etc.)
- theme: SKUEL theme headers for FastHTML apps
- enum_helpers: Dynamic enum presentation helpers (colors, icons, trends)
- enum_search_components: Auto-generated search UI from enums
- shared_components: Reusable SKUEL component library

Usage:
    # DaisyUI component wrappers (primary UI components)
    from core.ui.daisy_components import (
        Button, ButtonT, Card, CardBody, Alert, AlertT,
        Badge, BadgeT, Input, Select, Textarea, Modal, Loading,
        DivHStacked, DivVStacked, DivFullySpaced, Grid, Size
    )

    # Theme headers for app initialization
    from core.ui.theme import daisy_headers, Theme

    # Enum helpers for dynamic presentation
    from core.ui.enum_helpers import (
        get_trend_color,
        get_trend_icon,
        get_health_color,
        get_priority_color
    )

    # Shared UI components
    from core.ui.shared_components import (
        MetricCard,
        HealthStatusCard,
        StatusBadge,
        ProgressMetric,
        InsightCard,
        RecommendationCard,
        TrendIndicator,
        SettingToggle,
        QuickStatsBar
    )

    # Enum-based search UI generation
    from core.ui.enum_search_components import (
        generate_priority_filter_options,
        generate_status_filter_options,
        generate_all_filter_options
    )
"""

# Import shared components for convenience
# Import enum helpers
from core.ui.enum_helpers import (
    get_bridge_color,
    get_completion_emoji,
    get_health_color,
    get_health_icon,
    get_priority_color,
    get_priority_numeric,
    get_severity_color,
    get_severity_numeric,
    get_status_color,
    get_trend_color,
    get_trend_icon,
)

# Import search component generators
from core.ui.enum_search_components import (
    generate_all_filter_options,
    generate_domain_filter_options,
    generate_filter_options_for_domain,
    generate_priority_filter_options,
    generate_status_filter_options,
)
from core.ui.shared_components import (
    HealthStatusCard,
    InsightCard,
    MetricCard,
    ProgressMetric,
    QuickMetricCard,
    QuickStatsBar,
    RecommendationCard,
    SettingToggle,
    StatusBadge,
    TrendIndicator,
)

__all__ = [
    "HealthStatusCard",
    "InsightCard",
    # Shared Components
    "MetricCard",
    "ProgressMetric",
    "QuickMetricCard",
    "QuickStatsBar",
    "RecommendationCard",
    "SettingToggle",
    "StatusBadge",
    "TrendIndicator",
    "generate_all_filter_options",
    "generate_domain_filter_options",
    "generate_filter_options_for_domain",
    # Search Component Generators
    "generate_priority_filter_options",
    "generate_status_filter_options",
    "get_bridge_color",
    "get_completion_emoji",
    "get_health_color",
    "get_health_icon",
    "get_priority_color",
    "get_priority_numeric",
    "get_severity_color",
    "get_severity_numeric",
    "get_status_color",
    # Enum Helpers
    "get_trend_color",
    "get_trend_icon",
]
