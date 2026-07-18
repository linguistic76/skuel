#!/usr/bin/env python3
"""
One-off vault migration — developed files → knowledge/ + pipeline: knowledge
============================================================================

Moves the user's "developed files" (the deliberate "teach SKUEL about me"
channel — every loose root-level note in the personal vault) into a dedicated
``knowledge/`` doorway folder and re-stamps their frontmatter to the new
``pipeline: knowledge`` marker (from the legacy ``pipeline: journal`` that an
old habit/template left behind, or from no frontmatter at all).

Scope (matches the vault design in project_developed_files_knowledge_pipeline):
  - INCLUDED: every ``*.md`` directly under the vault root.
  - EXCLUDED: the journal-staging folders (je_in/je_out/je_raw/je_pro),
    periodic_notes/, and Obsidian/SKUEL scaffolding (templates/, userguides/,
    .obsidian/, .trash/) — plus the ``knowledge/`` destination itself.

Frontmatter surgery is minimal (line-level, not a YAML round-trip) so comments,
key order, and formatting are preserved:
  - ``pipeline: <anything>``  → ``pipeline: knowledge``
  - missing ``pipeline:``     → inserted
  - missing ``type:``         → ``type: user_entry`` inserted
  - no frontmatter at all     → a fresh block is prepended

Link integrity: Obsidian ``[[wikilinks]]`` resolve by basename vault-wide and
survive the move untouched. Markdown-style ``[text](path.md)`` links are
path-relative and are rewritten to their correct new relative path (both in the
moved files and in any staying file that pointed at a moved one). Non-.md and
http(s) targets are left alone.

Safety: DRY-RUN by default — prints the full plan and changes nothing. Pass
``--apply`` to execute. The move is reversible (it is a plain rename); Obsidian
file-recovery is also enabled on this vault.

Usage:
    uv run scripts/migrate_developed_files_to_knowledge.py            # dry run
    uv run scripts/migrate_developed_files_to_knowledge.py --apply    # execute
    uv run scripts/migrate_developed_files_to_knowledge.py --vault /path --dest knowledge
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

DEFAULT_VAULT = Path("/home/mike/0bsidian/skuel")
DEFAULT_DEST = "knowledge"

# Folders never treated as developed content — excluded from the MOVE + restamp
# (see .env SKUEL_VAULT_SYNC_ALLOWED_DIRS rationale + STAGING_EXCLUDED_DIRS in
# core/services/ingestion/config.py).
EXCLUDED_DIRS = frozenset(
    {
        "je_in",
        "je_out",
        "je_raw",
        "je_pro",
        "periodic_notes",
        "templates",
        "userguides",
        ".obsidian",
        ".trash",
    }
)

# Folders skipped by the INBOUND link-rewrite pass. Narrower than EXCLUDED_DIRS:
# periodic_notes/, templates/, userguides/ are real content that may link to a
# moved developed file, so their links must stay valid. Only journal staging
# (private) and Obsidian config/trash are left untouched.
LINK_SKIP_DIRS = frozenset({"je_in", "je_out", "je_raw", "je_pro", ".obsidian", ".trash"})

TARGET_PIPELINE = "knowledge"
TARGET_TYPE = "user_entry"

# Markdown inline link: [text](target)  — captures the target only.
_MD_LINK = re.compile(r"(?<!\!)\]\(([^)]+)\)")


@dataclass
class Plan:
    """Everything the migration will do, computed before any write."""

    moved: list[Path] = field(default_factory=list)  # root .md files to relocate
    restamped_journal: list[Path] = field(default_factory=list)
    restamped_added: list[Path] = field(default_factory=list)  # fm existed, pipeline added
    restamped_new_fm: list[Path] = field(default_factory=list)  # no fm at all
    other_subdirs: list[Path] = field(default_factory=list)  # unexpected dirs (reported)
    link_edits: dict[Path, int] = field(default_factory=dict)  # file -> # links rewritten
    collisions: list[Path] = field(default_factory=list)  # root files whose dest name is taken


# --------------------------------------------------------------------------- #
# Frontmatter surgery (minimal, formatting-preserving)
# --------------------------------------------------------------------------- #


def _split_frontmatter(text: str) -> tuple[list[str] | None, str]:
    """Return (frontmatter_lines, body) — frontmatter_lines is None if absent.

    frontmatter_lines excludes the ``---`` fences.
    """
    if not text.startswith("---"):
        return None, text
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], "".join(lines[i + 1 :])
    return None, text  # unterminated fence → treat as no frontmatter


def restamp(text: str) -> tuple[str, str]:
    """Re-stamp frontmatter to pipeline: knowledge. Returns (new_text, kind).

    kind ∈ {"journal", "added", "new_fm"} describing what changed, for reporting.
    """
    fm, body = _split_frontmatter(text)

    if fm is None:
        block = f"---\ntype: {TARGET_TYPE}\npipeline: {TARGET_PIPELINE}\n---\n\n"
        return block + text, "new_fm"

    had_pipeline = any(re.match(r"^\s*pipeline\s*:", ln) for ln in fm)
    has_type = any(re.match(r"^\s*type\s*:", ln) for ln in fm)

    new_fm: list[str] = []
    for ln in fm:
        if re.match(r"^\s*pipeline\s*:", ln):
            new_fm.append(f"pipeline: {TARGET_PIPELINE}\n")
        else:
            new_fm.append(ln)
    if not has_type:
        new_fm.insert(0, f"type: {TARGET_TYPE}\n")
    if not had_pipeline:
        # place pipeline right after type for readability
        idx = next((i for i, ln in enumerate(new_fm) if re.match(r"^\s*type\s*:", ln)), -1)
        new_fm.insert(idx + 1, f"pipeline: {TARGET_PIPELINE}\n")

    rebuilt = "---\n" + "".join(new_fm) + "---\n" + body
    kind = "journal" if had_pipeline else "added"
    return rebuilt, kind


# --------------------------------------------------------------------------- #
# Link rewriting
# --------------------------------------------------------------------------- #


def _is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "#")) or target.startswith("/")


def _rewrite_links(
    text: str,
    source_old_dir: Path,
    source_new_dir: Path,
    path_map: dict[Path, Path],
) -> tuple[str, int]:
    """Rewrite markdown .md links in ``text`` given the old→new path map.

    ``source_old_dir`` is where the source file lived BEFORE the move (used to
    resolve its relative links); ``source_new_dir`` is where it lives AFTER (used
    to recompute the new relative path). For a moved root note these differ
    (vault root → ``knowledge/``); for a file that stays put — including a note
    that already lived under ``knowledge/`` — they are equal. ``path_map`` maps
    every .md file's OLD absolute path to its NEW absolute path (identity for
    staying files).
    """
    count = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal count
        raw = m.group(1)
        if _is_external(raw):
            return m.group(0)
        # split off any #anchor
        anchor = ""
        target = raw
        if "#" in target:
            target, anchor = target.split("#", 1)
            anchor = "#" + anchor
        if not target.lower().endswith(".md"):
            return m.group(0)
        decoded = unquote(target)
        old_abs = (source_old_dir / decoded).resolve()
        new_abs = path_map.get(old_abs)
        if new_abs is None:
            return m.group(0)  # target not a tracked .md file; leave as-is
        rel = _relpath(new_abs, source_new_dir)
        encoded = quote(rel, safe="/") if "%" in raw else rel
        count += 1
        return f"]({encoded}{anchor})"

    return _MD_LINK.sub(repl, text), count


def _relpath(target: Path, start_dir: Path) -> str:
    import os

    return os.path.relpath(target, start_dir)


# --------------------------------------------------------------------------- #
# Planning + execution
# --------------------------------------------------------------------------- #


def resolve_dest(vault: Path, dest_name: str) -> Path:
    """Resolve + validate the destination folder — fail-closed on unsafe values.

    The destination must be a folder STRICTLY inside the vault. This rejects
    ``--dest .`` (which would resolve to the vault root and make each move a
    rewrite-in-place immediately followed by ``unlink`` — silent data loss) and
    absolute / ``..`` destinations that would move notes out of the vault.
    """
    dest = (vault / dest_name).resolve()
    if dest == vault or vault not in dest.parents:
        raise ValueError(
            f"--dest must be a subfolder strictly inside the vault; got {dest!r} for vault {vault!r}"
        )
    return dest


def build_plan(vault: Path, dest: Path) -> tuple[Plan, dict[Path, Path]]:
    plan = Plan()

    # Root-level developed files = *.md directly under the vault root.
    root_md = sorted(p for p in vault.iterdir() if p.is_file() and p.suffix.lower() == ".md")

    # Report unexpected subdirectories so nothing is silently skipped.
    for p in sorted(vault.iterdir()):
        if p.is_dir() and p.name not in EXCLUDED_DIRS and p.resolve() != dest:
            plan.other_subdirs.append(p)

    # old→new map over EVERY .md in the vault (for link rewriting).
    path_map: dict[Path, Path] = {}
    for md in vault.rglob("*.md"):
        # skip inside excluded dirs
        rel_parts = md.relative_to(vault).parts
        if rel_parts and rel_parts[0] in EXCLUDED_DIRS:
            path_map[md.resolve()] = md.resolve()
            continue
        if md.parent == vault:  # a moved root file
            path_map[md.resolve()] = (dest / md.name).resolve()
        else:
            path_map[md.resolve()] = md.resolve()

    plan.moved = root_md

    # Basename collisions: a root note whose name already exists under dest would
    # be overwritten (then its source unlinked) → irreversible loss. Detect up
    # front so the caller refuses to --apply.
    plan.collisions = [f for f in root_md if (dest / f.name).exists()]

    # classify restamp kind (dry preview)
    for f in root_md:
        _, kind = restamp(f.read_text(encoding="utf-8"))
        if kind == "journal":
            plan.restamped_journal.append(f)
        elif kind == "added":
            plan.restamped_added.append(f)
        else:
            plan.restamped_new_fm.append(f)

    return plan, path_map


def execute(vault: Path, dest: Path, plan: Plan, path_map: dict[Path, Path]) -> None:
    if plan.collisions:  # defensive: main() already guards this
        raise ValueError("refusing to execute: destination basename collisions present")
    dest.mkdir(exist_ok=True)

    # 1) Rewrite links + restamp moved files, write to NEW location. A moved root
    #    note came FROM the vault root (source_old_dir=vault) and lands in dest.
    for f in plan.moved:
        text = f.read_text(encoding="utf-8")
        text, _kind = restamp(text)
        text, n = _rewrite_links(text, vault, dest, path_map)
        if n:
            plan.link_edits[f] = n
        (dest / f.name).write_text(text, encoding="utf-8")
        f.unlink()  # remove old root copy after successful write

    # 2) Rewrite inbound links in STAYING .md files that referenced a moved file.
    #    A staying file did not move, so old dir == new dir == its own parent —
    #    including a note that already lived under dest/ (resolved against dest/,
    #    not the vault root).
    moved_new = {path_map[f.resolve()] for f in plan.moved}
    for md in vault.rglob("*.md"):
        if md.resolve() in moved_new:
            continue  # already handled (it's a moved file, now in dest)
        rel_parts = md.relative_to(vault).parts
        if rel_parts and rel_parts[0] in LINK_SKIP_DIRS:
            continue
        text = md.read_text(encoding="utf-8")
        parent = md.parent.resolve()
        new_text, n = _rewrite_links(text, parent, parent, path_map)
        if n:
            md.write_text(new_text, encoding="utf-8")
            plan.link_edits[md] = plan.link_edits.get(md, 0) + n


def print_plan(vault: Path, dest: Path, plan: Plan, applied: bool) -> None:
    verb = "MOVED" if applied else "WILL MOVE"
    print(f"\nVault: {vault}")
    print(f"Destination folder: {dest}\n")
    print(f"{verb} {len(plan.moved)} developed files → {dest.name}/")
    print(f"  • re-stamp pipeline: journal → knowledge : {len(plan.restamped_journal)}")
    print(f"  • add pipeline: knowledge (fm existed)   : {len(plan.restamped_added)}")
    print(f"  • add fresh frontmatter (none before)    : {len(plan.restamped_new_fm)}")
    if plan.other_subdirs:
        print("\n  ⚠ Unexpected subfolders under the vault root (NOT touched — review):")
        for d in plan.other_subdirs:
            print(f"      {d.name}/")
    if plan.collisions:
        print(
            f"\n  ✖ {len(plan.collisions)} name collision(s) — dest already has a file of this name:"
        )
        for c in plan.collisions:
            print(f"      {c.name}")
        print("      Resolve these (rename/remove) before --apply; refusing to overwrite.")
    if applied and plan.link_edits:
        total = sum(plan.link_edits.values())
        print(f"\n  ↳ rewrote {total} markdown link(s) across {len(plan.link_edits)} file(s)")
    if not applied:
        print("\nDRY RUN — nothing written. Re-run with --apply to execute.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    ap.add_argument("--dest", default=DEFAULT_DEST, help="destination subfolder name")
    ap.add_argument("--apply", action="store_true", help="execute (default: dry run)")
    args = ap.parse_args()

    vault: Path = args.vault.resolve()
    if not vault.is_dir():
        print(f"ERROR: vault not found: {vault}", file=sys.stderr)
        return 1

    try:
        dest = resolve_dest(vault, args.dest)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    plan, path_map = build_plan(vault, dest)
    if not plan.moved:
        print("No root-level .md developed files found — nothing to do.")
        return 0

    # Collisions are irreversible-loss risks: never --apply through them.
    if args.apply and plan.collisions:
        print_plan(vault, dest, plan, applied=False)
        print("\nERROR: refusing to --apply with destination name collisions.", file=sys.stderr)
        return 1

    if args.apply:
        execute(vault, dest, plan, path_map)
    print_plan(vault, dest, plan, applied=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
