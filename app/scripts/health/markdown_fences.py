"""
Fenced-code-block boundaries for the health scanners.

One CommonMark-backed walker, two contract shapes. ``scripts/health/`` used to hold
*two* fence parsers: this one (then private to ``dead_doc_links``) and a hand-written
scanner inside ``stale_names.extract_code_segments``. That is the "hand-written
approximation of a mechanism that already exists" defect class, and both instances
grew the same bug independently — a closing test of "the line starts with ``` or ~~~"
lets an inner ```` ```bash ```` sample close an outer ```` ````markdown ```` wrapper,
silently truncating every wrapped example.

Two shapes are genuinely needed, so the split here is by *projection*, not by parser:

  ``iter_code_fence_blocks``  whole blocks — what a scanner reporting per-block wants
  ``iter_code_fence_lines``   flat per-line coordinates + language tag

The second is derived from the first. Adding a third consumer means adding a third
projection, never a third walker.

Why a parser and not a longer regex: the scanner this replaced accrued **five**
container-handling bugs in one review (PR #872). Blockquoted fences never opened; an
unclosed quoted fence then leaked into following prose; a fence opened in a nested
quote (``> > ```) did not close when the inner quote ended; a list-item fence without a
closer swallowed the rest of the document; and a four-space-indented delimiter — an
*indented code block* under CommonMark, not a fence — was opened as a real fence. Each
one falsely reported ordinary prose as ``[code]``.

A tree-wide differential against CommonMark found ZERO disagreements with that
scanner, which read as "the scanner is equivalent" but only ever meant "the corpus
contains none of these shapes." Corpus-relative agreement is not correctness. Every
construction above is absent from ``docs/`` today and would have started silently
misreporting the moment someone wrote one.

Pinned by ``tests/unit/scripts/test_markdown_fences.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from markdown_it import MarkdownIt

# Reused across calls: `parse()` builds its own state per invocation and holds none
# between them, so one instance serves the whole 400+ document sweep.
_PARSER = MarkdownIt("commonmark")


@dataclass(frozen=True)
class FenceBlock:
    """
    One fenced code block, with 1-based line coordinates.

    ``span`` covers the WHOLE fence including its delimiter lines; ``lines`` covers only
    the content between them. Callers that also scan prose need ``span`` to know which
    lines a fence already claimed — a delimiter line is neither content nor prose, and
    scanning it as prose is how an info string like ``` ```core/dead.py ``` gets read as
    a citation.

    ``lines`` is empty for an empty fence. That block still occupies its ``span``.
    """

    lang: str
    span: tuple[int, int]
    lines: tuple[tuple[int, str], ...]


def strip_quote_prefix(line: str, depth: int | None = None) -> str:
    """
    Remove Markdown blockquote container markers from the head of a line.

    ``depth`` bounds how many are removed; pass the parser's quote depth so that a
    literal ``>`` in *fence content* survives. Stripping greedily conflates the two: in
    a quoted fence holding a no-space shell redirect, ``> >core/generated.txt`` has one
    container marker and one content character, and eating both hands the guard a bare
    path that gets reported — while the identical unquoted redirect is correctly rejected
    by the ``>`` template marker. Quoting a fence must not change what it reports
    (Codex, PR #872).

    ``None`` means strip every marker, which is only right when the caller has no depth
    to work from.
    """
    remaining = depth
    stripped = line
    while remaining is None or remaining > 0:
        candidate = stripped.lstrip()
        if not candidate.startswith(">"):
            break
        stripped = candidate[1:].removeprefix(" ")
        if remaining is not None:
            remaining -= 1
    return stripped


def _closes_fence(line: str, opener: str, quote_depth: int) -> bool:
    """
    Is this line a valid CommonMark closing delimiter for a fence opened with ``opener``?

    Exact rather than heuristic, and measured against the parser's own ``token.markup``:
    a closer uses the same character, is at least as long as the opener, and carries
    nothing but whitespace afterwards.

    A "starts with ``` or ~~~" test admits four non-closers, and each one is a silent
    loss of scanned content:

      ``` inside ````        a SHORTER run — closes a wrapper early, dropping its body
      ~~~ inside ```         the OTHER delimiter character, likewise
      ```bash                a run followed by an info string — the inner opener above
      ```core/dead.py        a run followed by text at EOF — makes an unclosed fence
                             look closed, dropping its last line from the audit

    The third is what broke ``stale_names.extract_code_segments`` on every
    ```` ````markdown ```` wrapper in the tree; the fourth is the shape Codex found in
    PR #872.

    The quote prefix comes off first: a blockquoted fence closes on ``> ``` ``, whose
    ``lstrip()`` starts with ``>``, so testing the raw line calls a closed fence unclosed
    and emits its own closing delimiter as content.
    """
    candidate = strip_quote_prefix(line, quote_depth).lstrip()
    char = opener[0]
    run = len(candidate) - len(candidate.lstrip(char))
    return run >= len(opener) and not candidate[run:].strip()


def iter_code_fence_blocks(content: str) -> list[FenceBlock]:
    """
    Return every fenced code block in ``content``, ordered by position.

    THE walker. Fence boundaries come from a real CommonMark parser, so nesting,
    blockquote containers, list containers, indented-code lookalikes and unclosed
    fences are the parser's problem rather than a regex's — see the module docstring
    for the five container bugs that motivated this.
    """
    lines = content.splitlines()
    blocks: list[FenceBlock] = []
    quote_depth = 0

    # Fences are block tokens, so they sit in the flat stream; only `inline` tokens carry
    # children. Blockquote depth comes from the parser rather than being sniffed off the
    # line, which is what lets the strip below stay narrow.
    for token in _PARSER.parse(content):
        if token.type == "blockquote_open":
            quote_depth += 1
        elif token.type == "blockquote_close":
            quote_depth -= 1
        elif token.type == "fence" and token.map:
            start, end = token.map  # 0-based, [start, end)
            # An unclosed fence has no closing delimiter line to skip, so whether the
            # last line is a real closer decides if it is content. Assuming it always
            # is once made this module's own CommonMark differential report a false
            # disagreement — the harness was wrong, not the code under test.
            closed = end - 1 < len(lines) and _closes_fence(
                lines[end - 1], token.markup, quote_depth
            )
            info = token.info.strip()
            blocks.append(
                FenceBlock(
                    lang=info.split()[0].lower() if info else "",
                    span=(start + 1, end),
                    lines=tuple(
                        # Strip `> ` only inside a real blockquote, so a shell redirect
                        # at the start of an unquoted fence line keeps its `>`.
                        (
                            lineno,
                            strip_quote_prefix(lines[lineno - 1], quote_depth)
                            if quote_depth
                            else lines[lineno - 1],
                        )
                        for lineno in range(start + 2, (end - 1 if closed else end) + 1)
                    ),
                )
            )

    return sorted(blocks, key=lambda block: block.span)


def iter_code_fence_lines(content: str) -> list[tuple[int, str, str]]:
    """
    Return (line_no, language_tag, line) for every line INSIDE a fenced code block.

    The per-line projection of :func:`iter_code_fence_blocks`, for callers whose report
    is only actionable at a line. Delimiter lines are excluded; ``line_no`` is 1-based.
    """
    return sorted(
        (lineno, block.lang, text)
        for block in iter_code_fence_blocks(content)
        for lineno, text in block.lines
    )
