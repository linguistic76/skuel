"""Founder-local instruction file access — shared containment + override reads.

THE single home for by-name reads from ``data/instructions/`` (the
founder-local authoring directory: admin-visible only, never committed).
Both consumers of the ADR-081 authoring approach import from here:

- ``core/services/journal/instruction_loader.py`` — the Journals DNWF and
  conversational-base loader (ADR-081)
- ``core/prompts/registry.py`` — the registry-chokepoint template override
  (ADR-082 D1)

Lifted out of the journal loader (ADR-082): the registry must never import
from ``core/services/journal/``, so the guard lives here and both consumers
import it. Functions take the base directory as a parameter so each consumer
keeps its own monkeypatchable module-level dir binding.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from core.utils.logging import get_logger

_logger = get_logger("skuel.utils.instruction_files")

_APP_ROOT: Final = Path(__file__).resolve().parent.parent.parent
INSTRUCTIONS_DIR: Final = _APP_ROOT / "data" / "instructions"


def resolve_contained(base_dir: Path, filename: str) -> Path | None:
    """Resolve ``filename`` inside ``base_dir`` — or ``None`` on traversal.

    THE single containment guard for every by-name read from the instructions
    dir. Traversal out of the dir is always an attack or a bug, so it warns
    regardless of which caller hit it. Containment is about the path, not
    existence — callers check ``is_file()`` themselves.
    """
    candidate = (base_dir / filename).resolve()
    try:
        candidate.relative_to(base_dir.resolve())
    except ValueError:
        _logger.warning("Path traversal attempt blocked: %r", filename)
        return None
    return candidate


def load_optional_override(base_dir: Path, filename: str) -> str | None:
    """Read an optional founder-local override file — ``None`` when absent or blank.

    The ADR-081 D1 override reader: absence is the NORMAL state (the committed
    floor serves), so a miss is silent. Blank/whitespace content also degrades
    to ``None`` so a stray empty file can never blank a floor.
    """
    candidate = resolve_contained(base_dir, filename)
    if candidate is None or not candidate.is_file():
        return None
    content = candidate.read_text(encoding="utf-8")
    return content if content.strip() else None
