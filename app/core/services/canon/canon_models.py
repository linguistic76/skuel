"""Canon retrieval value objects — the passages a journal stage draws on.

Frozen, domain-agnostic. ``CanonRetrievalService`` builds a ``CanonContext`` from
the reference shelf; a caller (today: ``JournalService``) turns it into two
plain-text pieces — a system-prompt block that voice-infuses the LLM's reasoning
and a light attribution footer appended to the visible output.

Nothing here is persisted (ADR-073): a ``CanonContext`` is ephemeral prompt
context that lives for one stage call and is dropped.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanonPassage:
    """One retrieved canon passage, tagged with the book it came from.

    ``text`` is the chunk body fed to the model as reasoning material;
    ``book_title`` drives the "Drawing on" attribution.
    """

    text: str
    book_title: str
    resource_uid: str
    similarity_score: float


@dataclass(frozen=True)
class CanonContext:
    """The canon passages a single journal stage may draw on.

    Domain-agnostic: it knows only "here are ranked passages and the books they
    came from". The caller decides placement (system-prompt context + footer).
    """

    passages: tuple[CanonPassage, ...]

    @classmethod
    def empty(cls) -> CanonContext:
        """The no-canon context — dial off, CORE tier, or no resonant passage.

        Callers fail-soft to this so a journal stage always completes: no
        system-prompt block, no footer.
        """
        return cls(passages=())

    @property
    def has_passages(self) -> bool:
        """Whether any passage was drawn — gates both the prompt block and footer."""
        return bool(self.passages)

    def books(self) -> list[str]:
        """Distinct book titles, in first-seen (best-scoring) order.

        Order-preserving de-dupe: several passages from the same book collapse to
        one attribution, ranked by where that book first appears in the results.
        """
        seen: dict[str, None] = {}
        for passage in self.passages:
            if passage.book_title and passage.book_title not in seen:
                seen[passage.book_title] = None
        return list(seen.keys())

    def to_prompt_block(self) -> str:
        """Render the passages as a system-prompt section, or ``""`` if none.

        Framed as reasoning material, not quotable text: the model is told to let
        these ideas inform its voice and thinking, never to quote or cite them
        inline (the visible attribution is the footer's job). Passages are joined
        plainly so no single one dominates.
        """
        if not self.passages:
            return ""
        body = "\n\n".join(
            passage.text.strip() for passage in self.passages if passage.text.strip()
        )
        if not body:
            return ""
        return (
            "## Wisdom to Draw On\n\n"
            "The following passages are drawn from a curated shelf of books. Let their "
            "ideas, framing, and voice inform your reasoning and tone — but do NOT quote "
            "them, name them, or cite them inline. They are background you have absorbed, "
            "not sources to attribute.\n\n"
            f"{body}"
        )

    def attribution_footer(self) -> str:
        """Render the light "Drawing on" footer, or ``""`` if no passages.

        Mirrors the shape of ``CitationBundle.format_for_askesis`` but far
        lighter: a single italic line naming the books the response leaned on,
        set off by a rule.
        """
        titles = self.books()
        if not titles:
            return ""
        # Italic label + italic titles kept as *separate* emphasis spans — a
        # single wrapping span (``*Drawing on: *HMS**``) collides asterisks and
        # renders inconsistently across markdown engines.
        rendered = ", ".join(f"*{title}*" for title in titles)
        return f"\n\n---\n*Drawing on:* {rendered}"
