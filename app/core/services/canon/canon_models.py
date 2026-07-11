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
    """One retrieved canon passage, tagged with the book and its in-book location.

    ``text`` is the exact chunk body — quotable verbatim (ADR-076). ``book_title``
    drives attribution; ``heading`` / ``section_path`` / ``sequence`` give the
    structural anchor a citation points to (chapter/section trail + position).
    An EPUB is reflowable, so there is no page number — ``locator`` is the honest
    best-practice anchor.
    """

    text: str
    book_title: str
    resource_uid: str
    similarity_score: float
    heading: str | None = None
    section_path: str | None = None
    sequence: int | None = None

    @property
    def locator(self) -> str:
        """Human location trail: ``section_path`` + immediate ``heading``.

        E.g. ``"Hypermedia Concepts > Hypermedia: A Reintroduction > A Brief
        History of Hypermedia"``. Empty when the passage has no heading context
        (front matter / unstructured) — the caller then cites the book + position
        only. ``section_path`` already excludes the immediate heading, so the two
        never duplicate.
        """
        return " > ".join(p for p in (self.section_path, self.heading) if p)

    def citation_line(self) -> str:
        """One-line source label for citing this passage: book + location trail.

        E.g. ``"Hypermedia Systems — Hypermedia Concepts > Hypermedia: A
        Reintroduction"``. Falls back to the book title alone when the passage
        has no heading context.
        """
        bits = [self.book_title] if self.book_title else []
        loc = self.locator
        if loc:
            bits.append(loc)
        return " — ".join(bits) if bits else "(untitled source)"


@dataclass(frozen=True)
class CanonSource:
    """One shelved book a response drew on, with the in-book locations it used.

    The UI-facing shape of an attribution: a book + the distinct location trails
    its quoted passages came from + the ``resource_uid`` that builds the link to
    its Resource page. Kept structured (not markdown) so a plain-text surface can
    render a real anchor.
    """

    book_title: str
    resource_uid: str
    locators: tuple[str, ...]


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
        """Distinct book titles that actually infused, in first-seen (best) order.

        Order-preserving de-dupe: several passages from the same book collapse to
        one attribution, ranked by where that book first appears in the results.

        A passage with blank text is skipped here just as ``to_prompt_block``
        skips it: only books that genuinely shaped the reasoning are named, so
        the "Drawing on" footer can never attribute a book that contributed no
        infused text ("point to the raw" honesty — the attribution and the
        infusion share one truth).
        """
        seen: dict[str, None] = {}
        for passage in self.passages:
            if passage.book_title and passage.text.strip() and passage.book_title not in seen:
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

    def to_discussion_block(self) -> str:
        """Render passages for OPEN discussion — the model may name AND quote them.

        The quote-on-demand counterpart to ``to_prompt_block`` (ADR-076). Unlike
        silent infusion, this tells the model it has a curated shelf and MAY
        engage the passages openly: name the book, discuss its ideas, and quote
        it **verbatim** when the user wants to see or verify the text — each
        passage labelled with its book + in-book location so a citation is exact.

        Carries the non-negotiable faithfulness contract: quote ONLY the text
        below, cite ONLY the location shown, never invent a quote or an anchor,
        and say plainly when the shelf has nothing on point. ``""`` if no passage.
        """
        if not self.passages:
            return ""
        entries = []
        for i, passage in enumerate(self.passages, start=1):
            if not passage.text.strip():
                continue
            entries.append(f"### Passage {i} — {passage.citation_line()}\n\n{passage.text.strip()}")
        if not entries:
            return ""
        body = "\n\n".join(entries)
        return (
            "## The Canon Shelf\n\n"
            "You have a curated shelf of real books. The passages below were retrieved "
            "from it for this conversation. You MAY discuss them openly — name the book, "
            "engage with its ideas, and quote it **verbatim** when the user wants to see "
            "or verify the words.\n\n"
            "Faithfulness (non-negotiable):\n"
            "- Quote ONLY the text in the passages below — never reconstruct a quote from memory.\n"
            "- When you quote, attribute it to its book and cite the location shown for that passage.\n"
            "- Never invent a quote, chapter, section, or page. If the shelf has nothing on the "
            "user's question, say so plainly rather than fabricate.\n"
            "- These are reflowable e-books: cite by chapter/section (shown), never by page number.\n\n"
            f"{body}"
        )

    def to_teaching_block(self) -> str:
        """Render passages to GROUND Socratic guidance — cite, quote sparingly, keep the method.

        The teaching-time counterpart to ``to_discussion_block`` (Askesis-canon
        integration, ADR-077): passages from the readings a learning step cites,
        framed to sharpen the guide's questions rather than hand over answers.
        Carries the ADR-076 faithfulness contract verbatim — quote only the
        text below, cite only the location shown, never fabricate. ``""`` if
        no passage.
        """
        if not self.passages:
            return ""
        entries = [
            f"### {p.citation_line()}\n\n{p.text.strip()}" for p in self.passages if p.text.strip()
        ]
        if not entries:
            return ""
        body = "\n\n".join(entries)
        return (
            "## Readings for This Step\n\n"
            "These passages are from the readings this learning step cites. Ground your Socratic "
            "guidance in them — let a passage sharpen the question you ask, the analogy you offer, "
            "the distinction you draw. When you lean on a specific idea, name its book and cite the "
            "location shown. Quote **verbatim and sparingly** — only the text below, never from "
            "memory — when the exact words matter.\n\n"
            "Do not surrender the method: a passage that states the answer is a reason to ask a "
            "better question, not to recite it. If the readings hold nothing on the learner's point, "
            "guide from the curriculum and say so — never invent a passage, chapter, or section.\n\n"
            "These are reflowable e-books: cite by chapter/section (shown), never by page number.\n\n"
            f"{body}"
        )

    def sources(self) -> tuple[CanonSource, ...]:
        """Structured per-book sources for the discussion path — for UI rendering.

        One entry per book actually drawn on, with the distinct in-book locations
        its passages came from. The UI turns each into a real, clickable link to
        the book's Resource page (the "point to the raw" destination) — the
        discussion path quotes, so the reader must be able to verify. Empty when
        nothing was drawn. Structured (not markdown) so the plain-text journal
        bubble can render an actual anchor rather than literal `[text](url)`.
        """
        if not self.has_passages:
            return ()
        by_book: dict[str, list[str]] = {}
        titles: dict[str, str] = {}
        for passage in self.passages:
            if not passage.text.strip() or not passage.book_title:
                continue
            titles[passage.resource_uid] = passage.book_title
            locators = by_book.setdefault(passage.resource_uid, [])
            loc = passage.locator
            if loc and loc not in locators:
                locators.append(loc)
        return tuple(
            CanonSource(
                book_title=titles[uid],
                resource_uid=uid,
                locators=tuple(locators),
            )
            for uid, locators in by_book.items()
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
