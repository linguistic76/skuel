"""M6 migration: replace UkIcon with Icon from ui.components across 29 files."""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

FILES = [
    "ui/activities/_shared.py",
    "ui/activities/choices_views.py",
    "ui/activities/events_views.py",
    "ui/activities/goals_views.py",
    "ui/activities/habits_views.py",
    "ui/activities/principles_views.py",
    "ui/activities/tasks_views.py",
    "ui/askesis/chat.py",
    "ui/calendar/components.py",
    "ui/explore/graph.py",
    "ui/explore/ku_detail.py",
    "ui/explore/ku_mastery.py",
    "ui/explore/ps_detail.py",
    "ui/explore/reading_plan.py",
    "ui/journals/__init__.py",
    "ui/journals/chat_page.py",
    "ui/journals/forms.py",
    "ui/layouts/navbar.py",
    "ui/layouts/nav_config.py",
    "ui/patterns/form_generator.py",
    "ui/patterns/hub.py",
    "ui/patterns/sidebar.py",
    "ui/system/landing.py",
    "ui/teaching/student_hub.py",
    "ui/today/page.py",
    "ui/user_entry/forms.py",
    "adapters/inbound/library_ui.py",
    "adapters/inbound/teaching_ui.py",
    "adapters/inbound/user_entry_ui.py",
]

# nav_config.py: update comment only, no import to add
NAV_CONFIG = "ui/layouts/nav_config.py"

# journals/__init__.py: local imports inside function bodies
JOURNALS_INIT = "ui/journals/__init__.py"


def migrate_file(rel_path: str) -> int:
    path = ROOT / rel_path
    original = path.read_text()
    text = original

    if rel_path == NAV_CONFIG:
        # Only update the comment string, no import changes
        text = text.replace(
            '"renders UkIcon instead of letter"',
            '"renders Icon instead of letter"',
        )
        if text != original:
            path.write_text(text)
            print(f"  [comment] {rel_path}")
            return 1
        return 0

    if rel_path == JOURNALS_INIT:
        # Local imports inside function bodies + call sites
        text = text.replace(
            "from monsterui.franken import UkIcon",
            "from ui.components import Icon",
        )
    else:
        # Top-level import: replace the UkIcon import line
        # Some files may also import other things from monsterui.franken
        text = re.sub(
            r"from monsterui\.franken import UkIcon\n",
            "from ui.components import Icon\n",
            text,
        )
        # Also handle: "from monsterui.franken import Foo, UkIcon" or similar (shouldn't exist
        # for these files, but guard against it)
        text = re.sub(
            r"(from monsterui\.franken import .*?),\s*UkIcon",
            r"\1",
            text,
        )
        text = re.sub(
            r"(from monsterui\.franken import )UkIcon,\s*",
            r"\1",
            text,
        )

    # Rename the call: UkIcon( → Icon(
    text = text.replace("UkIcon(", "Icon(")

    # --- Convert height=N, width=N to size=N ---

    # 1. Multi-line: height=N,\n<whitespace>width=N,
    #    Replace the two-line form with single size= line
    text = re.sub(
        r"height=(\d+),\n(\s+)width=\1,",
        r"size=\1,",
        text,
    )

    # 2. Single-line inline: height=N, width=N (with optional trailing comma)
    text = re.sub(
        r"height=(\d+),\s*width=\1\b",
        r"size=\1",
        text,
    )

    if text != original:
        path.write_text(text)
        return 1
    return 0


def main() -> None:
    changed = 0
    for rel_path in FILES:
        n = migrate_file(rel_path)
        if n:
            print(f"  [ok] {rel_path}")
            changed += 1
        else:
            print(f"  [--] {rel_path} (no changes)")
    print(f"\nDone: {changed}/{len(FILES)} files changed.")


if __name__ == "__main__":
    main()
