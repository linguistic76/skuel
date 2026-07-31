#!/usr/bin/env python3
"""Give pre-existing FormSubmissions the audience they were created without.

A ONE-SHOT migration — no background loop, so the CORE "no background workers"
guarantee holds.

Teacher access to a form submission is gated on the submission's own audience
(the Model B gate: a ``SHARED_WITH_GROUP`` edge to an active group the teacher
owns, or a direct ``SHARES_WITH``). Submissions created before submit-time
audience resolution existed carry no share edges at all — the PathStep-embedded
form path passed no ``group_uid`` and no ``recipient_uids``, and every branch of
the sharing step was conditional. Under the gate those submissions are readable
by nobody but their owner and admins.

This backfills exactly the audience a fresh submit would now resolve: each
submission is shared with every active group its submitter is a *student*
member of. Nothing wider — there is no implicit "share with everyone"
fallback, matching ``AudienceResolver.resolve_default_teachers``, which this
mirrors. A submitter in no group is left private, deliberately: there is no
audience to infer, and inventing one would expose their answers to a classroom
they are not in.

**Only submissions with no audience at all are touched.** One that already
names an audience was scoped deliberately — via ``group_uid`` or
``recipient_uids`` — and adding the submitter's other classrooms would hand
their answers to teachers they did not pick. A migration for this gate must
never widen an existing audience; that is the leak the gate exists to stop.

**And only submissions answering a PathStep-embedded template.** This is the
limit of what can be inferred, and it is worth stating plainly: having no
audience does not prove a submission was meant to be shared.
``/api/form-submissions/submit`` takes ``group_uid`` and ``recipient_uids``
from the caller, both optional, so a submission with neither may well be one
someone chose to keep private — and nothing on the node records which route
created it. The ``EMBEDS_FORM`` restriction keeps every submission that had no
*way* to declare an audience (the embedded route can only answer embedded
templates) while dropping API submissions of ordinary templates. An API
submission of an *embedded* template remains indistinguishable.

**The audience is a reconstruction, not a record.** It is resolved as of
``fs.created_at`` — only classrooms the submitter had already joined — but the
graph stores current membership state, not its history. ``MEMBER_OF`` carries
when the edge was created and not when its role last changed, so a membership
edited after the fact reads as though it always held that role. Recording role
history would fix this going forward and change nothing here, since no existing
edge carries it.

Because that residue cannot be resolved from the data, writing requires
``--confirm``. Run ``--dry-run`` first: it prints each submission with **the
classrooms it would be shared into**, which is the only reviewable form of a
reconstruction — a list of UIDs cannot be checked by anyone.

Each submission's whole audience is written in a single statement, so there is
no half-migrated state: a failure leaves the submission untouched and it is
picked up again on the next run. Safe to re-run, and safe to interrupt.

Usage:
    uv run scripts/backfill_form_submission_audience.py --dry-run   # list candidates
    uv run scripts/backfill_form_submission_audience.py --confirm   # backfill
    uv run scripts/backfill_form_submission_audience.py --confirm --after-uid fs_...
"""

from __future__ import annotations

import argparse
import asyncio
import sys

# Submissions fetched per query. Paging is by UID cursor, so this bounds memory
# without bounding how much the run completes.
DEFAULT_BATCH_SIZE = 500

# Backstop against a cursor that fails to advance — a bug here would otherwise
# spin forever against the database.
MAX_BATCHES = 10_000


async def run_backfill(*, batch_size: int, dry_run: bool, after_uid: str) -> int:
    """Walk every audience-less submission and give it its default audience."""
    from adapters.persistence.neo4j.backends.forms_backends import FormSubmissionBackend
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from core.models.enums.neo_labels import NeoLabel
    from core.models.forms.form_submission import FormSubmission

    print("Connecting to Neo4j...", file=sys.stderr)
    adapter = Neo4jAdapter()
    await adapter.connect()
    try:
        submissions = FormSubmissionBackend(
            driver=adapter.get_driver(),
            label=NeoLabel.FORM_SUBMISSION,
            entity_class=FormSubmission,
            base_label=NeoLabel.ENTITY,
        )

        cursor = after_uid
        examined = 0
        shared = 0
        left_private = 0
        failed: list[tuple[str, str]] = []
        batches = 0

        while batches < MAX_BATCHES:
            batches += 1
            page = await submissions.find_submissions_without_audience(cursor, batch_size)
            if page.is_error:
                print(f"ERROR listing submissions: {page.expect_error()}", file=sys.stderr)
                return 1
            rows = page.value or []
            if not rows:
                break

            for row in rows:
                submission_uid = row["submission_uid"]
                examined += 1

                if dry_run:
                    # Show the target classrooms, not just the candidate. The
                    # operator is being asked to confirm a reconstruction the
                    # data cannot fully justify, and "which group would this
                    # answer go to" is the only reviewable form of that.
                    preview = await submissions.preview_default_audience(submission_uid)
                    if preview.is_error:
                        failed.append((submission_uid, str(preview.expect_error())))
                        continue
                    targets = sorted(row["group_uid"] for row in preview.value or [])
                    shared += len(targets)
                    if targets:
                        print(
                            f"  {submission_uid} (submitter {row['owner_uid']}) "
                            f"→ {', '.join(targets)}"
                        )
                    else:
                        left_private += 1
                    continue

                result = await submissions.share_with_default_audience(submission_uid)
                if result.is_error:
                    failed.append((submission_uid, str(result.expect_error())))
                    continue
                written = result.value or []
                if written:
                    shared += len(written)
                else:
                    # Either the submitter studies in no active group, or an
                    # explicit share landed since this row was selected — the
                    # write re-checks. Both mean "leave it alone", not a failure.
                    left_private += 1

            # Advance past this page even when a write failed, so one bad row
            # cannot stall the walk. A failure resurfaces on the next run: the
            # write is atomic, so a failed submission still has no audience and
            # is selected again. Rows left private stay selected too, but the
            # cursor means they cannot block the rows behind them.
            cursor = rows[-1]["submission_uid"]

        # Hitting the backstop is not proof work remains: if the last non-empty
        # page happened to be batch MAX_BATCHES, the loop exits without ever
        # issuing the empty query that would have shown the cursor drained.
        # Reporting "unfinished" there would fail a migration that finished, so
        # probe once past the cursor and let the answer decide.
        exhausted = False
        if batches >= MAX_BATCHES:
            probe = await submissions.find_submissions_without_audience(cursor, 1)
            if probe.is_error:
                print(f"ERROR probing for remaining work: {probe.expect_error()}", file=sys.stderr)
                return 1
            exhausted = bool(probe.value)
        _print_report(
            examined=examined,
            shared=shared,
            left_private=left_private,
            failed=failed,
            exhausted=exhausted,
            resume_from=cursor,
            dry_run=dry_run,
        )
        # Exhausting the backstop means work remains. An operator or wrapper
        # checking only the exit status would otherwise read "stopped early"
        # as "finished", leaving later submissions with no audience.
        return 1 if failed or exhausted else 0
    finally:
        await adapter.close()


def _print_report(
    *,
    examined: int,
    shared: int,
    left_private: int,
    failed: list[tuple[str, str]],
    exhausted: bool,
    resume_from: str,
    dry_run: bool,
) -> None:
    """Render the outcome, including anything left undone."""
    if not examined:
        print("\nNo submissions are missing an audience — nothing to backfill.\n")
        return

    verb = "would create" if dry_run else "created"
    header = "DRY RUN (nothing written)" if dry_run else "Backfill complete"
    print(f"\n=== FormSubmission audience backfill — {header} ===\n")
    print(f"  Candidate submissions             {examined:>8,}")
    print(f"  Share edges {verb:<21} {shared:>8,}")
    print(f"  Left alone (no groups, or newly shared) {left_private:>8,}")
    if dry_run:
        print(
            "\n  The arrows above are this migration's *reconstruction* of who each\n"
            "  answer was for. Membership history is not recorded, so it cannot be\n"
            "  derived — check the classrooms, then re-run with --confirm."
        )
    if failed:
        print(f"\n  FAILED ({len(failed)}):")
        for target, reason in failed[:20]:
            print(f"    {target}: {reason}")
        if len(failed) > 20:
            print(f"    ... and {len(failed) - 20} more")
    if exhausted:
        # Never let a truncated walk read as "everything is done" — and the
        # cursor is in-memory only, so "re-run" has to carry the resume point
        # or the next run rescans the same prefix and can never get past it.
        print(f"\n  NOTE: stopped at the {MAX_BATCHES:,}-batch backstop without draining.")
        if failed:
            # The cursor advanced past the failures listed above, so resuming
            # from it would skip them permanently. A plain re-run picks them up:
            # the selection is idempotent and a failed row still has no audience.
            print("  Re-run WITHOUT --after-uid — the failures above are behind the cursor.")
        else:
            print(f"  Resume with:  --after-uid {resume_from}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill the default audience on FormSubmissions created before "
            "submit-time audience resolution. One-shot, idempotent, resumable."
        )
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"submissions fetched per query, minimum 1 (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--after-uid",
        default="",
        help=(
            "resume the walk strictly after this submission UID. Printed by a run "
            "that stops at the batch backstop; the cursor is not persisted between "
            "runs, so without it a re-run restarts from the beginning."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list every candidate submission without writing any edge",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help=(
            "actually write the share edges. Required: the selection cannot prove "
            "an audience-less submission was meant to be shared, so sharing one is "
            "a judgement call, not a derivation. Run --dry-run first."
        ),
    )
    args = parser.parse_args()

    if args.batch_size < 1:
        # LIMIT 0 returns no rows, so the run would report "nothing to
        # backfill" and exit 0 having inspected nothing.
        parser.error("--batch-size must be at least 1")

    if not args.dry_run and not args.confirm:
        parser.error(
            "refusing to write without --confirm. This shares student answers with "
            "their teachers and cannot be undone by re-running. Start with --dry-run "
            "to see exactly which submissions would be affected."
        )

    sys.exit(
        asyncio.run(
            run_backfill(
                batch_size=args.batch_size,
                dry_run=args.dry_run,
                after_uid=args.after_uid,
            )
        )
    )


if __name__ == "__main__":
    main()
