#!/usr/bin/env python3
# mypy: disable-error-code="union-attr"
"""
Import teacher reports from markdown files into SKUEL.

Usage:
    uv run scripts/import_reports.py --teacher-uid <uid>
    uv run scripts/import_reports.py --teacher-uid <uid> --done-dir ~/my-reviews/done

Reads every .md file from <done_dir>, posts each as an EntryReport, then
moves the processed file to <done_dir>/../imported/.

Report file format (YAML frontmatter + markdown body):

    ---
    submission_uid: es_abc123
    action: report        # report (default) | revision | approve
    ---

    Your feedback here as markdown...

Actions:
    report    — submit feedback, marks submission COMPLETED (default)
    revision  — request revision with your notes, marks REVISION_REQUESTED
    approve   — approve as-is with no written feedback

The submission_uid must match a real UserEntry. Get UIDs from
export_submissions.py — pending/<submission_uid>.md filenames are UIDs.
"""

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

from core.utils.frontmatter import parse_frontmatter


async def main(teacher_uid: str, done_dir: Path) -> None:
    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from services_bootstrap import compose_services

    if not done_dir.exists():
        print(f"Done directory does not exist: {done_dir}")
        print("Nothing to import.")
        return

    report_files = sorted(done_dir.glob("*.md"))
    if not report_files:
        print(f"No .md files found in {done_dir}")
        return

    print(f"Found {len(report_files)} file(s) to import.")
    print("Connecting to Neo4j...")

    adapter = Neo4jAdapter()
    await adapter.connect()

    event_bus = InMemoryEventBus()
    result = await compose_services(adapter, event_bus)
    if result.is_error:
        print(f"ERROR: Service composition failed: {result.error.message}", file=sys.stderr)
        await adapter.close()
        sys.exit(1)

    services = result.value
    teacher_review = services.teacher_review

    imported_dir = done_dir.parent / "imported"
    imported_dir.mkdir(exist_ok=True)

    ok_count = 0
    err_count = 0

    for path in report_files:
        text = path.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        body = body.strip()

        submission_uid = fm.get("submission_uid")
        if not submission_uid:
            print(f"  SKIP {path.name}: no submission_uid in frontmatter")
            err_count += 1
            continue

        action = (fm.get("action") or "report").lower()

        if action == "approve":
            res = await teacher_review.approve_report(
                report_uid=submission_uid,
                teacher_uid=teacher_uid,
            )
            verb = "approved"
        elif action == "revision":
            if not body:
                print(f"  SKIP {path.name}: action=revision but no revision notes in body")
                err_count += 1
                continue
            res = await teacher_review.request_revision(
                report_uid=submission_uid,
                teacher_uid=teacher_uid,
                notes=body,
            )
            verb = "revision requested"
        else:
            # Default: report
            if not body:
                print(f"  SKIP {path.name}: no report content in body")
                err_count += 1
                continue
            res = await teacher_review.submit_report(
                report_uid=submission_uid,
                teacher_uid=teacher_uid,
                feedback=body,
            )
            verb = "report submitted"

        if res.is_error:
            print(f"  ERROR {path.name}: {res.error.message}")
            err_count += 1
            continue

        dest = imported_dir / path.name
        shutil.move(str(path), str(dest))
        print(f"  OK {path.name}: {verb} → moved to imported/")
        ok_count += 1

    await adapter.close()
    print(f"\nDone. {ok_count} imported, {err_count} errors/skipped.")

    manifest_path = done_dir.parent / "export_manifest.json"
    if manifest_path.exists():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            pending_uids = manifest_data.get("pending_uids", [])
            unimported_in_done = []
            unimported_in_pending = []
            unimported_other = []

            for uid in pending_uids:
                if not (imported_dir / f"{uid}.md").exists():
                    if (done_dir / f"{uid}.md").exists():
                        unimported_in_done.append(uid)
                    elif (done_dir.parent / "pending" / f"{uid}.md").exists():
                        unimported_in_pending.append(uid)
                    else:
                        unimported_other.append(uid)

            if unimported_in_done or unimported_in_pending or unimported_other:
                print("\n--- Pending-State Reconciliation ---")
            if unimported_in_done:
                print(
                    "WARNING: The following files are in done/ but were NOT imported (check for errors):"
                )
                for uid in unimported_in_done:
                    print(f"  - {uid}.md")
            if unimported_in_pending:
                print("Note: The following files are still in pending/:")
                for uid in unimported_in_pending:
                    print(f"  - {uid}.md")
            if unimported_other:
                print(
                    "Note: The following exported files are missing (not in imported, done, or pending):"
                )
                for uid in unimported_other:
                    print(f"  - {uid}.md")
        except Exception as e:
            print(f"\nWARNING: Could not validate export_manifest.json: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import teacher reports from markdown files.")
    parser.add_argument("--teacher-uid", required=True, help="Teacher user UID")
    parser.add_argument(
        "--done-dir",
        default=str(Path.home() / "skuel-reviews" / "done"),
        help="Directory containing completed report files (default: ~/skuel-reviews/done)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.teacher_uid, Path(args.done_dir).expanduser()))
