"""Unit tests — a package, so every module under it imports as ``tests.unit.<...>``.

Without this file pytest's prepend import mode names a packaged subdirectory by its
bare directory name: ``tests/unit/scripts/`` would import as a top-level ``scripts``
package and shadow the repo's own ``scripts/`` namespace package for the rest of the
session (``tests/integration/conftest.py`` imports ``scripts.dev.bootstrap``).
"""
