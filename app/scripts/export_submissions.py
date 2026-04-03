#!/usr/bin/env python3
"""
Export pending ExerciseSubmissions to markdown files for offline review.

Usage:
    uv run scripts/export_submissions.py --teacher-uid <uid>
    uv run scripts/export_submissions.py --teacher-uid <uid> --output-dir ~/my-reviews

Each submission is written to <output_dir>/pending/<submission_uid>.md.
Files that already exist are skipped (idempotent — safe to re-run).

After reviewing a submission, write your report to:
    <output_dir>/done/<submission_uid>.md

Then run import_reports.py to post reports back to SKUEL.
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml


async def main(teacher_uid: str, output_dir: Path) -> None:
    from adapters.infrastructure.event_bus import InMemoryEventBus
    from adapters.persistence.neo4j_adapter import Neo4jAdapter
    from services_bootstrap import compose_services

    print(f"Connecting to Neo4j...")
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

    pending_dir = output_dir / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "done").mkdir(exist_ok=True)
    (output_dir / "imported").mkdir(exist_ok=True)

    print(f"Fetching review queue for {teacher_uid}...")
    queue_result = await teacher_review.get_review_queue(teacher_uid)
    if queue_result.is_error:
        print(f"ERROR: {queue_result.error.message}", file=sys.stderr)
        await adapter.close()
        sys.exit(1)

    items = queue_result.value
    if not items:
        print("No pending submissions.")
        await adapter.close()
        return

    print(f"Found {len(items)} pending submission(s).")

    exported = 0
    skipped = 0

    for item in items:
        uid = item["ku_uid"]
        out_path = pending_dir / f"{uid}.md"

        if out_path.exists():
            skipped += 1
            continue

        detail_result = await teacher_review.get_submission_detail(
            submission_uid=uid, teacher_uid=teacher_uid
        )
        if detail_result.is_error:
            print(f"  WARN: Could not fetch detail for {uid}: {detail_result.error.message}")
            continue

        detail = detail_result.value
        out_path.write_text(_render_submission_md(detail, item), encoding="utf-8")
        print(f"  Exported: {out_path.name}  ({item.get('student_name', 'unknown')})")
        exported += 1

    manifest_path = output_dir / "export_manifest.json"
    manifest_data = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "teacher_uid": teacher_uid,
        "pending_uids": [item["ku_uid"] for item in items]
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    await adapter.close()
    print(f"\nDone. {exported} exported, {skipped} already present.")
    if exported:
        print(f"Files in: {pending_dir}")
        print(f"Write reports to: {output_dir / 'done'}/<submission_uid>.md")
        print(f"Then run: uv run scripts/import_reports.py --teacher-uid {teacher_uid}")


def _render_submission_md(detail: dict, queue_item: dict) -> str:
    """Render a submission as a markdown file with YAML frontmatter."""
    frontmatter = {
        "submission_uid": detail["uid"],
        "student_uid": detail.get("student_uid", ""),
        "student_name": detail.get("student_name", ""),
        "exercise_uid": detail.get("exercise_uid", ""),
        "exercise_name": detail.get("exercise_title", ""),
        "status": detail.get("status", ""),
        "submitted_at": detail.get("created_at", ""),
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "feedback_count": queue_item.get("feedback_count", 0),
    }

    title = detail.get("title") or queue_item.get("title") or "Untitled"
    student = detail.get("student_name") or detail.get("student_uid") or "Unknown"
    exercise = detail.get("exercise_title") or ""
    content = detail.get("processed_content") or detail.get("content") or "(No content)"
    instructions = detail.get("exercise_instructions") or ""

    lines = [
        "---",
        yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True).rstrip(),
        "---",
        "",
        f"# {title}",
        "",
        f"**Student:** {student}",
    ]
    if exercise:
        lines.append(f"**Exercise:** {exercise}")
    lines += [
        f"**Status:** {detail.get('status', '')}",
        "",
    ]

    if instructions:
        lines += [
            "## Exercise Instructions",
            "",
            instructions,
            "",
        ]

    lines += [
        "## Submission Content",
        "",
        content,
    ]

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export pending submissions to markdown files.")
    parser.add_argument("--teacher-uid", required=True, help="Teacher user UID")
    parser.add_argument(
        "--output-dir",
        default=str(Path.home() / "skuel-reviews"),
        help="Output directory (default: ~/skuel-reviews)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.teacher_uid, Path(args.output_dir).expanduser()))
