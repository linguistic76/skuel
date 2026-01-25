#!/usr/bin/env python3
"""
LLM-Assisted Documentation Updater

Uses Claude to read stale documentation and the code files they reference,
then generates updated documentation for human approval.

Workflow:
1. Detect stale docs (via docs_freshness.py)
2. For each stale doc:
   a. Read current doc content
   b. Read all referenced code files
   c. Build context prompt for Claude
   d. Call Claude API to generate updated doc
   e. Show diff to user
   f. Apply if approved, or skip
3. Update doc mtime on completion

Usage:
    poetry run python scripts/docs_update.py --doc docs/patterns/metadata_manager_mixin.md
    poetry run python scripts/docs_update.py --all
    poetry run python scripts/docs_update.py --all --dry-run
    poetry run python scripts/docs_update.py --all --yes
"""

import argparse
import difflib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Add project root to path for imports
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

import anthropic
from anthropic.types import TextBlock

from scripts.docs_freshness import (
    DocFreshness,
    check_freshness,
    extract_code_refs,
    normalize_path,
    scan_docs,
)

# ANSI color codes for terminal output
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


SYSTEM_PROMPT = """You are a documentation maintainer. Given a markdown doc and
the current code it references, update the doc to reflect code changes.

Rules:
- Preserve document structure, headings, and voice
- Update method signatures to match current code
- Update line counts if mentioned (e.g., "~530 lines")
- Update code examples if they no longer compile/match
- Do NOT rewrite rationale/philosophy sections unless factually wrong
- Do NOT add new sections or remove existing ones unless necessary
- Do NOT change the overall tone or writing style
- Return the COMPLETE updated document, not a diff
- If the code has changed significantly, update the documentation to reflect the new patterns
- Pay attention to imports, function signatures, class names, and method names
- If a referenced file no longer exists, note this appropriately or remove the reference"""


@dataclass
class UpdateContext:
    """Context for updating a single documentation file."""

    doc_path: Path
    doc_content: str
    code_files: dict[str, str]  # path -> content
    stale_refs: list[str]
    freshness: DocFreshness


def gather_context(doc_path: Path, project_root: Path) -> UpdateContext | None:
    """
    Read doc and all referenced code files to build update context.

    Returns None if the doc has no stale references.
    """
    freshness = check_freshness(doc_path, project_root)

    if not freshness.is_stale:
        return None

    doc_content = doc_path.read_text(encoding="utf-8")

    # Get all code references (not just stale ones - context is important)
    code_refs = extract_code_refs(doc_path)
    code_files: dict[str, str] = {}

    for ref in code_refs:
        # Convert to absolute path
        normalized = normalize_path(ref)
        if normalized.startswith("/"):
            full_path = project_root / normalized.lstrip("/")
        else:
            full_path = project_root / normalized

        if full_path.exists():
            if full_path.is_file():
                try:
                    code_files[ref] = full_path.read_text(encoding="utf-8")
                except Exception:
                    code_files[ref] = f"[Error reading file: {ref}]"
            elif full_path.is_dir():
                # For directories, list the files and read key ones
                file_list = []
                for f in full_path.rglob("*.py"):
                    if not f.name.startswith("_") or f.name == "__init__.py":
                        file_list.append(str(f.relative_to(project_root)))
                code_files[ref] = f"[Directory containing: {', '.join(sorted(file_list)[:20])}]"
        else:
            code_files[ref] = f"[File not found: {ref}]"

    stale_refs = [r.code_path for r in freshness.stale_refs]

    return UpdateContext(
        doc_path=doc_path,
        doc_content=doc_content,
        code_files=code_files,
        stale_refs=stale_refs,
        freshness=freshness,
    )


def build_prompt(context: UpdateContext) -> str:
    """Build the user prompt for Claude with doc + code context."""
    prompt_parts = []

    prompt_parts.append("## Current Documentation\n")
    prompt_parts.append(f"**File:** `{context.doc_path}`\n")
    prompt_parts.append("```markdown")
    prompt_parts.append(context.doc_content)
    prompt_parts.append("```\n")

    prompt_parts.append("## Stale References (code files newer than doc)\n")
    for ref in context.stale_refs:
        prompt_parts.append(f"- `{ref}`")
    prompt_parts.append("")

    prompt_parts.append("## Referenced Code Files\n")
    for path, content in context.code_files.items():
        is_stale = path in context.stale_refs
        marker = " **(STALE - code is newer)**" if is_stale else ""
        prompt_parts.append(f"### `{path}`{marker}\n")

        if content.startswith("["):
            # Error or directory marker
            prompt_parts.append(content)
        else:
            # Actual file content - truncate if very long
            if len(content) > 15000:
                content = content[:15000] + "\n\n... [truncated, file continues] ..."
            prompt_parts.append("```python")
            prompt_parts.append(content)
            prompt_parts.append("```")
        prompt_parts.append("")

    prompt_parts.append(
        "## Task\n"
        "Update the documentation to reflect the current code. "
        "Return the COMPLETE updated markdown document."
    )

    return "\n".join(prompt_parts)


def generate_update(context: UpdateContext, client: anthropic.Anthropic, model: str) -> str:
    """Call Claude API to generate updated documentation."""
    prompt = build_prompt(context)

    try:
        message = client.messages.create(
            model=model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.BadRequestError as e:
        if "credit balance" in str(e):
            print(f"\n{RED}Error: Insufficient API credits.{RESET}", file=sys.stderr)
            print(
                "Your Anthropic API key needs credits. Claude Pro subscription does not",
                file=sys.stderr,
            )
            print(
                "include API credits. Visit https://console.anthropic.com to add credits.",
                file=sys.stderr,
            )
            sys.exit(1)
        raise

    # Extract text from response
    response_text = ""
    for block in message.content:
        if isinstance(block, TextBlock):
            response_text += block.text

    return response_text.strip()


def show_diff(original: str, updated: str, doc_path: str) -> None:
    """Display colored diff of changes."""
    original_lines = original.splitlines(keepends=True)
    updated_lines = updated.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        updated_lines,
        fromfile=f"a/{doc_path}",
        tofile=f"b/{doc_path}",
        lineterm="",
    )

    print(f"\n{BOLD}Diff for {doc_path}:{RESET}\n")

    for line in diff:
        if line.startswith("+++") or line.startswith("---"):
            print(f"{BOLD}{line}{RESET}", end="")
        elif line.startswith("@@"):
            print(f"{CYAN}{line}{RESET}", end="")
        elif line.startswith("+"):
            print(f"{GREEN}{line}{RESET}", end="")
        elif line.startswith("-"):
            print(f"{RED}{line}{RESET}", end="")
        else:
            print(line, end="")

    print()


def apply_update(doc_path: Path, content: str) -> None:
    """Write updated content to doc file."""
    doc_path.write_text(content, encoding="utf-8")
    print(f"{GREEN}Updated: {doc_path}{RESET}")


def touch_mtime(doc_path: Path) -> None:
    """Update modification time to now."""
    doc_path.touch()


def update_single_doc(
    doc_path: Path,
    project_root: Path,
    client: anthropic.Anthropic,
    model: str,
    dry_run: bool = False,
    auto_approve: bool = False,
) -> bool:
    """
    Update a single stale doc.

    Returns True if updated, False if skipped.
    """
    print(f"\n{BOLD}Processing: {doc_path.relative_to(project_root)}{RESET}")

    context = gather_context(doc_path, project_root)

    if context is None:
        print(f"{YELLOW}Skipping: Doc is not stale{RESET}")
        return False

    print(f"  Stale refs: {len(context.stale_refs)}")
    for ref in context.stale_refs:
        print(f"    - {ref}")

    print(f"\n{CYAN}Generating update with Claude...{RESET}")
    updated_content = generate_update(context, client, model)

    # Check if there are actual changes
    if updated_content.strip() == context.doc_content.strip():
        print(f"{YELLOW}No changes needed{RESET}")
        return False

    show_diff(context.doc_content, updated_content, str(doc_path.relative_to(project_root)))

    if dry_run:
        print(f"{YELLOW}Dry run - no changes written{RESET}")
        return False

    if auto_approve:
        apply_update(doc_path, updated_content)
        return True

    # Interactive approval
    while True:
        response = input(f"\n{BOLD}Apply this update? [y/n/q] {RESET}").strip().lower()
        if response == "y":
            apply_update(doc_path, updated_content)
            return True
        elif response == "n":
            print(f"{YELLOW}Skipped{RESET}")
            return False
        elif response == "q":
            print("Quitting")
            sys.exit(0)
        else:
            print("Please enter y (yes), n (no), or q (quit)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LLM-assisted documentation updater",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Update a specific doc (interactive)
    poetry run python scripts/docs_update.py --doc docs/patterns/metadata_manager_mixin.md

    # Update all stale docs (interactive, one at a time)
    poetry run python scripts/docs_update.py --all

    # Preview what would change (no writes)
    poetry run python scripts/docs_update.py --all --dry-run

    # Auto-approve all updates (for CI/batch)
    poetry run python scripts/docs_update.py --all --yes
""",
    )

    parser.add_argument(
        "--doc",
        type=str,
        help="Path to a specific documentation file to update",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Update all stale documentation files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Auto-approve all updates without prompting",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="claude-sonnet-4-20250514",
        help="Claude model to use (default: claude-sonnet-4-20250514)",
    )

    args = parser.parse_args()

    if not args.doc and not args.all:
        parser.error("Either --doc or --all is required")

    # Check for API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(f"{RED}Error: ANTHROPIC_API_KEY environment variable not set{RESET}", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    docs_dir = project_root / "docs"
    if not docs_dir.exists():
        print(f"{RED}Error: docs directory not found at {docs_dir}{RESET}", file=sys.stderr)
        sys.exit(1)

    updated_count = 0
    skipped_count = 0

    if args.doc:
        # Single doc mode
        doc_path = Path(args.doc)
        if not doc_path.is_absolute():
            doc_path = project_root / doc_path

        if not doc_path.exists():
            print(f"{RED}Error: File not found: {doc_path}{RESET}", file=sys.stderr)
            sys.exit(1)

        if update_single_doc(doc_path, project_root, client, args.model, args.dry_run, args.yes):
            updated_count += 1
        else:
            skipped_count += 1

    else:
        # All stale docs mode
        print(f"{BOLD}Scanning for stale documentation...{RESET}")
        results = scan_docs(docs_dir, project_root)
        stale_results = [r for r in results if r.is_stale]

        if not stale_results:
            print(f"{GREEN}No stale documentation found!{RESET}")
            return

        print(f"Found {len(stale_results)} stale document(s)\n")

        for result in stale_results:
            doc_path = project_root / result.doc_path
            if update_single_doc(
                doc_path, project_root, client, args.model, args.dry_run, args.yes
            ):
                updated_count += 1
            else:
                skipped_count += 1

    # Summary
    print(f"\n{BOLD}Summary:{RESET}")
    print(f"  Updated: {updated_count}")
    print(f"  Skipped: {skipped_count}")


if __name__ == "__main__":
    main()
