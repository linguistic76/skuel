#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["pypandoc-binary"]
# ///
"""Convert a reference book (EPUB) into clean, durable Markdown for the SKUEL canon.

This is **author-side tooling**, not app code. It prepares the raw books in
``0vault/Resources/`` for the "canon" journaling-companion surface (see
``docs/roadmap/canon-journaling-companion.md``). Running it on a book is the
first step in shelving that book: clean text now, ``:ReferenceChunk`` ingestion
later (Phase 2).

Pipeline (deterministic — NO LLM rewriting, which would corrode the raw text):

    EPUB --(pandoc, native reader)--> AST
         --(clean_reference lua filter)--> unwrap <div>/<span>, drop images,
                                           drop stray raw HTML, unwrap <figure>
         --(gfm-raw_html writer)--> Markdown with raw HTML disabled on OUTPUT,
                                    so leftover styling (e.g. <span class="smallcaps">)
                                    degrades to plain text instead of leaking tags

Why this recipe (verified empirically on *Hyper Media Systems*, 2026-07-08):

  * The lua filter runs on pandoc's AST, so structural wrappers are removed
    *before* the writer runs — which lets syntax-highlighted code blocks parse
    as proper fenced code (```) instead of ``<span class="im">`` HTML soup.
  * Disabling ``raw_html`` on the *output* format (``gfm-raw_html``) means any
    styling the writer still cannot represent is dropped to text, not emitted
    as literal tags.
  * ``--wrap=none`` keeps each paragraph on one line — friendlier for the prose
    chunking that Phase 2 will do.

HTML *content* is preserved: this recipe is safe for technical books that teach
markup (HMS discusses "<div> soup" and shows HTML examples). Those live inside
code fences / inline code and are never stripped — only structural epub cruft is.

Usage::

    uv run scripts/clean_reference_book.py "/home/mike/0bsidian/0vault/Resources/0 Hyper Media Systems.epub"

By default the cleaned ``.md`` is written next to the source with the same stem
(``0 Hyper Media Systems.md``). Pass ``--output`` to override.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# pypandoc is a script-only PEP 723 dependency (see header), not an app dependency,
# so it is intentionally outside the project's type universe.
import pypandoc  # type: ignore[import-not-found]

# Pandoc AST filter. Embedded here so the whole cleaner is one committable file;
# written to a temp file at run time and passed via --lua-filter.
CLEAN_REFERENCE_LUA = """\
-- Deterministic reference-text cleaner (pandoc AST filter).
-- Strips epub structural cruft so a book converts to clean prose + code markdown:
--   * unwrap <div>/<span> section wrappers (drop id/class page anchors)
--   * drop images (deferred for text-companion use)
--   * drop stray raw HTML (cover <svg>, etc.)
--   * unwrap <figure> (keep caption text; images already removed)
-- No semantic rewriting -- structure only. HTML shown *as content* (inside code
-- blocks / inline code) is untouched: those are Str/Code nodes, not Div/Span/Raw.

function Div(el)   return el.content end
function Span(el)  return el.content end
function Image(_)  return {} end
function Figure(el) return el.content end

function RawBlock(el)
  if el.format == 'html' then return {} end
end
function RawInline(el)
  if el.format == 'html' then return {} end
end
"""

# Structural artifacts that must be zero in clean prose (informational audit only).
_PROSE_ARTIFACT_TAGS = ("<div", "<span", "<img", "<image", "<svg", "<figure")


def convert(source: Path, input_format: str) -> str:
    """Run pandoc with the clean_reference filter and return Markdown text."""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".lua", encoding="utf-8", delete=False
    ) as lua_file:
        lua_file.write(CLEAN_REFERENCE_LUA)
        lua_path = lua_file.name
    try:
        return pypandoc.convert_file(
            str(source),
            to="gfm-raw_html",  # disable raw_html on OUTPUT: leftover styling -> text
            format=input_format,
            extra_args=[f"--lua-filter={lua_path}", "--wrap=none"],
        )
    finally:
        Path(lua_path).unlink(missing_ok=True)


def audit(markdown: str) -> dict[str, int]:
    """Fence-aware audit: count code fences and any structural tags leaking into prose.

    Tags inside code fences are legitimate content (a book may teach HTML), so
    they are excluded. Only prose-side structural tags count as leaks.
    """
    fences = 0
    prose_leaks = 0
    in_fence = False
    for line in markdown.split("\n"):
        if line.strip().startswith("```"):
            fences += 1
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # Ignore inline code spans (`<div>` in prose is book content, not cruft).
        outside_code = "`".join(line.split("`")[::2])
        if any(tag in outside_code for tag in _PROSE_ARTIFACT_TAGS):
            prose_leaks += 1
    return {"words": len(markdown.split()), "fences": fences, "prose_leaks": prose_leaks}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a reference book (EPUB) to clean Markdown for the SKUEL canon.",
    )
    parser.add_argument("source", type=Path, help="Path to the source book (EPUB).")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output .md path (default: source path with a .md suffix).",
    )
    parser.add_argument(
        "--format",
        default="epub",
        help="Pandoc input format (default: epub).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    args = parser.parse_args()

    source: Path = args.source
    if not source.exists():
        print(f"error: source not found: {source}", file=sys.stderr)
        return 1

    output: Path = args.output or source.with_suffix(".md")
    if output.exists() and not args.force:
        print(
            f"error: {output} already exists (pass --force to overwrite)",
            file=sys.stderr,
        )
        return 1

    print(f"Converting {source.name} ...")
    markdown = convert(source, args.format)

    # Minimal provenance frontmatter. No `type:` field -> stays non-ingestible
    # (the Resources/ wall excludes this dir from curriculum ingestion anyway).
    # `resource_uid:` maps this book to its pre-existing Resource for the canon
    # ingest door (scripts/ingest_canon_book.py) — author fills the value (an
    # explicit UID, never slug-matched from the filename).
    frontmatter = (
        f'---\nsource_epub: "{source.name}"\n'
        f"generated_by: scripts/clean_reference_book.py\n"
        f'resource_uid: ""\n---\n\n'
    )
    output.write_text(frontmatter + markdown, encoding="utf-8")

    stats = audit(markdown)
    print(f"Wrote {output}")
    print(
        f"  words={stats['words']:,}  code_fences={stats['fences']}  "
        f"prose_tag_leaks={stats['prose_leaks']}"
    )
    if stats["prose_leaks"]:
        print(
            "  note: a few structural tags remain in prose; inspect if > single digits.",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
