"""Read the lines one first-party module logs, under ``structlog.testing.capture_logs``.

Tests never call ``setup_logging``, so structlog runs on its default configuration and prints
through a ``PrintLogger``, which has no name: a captured line does not say which logger wrote
it. ``capture_with_call_sites`` stamps each line with the file whose code made the call and
renders its traceback into an ``exception`` string; ``lines_from`` then keeps one module's lines.
"""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import AbstractContextManager
from pathlib import PurePath

from structlog.processors import CallsiteParameter, CallsiteParameterAdder, format_exc_info
from structlog.testing import capture_logs
from structlog.typing import EventDict, Processor

#: Stamp the calling file, then turn ``exc_info`` into the formatted ``exception`` field.
CALL_SITE_PROCESSORS: tuple[Processor, ...] = (
    CallsiteParameterAdder({CallsiteParameter.PATHNAME}),
    format_exc_info,
)


def capture_with_call_sites() -> AbstractContextManager[list[EventDict]]:
    """Capture every structlog line, each carrying its calling file and rendered traceback."""
    return capture_logs(processors=CALL_SITE_PROCESSORS)


def lines_from(entries: Iterable[EventDict], module: str) -> list[EventDict]:
    """The captured lines whose call sits in ``module``, a repo-relative path such as
    ``core/utils/error_boundary.py``."""
    suffix = PurePath(module).parts
    return [
        entry for entry in entries if PurePath(entry["pathname"]).parts[-len(suffix) :] == suffix
    ]
