"""Entry point for ``uv run python -m core.config``.

That command is how the docs, SKUEL019's rule text, and the error a service
raises on a missing credential all tell you to load one into the active
backend. This module is what makes it resolve to the setup tool.
"""

from core.config.credential_setup import main

main()
