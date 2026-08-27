#!/usr/bin/env python3
"""One-time care cleanup: Tasks minted twice from the SAME vault checkbox line.

Why this exists (live census, 2026-08-27, AuraDB ``d2d160c4``): the 🆔→task join
key lives on the ``EXTRACTED_FROM`` edge (``vault_id`` + ``source_line_hash``),
not on the Task node. Tasks minted before that edge existed — the 2026-06-28
LLM-paraphrase door, and lines whose entry was later deleted and re-created —
carry no edge at all, so no extraction guard can recognise them: Guard 2/2b
read this entry's edges (none), and Guard 4 filters to ACTIVE twins by design
(a recurring template line MUST re-mint after completion — deferred-work.md
§ R4). Once such an orphan was completed in SKUEL its still-unchecked vault
line minted a twin on the next sync, and the twin took the line's 🆔.

The provable rule — **one physical vault checkbox line ⇒ one task**:

  - Group the user's Tasks by the R3 semantic key (``normalized_activity_title``,
    the same normaliser Guard 4 uses).
  - A group is a duplicate set ONLY when the vault holds exactly ONE
    ``extract_activities`` checkbox line with that title today. Zero lines
    (deleted / template variant) or ≥2 lines (recurring template) are REVIEW.
  - Keeper = the task whose edge owns that line's 🆔; else the oldest task.
  - DELETE = the other tasks in the group that have NO ``EXTRACTED_FROM`` edge
    (an edge-bearing twin may legitimately belong to another entry) AND are
    COMPLETED (an active twin is Guard 4's business — REVIEW).

Also reported, never acted on:
  - **Phantom 🆔s** — a vault line whose id no edge owns (the next sync of that
    file re-mints it, then recovers the id onto the new edge). With the
    edge-less same-title task that is its likely owner, when one exists.
  - **Dangling ids** — edge ids no vault line carries today (line deleted:
    deferred-work.md § "Line Deletions Leave EXTRACTED_FROM Edges").
  - **Orphans** — every edge-less task outside a duplicate set (the paraphrase-
    era census; a human decides).

Dry-run by default: prints every set and changes nothing. ``--apply`` deletes
ONLY the DELETE set, through ``TasksService.delete_task`` (cascade + the
``TaskDeleted`` event), after the dry-run has been reviewed.

Usage:
    uv run python scripts/cleanup_duplicate_vault_tasks.py --user user_linguistic76
    uv run python scripts/cleanup_duplicate_vault_tasks.py --user user_linguistic76 --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.pipeline import Pipeline
from core.services.dsl.activity_extractor import normalized_activity_title
from core.services.dsl.obsidian_tasks_adapter import obsidian_task_line_to_parsed
from core.services.ingestion.config import SyncAllowlist, is_ingestible_path
from core.utils.frontmatter import parse_frontmatter


@dataclass(frozen=True)
class VaultTaskLine:
    """One checkbox line as the extraction door sees it."""

    file: str  # vault-relative path
    line_no: int  # 1-based
    title: str  # the description the door persists as ``Task.title``
    vault_id: str | None
    is_checked: bool

    @property
    def where(self) -> str:
        return f"{self.file}:{self.line_no}"


@dataclass(frozen=True)
class TaskRow:
    """One Task with its provenance summary."""

    uid: str
    title: str
    status: str
    created_at: str  # ISO string — sorts lexically
    vault_ids: tuple[str, ...]  # 🆔s on its EXTRACTED_FROM edges
    edge_count: int  # EXTRACTED_FROM edges, ids or not
    other_rel_count: int = 0  # relationships other than OWNS / EXTRACTED_FROM

    @property
    def is_edgeless(self) -> bool:
        return self.edge_count == 0

    @property
    def is_completed(self) -> bool:
        return self.status == EntityStatus.COMPLETED.value


@dataclass(frozen=True)
class DuplicateSet:
    """A title group proven to be one vault line: keep one, delete the re-mints."""

    line: VaultTaskLine
    keep: TaskRow
    delete: tuple[TaskRow, ...]
    left_for_review: tuple[TaskRow, ...]  # twins that fail the delete criteria


@dataclass(frozen=True)
class ReviewGroup:
    title: str
    tasks: tuple[TaskRow, ...]
    reason: str


@dataclass(frozen=True)
class PhantomId:
    line: VaultTaskLine
    likely_owners: tuple[TaskRow, ...]  # edge-less tasks with the line's title


@dataclass
class Classification:
    duplicate_sets: list[DuplicateSet] = field(default_factory=list)
    review: list[ReviewGroup] = field(default_factory=list)
    phantom_ids: list[PhantomId] = field(default_factory=list)
    dangling_ids: list[str] = field(default_factory=list)
    orphans: list[TaskRow] = field(default_factory=list)

    @property
    def delete_uids(self) -> list[str]:
        return [t.uid for s in self.duplicate_sets for t in s.delete]


# ---------------------------------------------------------------------------
# Pure classification
# ---------------------------------------------------------------------------


def classify(
    tasks: list[TaskRow],
    lines: list[VaultTaskLine],
    owned_vault_ids: set[str],
) -> Classification:
    """Apply the one-line-one-task rule; everything short of proof is REVIEW.

    ``owned_vault_ids`` is every 🆔 any ``EXTRACTED_FROM`` edge into this
    user's entries carries — the phantom/dangling reconciliation set. It is a
    superset of the ids on ``tasks`` (checkbox lines only mint Tasks, but the
    edge read is the honest source).
    """
    out = Classification()

    lines_by_title: dict[str, list[VaultTaskLine]] = defaultdict(list)
    for line in lines:
        if line.title:
            lines_by_title[normalized_activity_title(line.title)].append(line)

    tasks_by_title: dict[str, list[TaskRow]] = defaultdict(list)
    for task in tasks:
        tasks_by_title[normalized_activity_title(task.title)].append(task)

    deleted: set[str] = set()
    for key, group in sorted(tasks_by_title.items()):
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda t: t.created_at)
        title_lines = lines_by_title.get(key, [])
        if not title_lines:
            out.review.append(
                ReviewGroup(
                    title=group[0].title,
                    tasks=tuple(group),
                    reason="no vault checkbox line carries this title today — "
                    "cannot prove one line (deleted line, or a template variant)",
                )
            )
            continue
        if len(title_lines) > 1:
            out.review.append(
                ReviewGroup(
                    title=group[0].title,
                    tasks=tuple(group),
                    reason=f"{len(title_lines)} vault lines carry this title "
                    f"({', '.join(ln.where for ln in title_lines)}) — recurring, not a duplicate",
                )
            )
            continue

        line = title_lines[0]
        keeper = _keeper(group, line)
        if keeper is None:
            out.review.append(
                ReviewGroup(
                    title=group[0].title,
                    tasks=tuple(group),
                    reason=f"🆔 {line.vault_id} at {line.where} is owned by more than one task",
                )
            )
            continue
        delete = tuple(t for t in group if t is not keeper and t.is_edgeless and t.is_completed)
        leftover = tuple(t for t in group if t is not keeper and t not in delete)
        if not delete:
            out.review.append(
                ReviewGroup(
                    title=group[0].title,
                    tasks=tuple(group),
                    reason="twins all carry provenance edges or are still active — "
                    "nothing provably re-minted",
                )
            )
            continue
        deleted.update(t.uid for t in delete)
        out.duplicate_sets.append(
            DuplicateSet(line=line, keep=keeper, delete=delete, left_for_review=leftover)
        )

    line_ids = {line.vault_id for line in lines if line.vault_id}
    for line in lines:
        if line.vault_id and line.vault_id not in owned_vault_ids:
            key = normalized_activity_title(line.title)
            owners = tuple(
                t for t in tasks_by_title.get(key, []) if t.is_edgeless and t.uid not in deleted
            )
            out.phantom_ids.append(PhantomId(line=line, likely_owners=owners))
    out.dangling_ids = sorted(owned_vault_ids - line_ids)

    out.orphans = [
        t
        for t in sorted(tasks, key=lambda t: t.created_at)
        if t.is_edgeless and t.uid not in deleted
    ]
    return out


def _keeper(group: list[TaskRow], line: VaultTaskLine) -> TaskRow | None:
    """The task the line belongs to: its 🆔's owner, else the oldest. None = contested."""
    if line.vault_id:
        owners = [t for t in group if line.vault_id in t.vault_ids]
        if len(owners) > 1:
            return None
        if owners:
            return owners[0]
    return group[0]  # caller passes the group oldest-first


# ---------------------------------------------------------------------------
# Vault scan
# ---------------------------------------------------------------------------


def scan_vault_task_lines(root: Path, allowlist: SyncAllowlist | None) -> list[VaultTaskLine]:
    """Every checkbox line the extraction door would see under ``root``.

    Same eligibility as ingestion (``is_ingestible_path``: staging floor +
    allowlist + je_pro consent), then only ``pipeline: extract_activities``
    files — the one pipeline whose checkbox lines become Tasks. Lines are
    parsed by the door's own adapter so titles compare the way they were
    minted.
    """
    found: list[VaultTaskLine] = []
    for path in sorted(root.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if not is_ingestible_path(path, allowlist):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        frontmatter, _body = parse_frontmatter(text)
        try:
            pipeline = Pipeline(str(frontmatter.get("pipeline", "")).strip().casefold())
        except ValueError:
            continue
        if pipeline is not Pipeline.EXTRACT_ACTIVITIES:
            continue
        for line_no, raw in enumerate(text.splitlines(), start=1):
            parsed = obsidian_task_line_to_parsed(raw)
            if parsed is None:
                continue
            found.append(
                VaultTaskLine(
                    file=str(path.relative_to(root)),
                    line_no=line_no,
                    title=parsed.description,
                    vault_id=parsed.vault_id,
                    is_checked=parsed.is_checked,
                )
            )
    return found


# ---------------------------------------------------------------------------
# Graph reads (script tier — Cypher is allowed here, never in core/)
# ---------------------------------------------------------------------------


async def _fetch_tasks(driver: Any, user_uid: str) -> list[TaskRow]:
    result = await driver.execute_query(
        """
        MATCH (t:Task {user_uid: $user_uid})
        OPTIONAL MATCH (t)-[r:EXTRACTED_FROM]->(:UserEntry)
        WITH t, collect(r.vault_id) AS vault_ids, count(r) AS edge_count
        OPTIONAL MATCH (t)-[o]-()
        WHERE NOT type(o) IN ['OWNS', 'EXTRACTED_FROM']
        RETURN t.uid AS uid, t.title AS title, t.status AS status,
               toString(t.created_at) AS created_at,
               vault_ids, edge_count, count(o) AS other_rel_count
        ORDER BY created_at
        """,
        user_uid=user_uid,
    )
    return [
        TaskRow(
            uid=str(r["uid"]),
            title=str(r["title"] or ""),
            status=str(r["status"] or ""),
            created_at=str(r["created_at"] or ""),
            vault_ids=tuple(str(v) for v in r["vault_ids"] if v),
            edge_count=int(r["edge_count"]),
            other_rel_count=int(r["other_rel_count"]),
        )
        for r in result.records
    ]


async def _fetch_owned_vault_ids(driver: Any, user_uid: str) -> set[str]:
    result = await driver.execute_query(
        """
        MATCH ()-[r:EXTRACTED_FROM]->(ue:UserEntry {user_uid: $user_uid})
        WHERE r.vault_id IS NOT NULL
        RETURN DISTINCT r.vault_id AS vault_id
        """,
        user_uid=user_uid,
    )
    return {str(r["vault_id"]) for r in result.records}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _task_line(t: TaskRow) -> str:
    prov = "no edge" if t.is_edgeless else f"{t.edge_count} edge(s) {list(t.vault_ids) or ''}"
    extra = f", {t.other_rel_count} other rel(s)" if t.other_rel_count else ""
    return f"{t.uid}  [{t.status}]  created {t.created_at[:19]}  ({prov}{extra})"


def _print_report(c: Classification) -> None:
    bar = "=" * 72
    print(
        f"\n{bar}\nDELETE — re-mints of ONE vault line (edge-less, completed): {len(c.delete_uids)}\n{bar}"
    )
    for s in c.duplicate_sets:
        state = "[x]" if s.line.is_checked else "[ ]"
        print(f"\n  line  {s.line.where}  {state} {s.line.title!r}  🆔 {s.line.vault_id}")
        print(f"  KEEP  {_task_line(s.keep)}")
        for t in s.delete:
            print(f"  DEL   {_task_line(t)}")
        for t in s.left_for_review:
            print(f"  ...   {_task_line(t)}  ← left alone (has edges or still active)")

    print(f"\n{bar}\nREVIEW — same-title groups NOT proven duplicates: {len(c.review)}\n{bar}")
    for g in c.review:
        print(f"\n  {g.title!r} — {g.reason}")
        for t in g.tasks:
            print(f"      {_task_line(t)}")

    print(f"\n{bar}\nPHANTOM 🆔 — vault line whose id no edge owns: {len(c.phantom_ids)}\n{bar}")
    print("  The next sync of that file re-mints the line, then recovers the id onto the new")
    print("  edge. Repair = give the likely owner an EXTRACTED_FROM edge with this id (by hand).")
    for p in c.phantom_ids:
        state = "[x]" if p.line.is_checked else "[ ]"
        print(f"\n  {p.line.where}  {state} {p.line.title!r}  🆔 {p.line.vault_id}")
        for t in p.likely_owners:
            print(f"      likely owner: {_task_line(t)}")
        if not p.likely_owners:
            print("      no edge-less task carries this title")

    print(f"\n{bar}\nDANGLING ids — on edges, on no vault line today: {len(c.dangling_ids)}\n{bar}")
    if c.dangling_ids:
        print("  " + ", ".join(c.dangling_ids))
        print("  (registered: deferred-work.md § Line Deletions Leave EXTRACTED_FROM Edges)")

    print(f"\n{bar}\nORPHANS — edge-less tasks outside any duplicate set: {len(c.orphans)}\n{bar}")
    print(
        "  Pre-🆔-era minting (LLM paraphrase door, deleted entries) or app-created; a human decides."
    )
    for t in c.orphans:
        print(f"  {_task_line(t)}  {t.title!r}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--user", required=True, help="Owner uid of the personal vault + tasks")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete the DELETE set via TasksService.delete_task (cascade). "
        "REVIEW / PHANTOM / ORPHANS are never touched. Run the dry-run and get sign-off first.",
    )
    args = parser.parse_args()

    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.models.type_hints import UserUID
    from core.services.ingestion.unified_ingestion_service import UnifiedIngestionService
    from core.services.vault.vault_descriptor import VaultKind
    from services_bootstrap import compose_services

    user_uid = UserUID(args.user)
    print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        composed = await compose_services(adapter, InMemoryEventBus())
        if composed.is_error:
            print(f"ERROR: composition failed: {composed.expect_error()}", file=sys.stderr)
            return 1
        services = composed.value
        ingestion = services.unified_ingestion
        if not isinstance(ingestion, UnifiedIngestionService) or ingestion.vault_registry is None:
            print("ERROR: vault registry is not wired (check ADR-070 config)", file=sys.stderr)
            return 1
        descriptor_result = ingestion.vault_registry.resolve(VaultKind.PERSONAL, user_uid)
        if descriptor_result.is_error:
            print(f"ERROR: {descriptor_result.expect_error()}", file=sys.stderr)
            return 1
        descriptor = descriptor_result.value
        if services.tasks is None:
            print("ERROR: tasks service is not wired", file=sys.stderr)
            return 1

        driver = adapter.get_driver()
        tasks = await _fetch_tasks(driver, str(user_uid))
        owned_ids = await _fetch_owned_vault_ids(driver, str(user_uid))
        lines = scan_vault_task_lines(descriptor.root, descriptor.allowlist)
        print(
            f"{len(tasks)} task(s), {len(owned_ids)} owned 🆔(s), "
            f"{len(lines)} vault checkbox line(s) under {descriptor.root}",
            file=sys.stderr,
        )

        classification = classify(tasks, lines, owned_ids)
        _print_report(classification)

        uids = classification.delete_uids
        if not uids:
            print("\nNothing to delete — no provably re-minted twin found.")
            return 0
        if not args.apply:
            print("\n[DRY-RUN] No changes made. Re-run with --apply to delete the DELETE set.")
            return 0

        deleted = 0
        for uid in uids:
            outcome = await services.tasks.delete_task(uid)
            if outcome.is_error:
                print(f"  FAILED  {uid}: {outcome.expect_error()}")
                continue
            deleted += 1
            print(f"  deleted {uid}")
        print(
            f"\n[APPLIED] Deleted {deleted}/{len(uids)} re-minted task(s). Everything else untouched."
        )
        return 0 if deleted == len(uids) else 1
    finally:
        await adapter.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
