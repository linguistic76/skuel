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

The script PROPOSES; a human CONFIRMS. Without an edge nothing ties an
edge-less task to a line beyond its title — a completed app-created task with a
coincidental title would look identical (Codex #1165 P1) — so ``--apply``
deletes ONLY uids that are both proposed by the rule below AND passed back via
``--confirm`` / ``--confirm-file``. Any confirmed uid the current run does not
propose aborts the whole apply: the census is stale, re-read it.

Proposal rule — **one physical vault checkbox line ⇒ one task**:

  - Group the user's Tasks by the R3 semantic key (``normalized_activity_title``,
    the same normaliser Guard 4 uses).
  - A group is a RE-MINT set ONLY when the vault holds exactly ONE
    ``extract_activities`` checkbox line with that title today. Zero lines
    (deleted / template variant) or ≥2 lines (recurring template) are REVIEW.
  - Keeper = the task whose edge owns that line's 🆔; else the oldest task.
  - Proposed = the other tasks in the group that have NO ``EXTRACTED_FROM``
    edge (an edge-bearing twin may legitimately belong to another entry) AND
    are COMPLETED (an active twin is Guard 4's business — REVIEW).
  - STRAYS — edge-less COMPLETED tasks whose title matches NO vault line at all
    (the pre-🆔-era paraphrase census) — are proposed separately. A task whose
    title matches a live line is that line's task (its edge was lost), never a
    stray.

Also reported: **phantom 🆔s** — a vault line whose id no edge owns (the next
sync of that file re-mints it, then recovers the id onto the new edge). Repair
with ``--repair-id <id>``: the line's single edge-less same-title task gets the
``EXTRACTED_FROM`` edge (``vault_id`` + the door's ``source_line_hash``) on the
entry the file's OTHER owned ids point to — the reconciler's own recovery case,
applied to a task that predates the edge. A file with no owned id resolves no
entry and is refused. **Dangling ids** (on edges, on no line) are counted; that
class is registered (deferred-work.md § "Line Deletions Leave EXTRACTED_FROM
Edges").

Dry-run by default: prints every set and the exact ``--confirm`` invocation,
changes nothing. Deletions go through ``TasksService.delete_task`` (cascade +
``TaskDeleted``); repairs through ``UserEntryService.create_extracted_from_links``.

Usage:
    uv run python scripts/cleanup_duplicate_vault_tasks.py --user user_x
    uv run python scripts/cleanup_duplicate_vault_tasks.py --user user_x \\
        --apply --confirm task_a --confirm task_b --repair-id sk_abc123
    uv run python scripts/cleanup_duplicate_vault_tasks.py --user user_x \\
        --apply --confirm-file /path/to/uids.txt
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

sys.path.insert(0, str(Path(__file__).parent.parent))

from neo4j import EagerResult

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.pipeline import Pipeline
from core.models.relationship_names import RelationshipName
from core.services.dsl.activity_extractor import normalized_activity_title, normalized_line_hash
from core.services.dsl.obsidian_tasks_adapter import obsidian_task_line_to_parsed
from core.services.ingestion.config import SyncAllowlist, collect_files
from core.utils.frontmatter import parse_frontmatter


class _ReadDriver(Protocol):
    """The one driver call this script makes (script-tier read; Cypher lives here, not core/)."""

    async def execute_query(self, query: str, /, **parameters: object) -> EagerResult: ...


@dataclass(frozen=True)
class VaultTaskLine:
    """One checkbox line as the extraction door sees it."""

    file: str  # vault-relative path
    line_no: int  # 1-based
    title: str  # the description the door persists as ``Task.title``
    vault_id: str | None
    is_checked: bool
    raw_line: str = ""  # the door's normalized raw line — what ``source_line_hash`` digests

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
    """A title group proven to be one vault line: keep one, propose the re-mints."""

    line: VaultTaskLine
    keep: TaskRow
    proposed: tuple[TaskRow, ...]
    left_for_review: tuple[TaskRow, ...]  # twins that fail the proposal criteria


@dataclass(frozen=True)
class ReviewGroup:
    title: str
    tasks: tuple[TaskRow, ...]
    reason: str


@dataclass(frozen=True)
class PhantomId:
    line: VaultTaskLine
    likely_owners: tuple[TaskRow, ...]  # edge-less tasks with the line's title


@dataclass(frozen=True)
class Repair:
    """One EXTRACTED_FROM edge to write: ``(task_uid, source_line_hash, vault_id)`` on ``entry_uid``."""

    phantom: PhantomId
    task: TaskRow
    entry_uid: str

    @property
    def link(self) -> tuple[str, str, str | None]:
        return (
            self.task.uid,
            normalized_line_hash(self.phantom.line.raw_line),
            self.phantom.line.vault_id,
        )


@dataclass
class Classification:
    duplicate_sets: list[DuplicateSet] = field(default_factory=list)
    review: list[ReviewGroup] = field(default_factory=list)
    phantom_ids: list[PhantomId] = field(default_factory=list)
    dangling_ids: list[str] = field(default_factory=list)
    strays: list[TaskRow] = field(default_factory=list)
    line_backed: list[TaskRow] = field(default_factory=list)  # edge-less, but a live line's task

    @property
    def remint_uids(self) -> list[str]:
        return [t.uid for s in self.duplicate_sets for t in s.proposed]

    @property
    def proposed_uids(self) -> list[str]:
        return self.remint_uids + [t.uid for t in self.strays]


# ---------------------------------------------------------------------------
# Pure rules
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

    proposed: set[str] = set()
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
        remints = tuple(t for t in group if t is not keeper and t.is_edgeless and t.is_completed)
        leftover = tuple(t for t in group if t is not keeper and t not in remints)
        if not remints:
            out.review.append(
                ReviewGroup(
                    title=group[0].title,
                    tasks=tuple(group),
                    reason="twins all carry provenance edges or are still active — "
                    "nothing provably re-minted",
                )
            )
            continue
        proposed.update(t.uid for t in remints)
        out.duplicate_sets.append(
            DuplicateSet(line=line, keep=keeper, proposed=remints, left_for_review=leftover)
        )

    line_ids = {line.vault_id for line in lines if line.vault_id}
    for line in lines:
        if line.vault_id and line.vault_id not in owned_vault_ids:
            key = normalized_activity_title(line.title)
            owners = tuple(
                t for t in tasks_by_title.get(key, []) if t.is_edgeless and t.uid not in proposed
            )
            out.phantom_ids.append(PhantomId(line=line, likely_owners=owners))
    out.dangling_ids = sorted(owned_vault_ids - line_ids)

    # Edge-less survivors: a live line with the same title makes the task that
    # line's task (its edge was lost) — never a stray. No line at all = stray.
    for task in sorted(tasks, key=lambda t: t.created_at):
        if not task.is_edgeless or task.uid in proposed:
            continue
        if normalized_activity_title(task.title) in lines_by_title:
            out.line_backed.append(task)
        elif task.is_completed:
            out.strays.append(task)
        else:
            out.line_backed.append(task)  # active + edge-less: could be app-created; not ours
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


def select_confirmed(proposed: list[str], confirmed: list[str]) -> tuple[list[str], list[str]]:
    """``(to_delete, refused)`` — the human census intersected with this run's proposals.

    A confirmed uid the run does not propose is REFUSED (stale census, typo, or
    a task the rule never tied to a line); the caller aborts on any refusal.
    Order follows ``proposed`` so the apply log reads like the report.
    """
    wanted = {uid.strip() for uid in confirmed if uid.strip()}
    to_delete = [uid for uid in proposed if uid in wanted]
    refused = sorted(wanted - set(proposed))
    return to_delete, refused


def entry_for_file(lines: list[VaultTaskLine], owned: dict[str, set[str]]) -> dict[str, str | None]:
    """``file → entry_uid`` from the owned 🆔s the file's lines carry.

    Periodic entries carry no ``vault_file_path``; the ids on their edges are
    the only honest file↔entry link. ``owned`` keeps EVERY entry an id's edges
    reach (an id with edges into two entries is itself ambiguous — Codex #1165
    r4), and a file whose owned ids reach more than one entry resolves to
    ``None`` — as does a file with no owned id.
    """
    seen: dict[str, set[str]] = defaultdict(set)
    for line in lines:
        if line.vault_id and line.vault_id in owned:
            seen[line.file] |= owned[line.vault_id]
    return {
        file: next(iter(entries)) if len(entries) == 1 else None for file, entries in seen.items()
    }


def plan_repairs(
    classification: Classification,
    repair_ids: list[str],
    file_entry: dict[str, str | None],
) -> tuple[list[Repair], list[str]]:
    """``(repairs, problems)`` — every requested id must be ONE line with ONE owner + ONE entry.

    A 🆔 copied onto two vault lines is ambiguous: repairing either line would
    write provenance the other then inherits (ownership is checked globally),
    so the id is refused outright (Codex #1165 r3). The mirror case is refused
    too: a task that is the sole candidate for TWO phantom lines (same title,
    different ids) has no knowable line — repairing one would attribute it
    arbitrarily, repairing both would write it twice (Codex #1165 r5).
    """
    lines_by_id: dict[str, list[PhantomId]] = defaultdict(list)
    lines_per_task: dict[str, int] = defaultdict(int)
    for phantom in classification.phantom_ids:
        if phantom.line.vault_id:
            lines_by_id[phantom.line.vault_id].append(phantom)
        for owner in phantom.likely_owners:
            lines_per_task[owner.uid] += 1
    repairs: list[Repair] = []
    problems: list[str] = []
    for vault_id in repair_ids:
        candidates = lines_by_id.get(vault_id, [])
        if not candidates:
            problems.append(f"{vault_id}: not a phantom id in this run (owned, or on no line)")
            continue
        if len(candidates) > 1:
            problems.append(
                f"{vault_id}: {len(candidates)} vault lines carry this id "
                f"({', '.join(p.line.where for p in candidates)}) — ambiguous, fix the vault first"
            )
            continue
        phantom = candidates[0]
        if len(phantom.likely_owners) != 1:
            problems.append(
                f"{vault_id}: {len(phantom.likely_owners)} edge-less task(s) carry the line's "
                f"title at {phantom.line.where} — need exactly one"
            )
            continue
        task = phantom.likely_owners[0]
        if lines_per_task[task.uid] > 1:
            problems.append(
                f"{vault_id}: {task.uid} is the sole candidate for "
                f"{lines_per_task[task.uid]} phantom lines — its line is not knowable"
            )
            continue
        entry_uid = file_entry.get(phantom.line.file)
        if entry_uid is None:
            problems.append(
                f"{vault_id}: {phantom.line.file} resolves to no single entry "
                "(no other owned 🆔 in the file) — re-sync the file first"
            )
            continue
        repairs.append(Repair(phantom=phantom, task=task, entry_uid=entry_uid))
    return repairs, problems


# ---------------------------------------------------------------------------
# Vault scan
# ---------------------------------------------------------------------------


def scan_vault_task_lines(root: Path, allowlist: SyncAllowlist | None) -> list[VaultTaskLine]:
    """Every checkbox line the extraction door would see under ``root``.

    The file set IS ingestion's: ``collect_files`` (the same collector the
    reconciler's ingest runs — staging floor, allowlist, je_pro consent, and
    NO extra hidden-directory rule, since pathlib's ``**`` glob does not skip
    dot-directories either; Codex #1165 r2). Then only ``pipeline:
    extract_activities`` files — the one pipeline whose checkbox lines become
    Tasks. Lines are parsed by the door's own adapter so titles compare the
    way they were minted and hashes digest the way Guard 2 digests them.
    """
    found: list[VaultTaskLine] = []
    for path in sorted(collect_files(root, "*.md", allowlist)):
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
                    raw_line=parsed.raw_line or "",
                )
            )
    return found


# ---------------------------------------------------------------------------
# Graph reads (script tier — Cypher is allowed here, never in core/)
# ---------------------------------------------------------------------------


async def _fetch_tasks(driver: _ReadDriver, user_uid: str) -> list[TaskRow]:
    result = await driver.execute_query(
        """
        MATCH (t:Task {user_uid: $user_uid})
        OPTIONAL MATCH (t)-[r:EXTRACTED_FROM]->(:UserEntry)
        WITH t, collect(r.vault_id) AS vault_ids, count(r) AS edge_count
        OPTIONAL MATCH (t)-[o]-()
        WHERE NOT type(o) IN $provenance_types
        RETURN t.uid AS uid, t.title AS title, t.status AS status,
               toString(t.created_at) AS created_at,
               vault_ids, edge_count, count(o) AS other_rel_count
        ORDER BY created_at
        """,
        user_uid=user_uid,
        # The two edges every vault task carries by construction; anything else
        # is a relationship the human should see before confirming a deletion.
        provenance_types=[RelationshipName.OWNS.value, RelationshipName.EXTRACTED_FROM.value],
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


async def _fetch_owned_vault_ids(driver: _ReadDriver, user_uid: str) -> dict[str, set[str]]:
    """``vault_id → {entry_uid, …}`` for every 🆔 an EXTRACTED_FROM edge into this user's entries carries.

    Every entry per id, not one: the rows carry no ordering, so keeping "the"
    entry would pick an arbitrary one for an id that reaches two.
    """
    result = await driver.execute_query(
        """
        MATCH ()-[r:EXTRACTED_FROM]->(ue:UserEntry {user_uid: $user_uid})
        WHERE r.vault_id IS NOT NULL
        RETURN DISTINCT r.vault_id AS vault_id, ue.uid AS entry_uid
        """,
        user_uid=user_uid,
    )
    owned: dict[str, set[str]] = defaultdict(set)
    for r in result.records:
        owned[str(r["vault_id"])].add(str(r["entry_uid"]))
    return dict(owned)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _task_line(t: TaskRow) -> str:
    prov = "no edge" if t.is_edgeless else f"{t.edge_count} edge(s) {list(t.vault_ids) or ''}"
    extra = f", {t.other_rel_count} other rel(s)" if t.other_rel_count else ""
    return f"{t.uid}  [{t.status}]  created {t.created_at[:19]}  ({prov}{extra})"


def _print_report(c: Classification, user_uid: str) -> None:
    bar = "=" * 72
    print(
        f"\n{bar}\nPROPOSED re-mints of ONE vault line (edge-less, completed): {len(c.remint_uids)}\n{bar}"
    )
    for s in c.duplicate_sets:
        state = "[x]" if s.line.is_checked else "[ ]"
        print(f"\n  line  {s.line.where}  {state} {s.line.title!r}  🆔 {s.line.vault_id}")
        print(f"  KEEP  {_task_line(s.keep)}")
        for t in s.proposed:
            print(f"  DEL?  {_task_line(t)}")
        for t in s.left_for_review:
            print(f"  ...   {_task_line(t)}  ← left alone (has edges or still active)")

    print(
        f"\n{bar}\nPROPOSED strays — edge-less, completed, title on NO vault line: {len(c.strays)}\n{bar}"
    )
    print(
        "  Pre-🆔-era minting (LLM paraphrase door, deleted entries) or app-created; a human decides."
    )
    for t in c.strays:
        print(f"  DEL?  {_task_line(t)}  {t.title!r}")

    print(f"\n{bar}\nREVIEW — same-title groups NOT proven duplicates: {len(c.review)}\n{bar}")
    for g in c.review:
        print(f"\n  {g.title!r} — {g.reason}")
        for t in g.tasks:
            print(f"      {_task_line(t)}")

    print(
        f"\n{bar}\nLINE-BACKED — edge-less, but a live vault line carries the title: {len(c.line_backed)}\n{bar}"
    )
    print("  That line's task with its edge lost (or an active app-created task). Never proposed.")
    for t in c.line_backed:
        print(f"  {_task_line(t)}  {t.title!r}")

    print(f"\n{bar}\nPHANTOM 🆔 — vault line whose id no edge owns: {len(c.phantom_ids)}\n{bar}")
    print("  The next sync of that file re-mints the line, then recovers the id onto the new edge.")
    print("  Repair with --repair-id <id> when exactly one edge-less task carries the title.")
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

    if c.proposed_uids:
        confirms = " ".join(f"--confirm {uid}" for uid in c.proposed_uids)
        print(
            f"\nTo delete everything proposed above, after reading it:\n  uv run python {sys.argv[0]} --user {user_uid} --apply {confirms}"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _read_confirm_file(path: str) -> list[str]:
    return [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--user", required=True, help="Owner uid of the personal vault + tasks")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Act: delete the --confirm'd proposed uids and write the --repair-id edges. "
        "Run the dry-run and read it first.",
    )
    parser.add_argument(
        "--confirm",
        action="append",
        default=[],
        metavar="UID",
        help="A proposed task uid to delete (repeatable). Refused if this run does not propose it.",
    )
    parser.add_argument(
        "--confirm-file", metavar="PATH", help="File with one proposed task uid per line to delete."
    )
    parser.add_argument(
        "--repair-id",
        action="append",
        default=[],
        metavar="ID",
        help="A phantom 🆔 to repair by giving its single edge-less owner the EXTRACTED_FROM edge.",
    )
    args = parser.parse_args()
    confirmed: list[str] = list(args.confirm)
    if args.confirm_file:
        confirmed.extend(_read_confirm_file(args.confirm_file))
    if args.apply and not confirmed and not args.repair_id:
        parser.error("--apply needs at least one --confirm/--confirm-file uid or --repair-id")
    if (confirmed or args.repair_id) and not args.apply:
        parser.error("--confirm/--repair-id only act together with --apply (dry-run ignores them)")

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
        if services.tasks is None or services.user_entry is None:
            print("ERROR: tasks / user_entry services are not wired", file=sys.stderr)
            return 1

        driver: _ReadDriver = adapter.get_driver()
        tasks = await _fetch_tasks(driver, str(user_uid))
        owned = await _fetch_owned_vault_ids(driver, str(user_uid))
        lines = scan_vault_task_lines(descriptor.root, descriptor.allowlist)
        print(
            f"{len(tasks)} task(s), {len(owned)} owned 🆔(s), "
            f"{len(lines)} vault checkbox line(s) under {descriptor.root}",
            file=sys.stderr,
        )

        classification = classify(tasks, lines, set(owned))
        _print_report(classification, str(user_uid))

        if not args.apply:
            print("\n[DRY-RUN] No changes made.")
            return 0

        to_delete, refused = select_confirmed(classification.proposed_uids, confirmed)
        repairs, problems = plan_repairs(
            classification, list(args.repair_id), entry_for_file(lines, owned)
        )
        if refused or problems:
            for uid in refused:
                print(f"  REFUSED {uid}: not proposed by this run — re-read the dry-run")
            for problem in problems:
                print(f"  REFUSED repair {problem}")
            print("\n[ABORTED] Nothing changed: every --confirm / --repair-id must match this run.")
            return 1

        repaired = 0
        for repair in repairs:
            outcome = await services.user_entry.create_extracted_from_links(
                repair.entry_uid, [repair.link]
            )
            if outcome.is_error:
                print(f"  FAILED repair {repair.phantom.line.vault_id}: {outcome.expect_error()}")
                continue
            repaired += 1
            print(
                f"  repaired {repair.phantom.line.vault_id}: {repair.task.uid} "
                f"-[:EXTRACTED_FROM]-> {repair.entry_uid} ({repair.phantom.line.where})"
            )

        deleted = 0
        for uid in to_delete:
            deletion = await services.tasks.delete_task(uid)
            if deletion.is_error:
                print(f"  FAILED delete {uid}: {deletion.expect_error()}")
                continue
            deleted += 1
            print(f"  deleted {uid}")

        print(
            f"\n[APPLIED] {repaired}/{len(repairs)} repair(s), {deleted}/{len(to_delete)} "
            "deletion(s). Everything not confirmed is untouched."
        )
        return 0 if (repaired == len(repairs) and deleted == len(to_delete)) else 1
    finally:
        await adapter.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
