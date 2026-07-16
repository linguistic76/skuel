"""
Shared ANSI Terminal Colors
===========================

Single source for the color palette used by SKUEL's CLI scripts
(lint_skuel, detect_bloat, docs_update, audit_route_security, health/*).
Interactive-CLI concern only — production runtime output goes through
core.utils.logging, never raw ANSI.

    from core.utils.terminal_colors import Colors
"""


class Colors:
    """Terminal colors for better output readability."""

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    @classmethod
    def disable(cls) -> None:
        """Disable colors (for non-TTY output)."""
        cls.RED = ""
        cls.GREEN = ""
        cls.YELLOW = ""
        cls.BLUE = ""
        cls.CYAN = ""
        cls.BOLD = ""
        cls.DIM = ""
        cls.RESET = ""
