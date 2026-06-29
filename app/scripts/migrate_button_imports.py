#!/usr/bin/env python3
"""M4 migration: move Button/ButtonT from monsterui.franken → ui.components.

Also fixes size-token tuple patterns:
    cls=(ButtonT.primary, ButtonT.sm)  →  cls=ButtonT.primary, size="sm"
    cls=(ButtonT.primary, ButtonT.sm, "extra")  →  cls=(ButtonT.primary, "extra"), size="sm"

Run from the app directory:
    uv run python scripts/migrate_button_imports.py
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Size tokens that need extracting to size= kwarg
SIZE_TOKENS = {"ButtonT.sm": "sm", "ButtonT.xs": "xs", "ButtonT.lg": "lg", "ButtonT.xl": "xl"}
SIZE_TOKEN_PAT = re.compile(r"ButtonT\.(sm|xs|lg|xl)")


def has_button_in_monster_import(content: str) -> bool:
    """Return True if file has Button or ButtonT in a monsterui.franken import."""
    pattern = re.compile(r"from\s+monsterui\.franken\s+import\s+[^\n]*\b(Button|ButtonT)\b")
    return bool(pattern.search(content))


def fix_import_lines(content: str) -> str:
    """Swap Button/ButtonT from monsterui.franken → ui.components."""
    lines = content.split("\n")
    new_lines = []
    ui_components_insert_after = -1  # line index after which to insert ui.components import
    existing_ui_components_line = -1
    existing_ui_components_names: list[str] = []
    buttons_to_add: set[str] = set()

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check if this is a monsterui.franken import line (possibly multi-line with parens)
        if re.match(r"^(\s*)from\s+monsterui\.franken\s+import\s+", line):
            indent_m = re.match(r"^(\s*)", line)
            indent = indent_m.group(1) if indent_m else ""
            # Collect the full import (may span multiple lines with parens)
            full_lines = [line]
            j = i
            if "(" in line and ")" not in line.split("#")[0]:
                j += 1
                while j < len(lines) and ")" not in lines[j].split("#")[0]:
                    full_lines.append(lines[j])
                    j += 1
                if j < len(lines):
                    full_lines.append(lines[j])

            full_import = "\n".join(full_lines)

            # Check if Button or ButtonT appear in this import
            # Parse out the imported names
            # Remove 'from monsterui.franken import' prefix and handle parens
            import_body = re.sub(r"from\s+monsterui\.franken\s+import\s+", "", full_import)
            import_body = import_body.replace("(", "").replace(")", "").replace("\n", " ")
            # Remove inline comments
            import_body = re.sub(r"#[^\n]*", "", import_body)

            names = [n.strip() for n in import_body.split(",") if n.strip()]

            btn_names = [n for n in names if n in ("Button", "ButtonT")]
            other_names = [n for n in names if n not in ("Button", "ButtonT")]

            if btn_names:
                buttons_to_add.update(btn_names)

                if other_names:
                    # Rebuild the monsterui.franken import with remaining names
                    if len(other_names) == 1:
                        new_line = f"{indent}from monsterui.franken import {other_names[0]}"
                    else:
                        new_line = f"{indent}from monsterui.franken import {', '.join(other_names)}"
                    new_lines.append(new_line)
                else:
                    # All names were Button/ButtonT — drop the line entirely
                    pass  # don't append

                # Track where to insert ui.components import
                # Use the position of the last line of this import block
                ui_components_insert_after = len(new_lines) - 1

                # Skip past multi-line import
                i = j + 1
                continue
            # No Button/ButtonT here, keep as-is (but rebuild as single line if multi-line)
            new_lines.extend(full_lines[1:] if len(full_lines) > 1 else [])
            if len(full_lines) > 1:
                new_lines.insert(len(new_lines) - len(full_lines) + 1, line)
            else:
                new_lines.append(line)
            i = j + 1
            continue

        # Check if this is a ui.components import line
        if re.match(r"^(\s*)from\s+ui\.components\s+import\s+", line):
            indent_m = re.match(r"^(\s*)", line)
            indent = indent_m.group(1) if indent_m else ""
            full_lines = [line]
            j = i
            if "(" in line and ")" not in line.split("#")[0]:
                j += 1
                while j < len(lines) and ")" not in lines[j].split("#")[0]:
                    full_lines.append(lines[j])
                    j += 1
                if j < len(lines):
                    full_lines.append(lines[j])

            full_import = "\n".join(full_lines)
            import_body = re.sub(r"from\s+ui\.components\s+import\s+", "", full_import)
            import_body = import_body.replace("(", "").replace(")", "").replace("\n", " ")
            import_body = re.sub(r"#[^\n]*", "", import_body)
            existing_names = [n.strip() for n in import_body.split(",") if n.strip()]

            existing_ui_components_line = len(new_lines)
            existing_ui_components_names = existing_names
            # Placeholder; will rebuild at end if needed
            new_lines.extend(full_lines)
            i = j + 1
            continue

        new_lines.append(line)
        i += 1

    if not buttons_to_add:
        return content  # nothing to do

    result_lines = new_lines

    if existing_ui_components_line >= 0:
        # Merge into existing ui.components import line
        all_names = existing_ui_components_names + sorted(buttons_to_add)
        # Deduplicate
        seen: set[str] = set()
        merged: list[str] = []
        for n in all_names:
            if n not in seen:
                merged.append(n)
                seen.add(n)

        # Rebuild the ui.components import lines
        indent_match = re.match(r"^(\s*)", result_lines[existing_ui_components_line])
        indent = indent_match.group(1) if indent_match else ""

        # Find the span of the old ui.components import
        old_start = existing_ui_components_line
        old_end = old_start
        while old_end < len(result_lines):
            if ")" in result_lines[old_end].split("#")[0]:
                break
            old_end += 1

        new_import_line = f"{indent}from ui.components import {', '.join(merged)}"
        result_lines[old_start : old_end + 1] = [new_import_line]
    else:
        # Insert new ui.components import line after the last monsterui.franken line we saw
        sorted_btns = sorted(buttons_to_add)
        # Determine indent of insertion point
        insert_at = ui_components_insert_after + 1
        indent = ""
        if ui_components_insert_after >= 0 and ui_components_insert_after < len(result_lines):
            indent_match = re.match(r"^(\s*)", result_lines[ui_components_insert_after])
            if indent_match:
                indent = indent_match.group(1)

        new_import_line = f"{indent}from ui.components import {', '.join(sorted_btns)}"
        result_lines.insert(insert_at, new_import_line)

    return "\n".join(result_lines)


# ── size-token tuple patterns ─────────────────────────────────────────────────
#
# We want to transform patterns like:
#   cls=(ButtonT.primary, ButtonT.sm)         → cls=ButtonT.primary, size="sm"
#   cls=(ButtonT.primary, ButtonT.sm, "foo")  → cls=(ButtonT.primary, "foo"), size="sm"
#   cls=(ButtonT.sm,)                         → size="sm"  (rare)
#
# The pattern: cls=( <items> )
# where one item is a size token.


def _rebuild_cls_with_size(match: re.Match) -> str:
    """Re-emit a cls=(...) group that contains a size token."""
    full = match.group(0)
    # Extract the tuple contents
    inner = match.group(1)

    # Split on commas (not inside strings)
    # Simple split — items won't nest further than a simple string literal
    parts = [p.strip() for p in _split_cls_parts(inner)]
    parts = [p for p in parts if p]  # drop empties

    size_token = None
    non_size_parts: list[str] = []
    for part in parts:
        matched_size = SIZE_TOKEN_PAT.match(part)
        if matched_size and part in SIZE_TOKENS:
            size_token = SIZE_TOKENS[part]
        else:
            non_size_parts.append(part)

    if size_token is None:
        return full  # no size token, leave alone

    size_kwarg = f'size="{size_token}"'

    if len(non_size_parts) == 0:
        # cls=(ButtonT.sm,) → size="sm" — need to remove cls= entirely, just return size=
        # But we need to know whether it's cls=(size,) or cls=size
        return size_kwarg
    elif len(non_size_parts) == 1:
        # cls=(ButtonT.primary, ButtonT.sm) → cls=ButtonT.primary, size="sm"
        return f"cls={non_size_parts[0]}, {size_kwarg}"
    else:
        # cls=(ButtonT.primary, ButtonT.sm, "extra") → cls=(ButtonT.primary, "extra"), size="sm"
        return f"cls=({', '.join(non_size_parts)}), {size_kwarg}"


def _split_cls_parts(s: str) -> list[str]:
    """Split comma-separated cls tuple contents, respecting quoted strings."""
    parts = []
    depth = 0
    current = []
    in_str = None
    for ch in s:
        if in_str:
            current.append(ch)
            if ch == in_str:
                in_str = None
        elif ch in ('"', "'"):
            in_str = ch
            current.append(ch)
        elif ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return parts


# Pattern to match cls=( ... ) where the parens contain something
# We need to capture the tuple contents
CLS_TUPLE_PAT = re.compile(r"cls=\(([^)]+)\)")


def fix_size_tokens(content: str) -> str:
    """Replace cls=(ButtonT.style, ButtonT.size) with cls=ButtonT.style, size="x"."""

    def replacer(m: re.Match) -> str:
        inner = m.group(1)
        # Check if any size token is present
        if not SIZE_TOKEN_PAT.search(inner):
            return m.group(0)  # no size token, leave alone
        return _rebuild_cls_with_size(m)

    return CLS_TUPLE_PAT.sub(replacer, content)


def migrate_file(path: Path) -> bool:
    """Migrate a single file. Returns True if changes were made."""
    original = path.read_text(encoding="utf-8")

    if not has_button_in_monster_import(original):
        return False

    content = fix_import_lines(original)
    content = fix_size_tokens(content)

    if content != original:
        path.write_text(content, encoding="utf-8")
        return True
    return False


def main() -> None:
    files_with_button = []
    for py_file in ROOT.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        # Skip source files
        if "ui/components/__init__.py" in str(py_file) or "ui/components/button.py" in str(py_file):
            continue
        text = py_file.read_text(encoding="utf-8")
        if has_button_in_monster_import(text):
            files_with_button.append(py_file)

    print(f"Found {len(files_with_button)} files to migrate")

    changed = 0
    for path in sorted(files_with_button):
        if migrate_file(path):
            rel = path.relative_to(ROOT)
            print(f"  ✓ {rel}")
            changed += 1
        else:
            rel = path.relative_to(ROOT)
            print(f"  ~ {rel} (no changes needed)")

    print(f"\nDone: {changed}/{len(files_with_button)} files updated")


if __name__ == "__main__":
    main()
