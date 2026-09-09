"""Entry point for ``uv run python -m core.config``.

The credential setup tool is the documented way to load credentials into the
active backend (README.md, `.env.example`, SKUEL019's rule text, and the
runtime error services raise when a credential is missing all name this exact
command). Without this module the package is not executable and every one of
those instructions dead-ends on "No module named core.config.__main__".
"""

from core.config.credential_setup import main

main()
