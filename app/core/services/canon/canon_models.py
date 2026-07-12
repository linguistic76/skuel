"""Canon retrieval value objects — the passages a journal stage draws on.

Frozen, domain-agnostic. ``CanonRetrievalService`` builds a ``CanonContext`` from
the reference shelf (``retrieve``) or the user's own vault notes
(``retrieve_vault`` — canon P3); a caller (today: ``JournalService``) turns it
into two plain-text pieces — a system-prompt block that voice-infuses the LLM's
reasoning and a light attribution footer appended to the visible output.

``SourceKind`` discriminates the two corpora on ONE value-object family (ADR-077:
one contract, two substrates — never a parallel model family). A VAULT passage
reinterprets the book fields: ``book_title`` is the note title, ``resource_uid``
is the UserEntry uid, and ``vault_path`` replaces the in-book location trail.

Nothing here is persisted (ADR-073): a ``CanonContext`` is ephemeral prompt
context that lives for one stage call and is dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SourceKind(StrEnum):
    """Which corpus a passage/source came from — canon shelf or personal vault."""

    CANON = "canon"
    VAULT = "vault"


def _footer_line(titles: list[str]) -> str:
    """The shared "Drawing on" footer body for a list of source titles.

    Italic label + italic titles kept as *separate* emphasis spans — a single
    wrapping span (``*Drawing on: *HMS**``) collides asterisks and renders
    inconsistently across markdown engines. ``""`` for no titles.
    """
    if not titles:
        return ""
    rendered = ", ".join(f"*{title}*" for title in titles)
    return f"\n\n---\n*Drawing on:* {rendered}"


def merged_attribution_footer(*contexts: CanonContext) -> str:
    """THE light "Drawing on" footer — one line across any number of contexts.

    Mirrors the shape of ``CitationBundle.format_for_askesis`` but far lighter:
    a single italic line naming the sources the response leaned on, set off by
    a rule — never two rules when a stage draws on both corpora.
    Order-preserving de-dupe across the contexts' drawn titles; ``""`` when
    nothing infused anywhere.
    """
    seen: dict[str, None] = {}
    for context in contexts:
        for title in context.books():
            seen.setdefault(title, None)
    return _footer_line(list(seen.keys()))


@dataclass(frozen=True)
class CanonPassage:
    """One retrieved passage, tagged with its source and in-source location.

    ``text`` is the exact chunk body — quotable verbatim (ADR-076). ``book_title``
    drives attribution; ``heading`` / ``section_path`` / ``sequence`` give the
    structural anchor a citation points to (chapter/section trail + position).
    An EPUB is reflowable, so there is no page number — ``locator`` is the honest
    best-practice anchor.

    VAULT passages (canon P3) reinterpret the book fields: ``book_title`` is the
    note title, ``resource_uid`` is the owning UserEntry uid (it builds the
    ``/gradebook/{uid}`` citation link), and ``vault_path`` — the vault-relative
    display path — is the locator. ``weight`` is the ADR-077 contract letter for
    per-source weighting: uniform ``1.0`` today, nothing reads it yet.
    """

    text: str
    book_title: str
    resource_uid: str
    similarity_score: float
    heading: str | None = None
    section_path: str | None = None
    sequence: int | None = None
    source_kind: SourceKind = SourceKind.CANON
    vault_path: str | None = None
    weight: float = 1.0

    @property
    def locator(self) -> str:
        """Human location trail: in-book section trail, or the vault path.

        CANON: ``section_path`` + immediate ``heading``, e.g. ``"Hypermedia
        Concepts > Hypermedia: A Reintroduction > A Brief History of
        Hypermedia"``. Empty when the passage has no heading context (front
        matter / unstructured) — the caller then cites the book + position
        only. ``section_path`` already excludes the immediate heading, so the
        two never duplicate. VAULT: the vault-relative file path
        (``knowledge/foo.md``), empty when unavailable.
        """
        if self.source_kind is SourceKind.VAULT:
            return self.vault_path or ""
        return " > ".join(p for p in (self.section_path, self.heading) if p)

    def citation_line(self) -> str:
        """One-line source label for citing this passage: title + location trail.

        CANON e.g. ``"Hypermedia Systems — Hypermedia Concepts > Hypermedia: A
        Reintroduction"``; VAULT e.g. ``"My Stoicism Notes — knowledge/stoicism.md"``.
        Falls back to the title alone when the passage has no location context.
        """
        bits = [self.book_title] if self.book_title else []
        loc = self.locator
        if loc:
            bits.append(loc)
        return " — ".join(bits) if bits else "(untitled source)"


@dataclass(frozen=True)
class CanonSource:
    """One source a response drew on, with the in-source locations it used.

    The UI-facing shape of an attribution: a title + the distinct location
    trails its quoted passages came from + the ``resource_uid`` that builds the
    link — the book's Resource page for CANON, the note's ``/gradebook/{uid}``
    detail for VAULT (``source_kind`` tells the renderer which). Kept
    structured (not markdown) so a plain-text surface can render a real anchor.
    """

    book_title: str
    resource_uid: str
    locators: tuple[str, ...]
    source_kind: SourceKind = SourceKind.CANON


@dataclass(frozen=True)
class CanonContext:
    """The passages a single journal stage may draw on — canon shelf or vault.

    Domain-agnostic: it knows only "here are ranked passages and the sources
    they came from". The caller decides placement (system-prompt context +
    footer). ``source_kind`` selects the prompt framing: curated books are
    absorbed background voice; the user's own vault notes are their material,
    framed as such.
    """

    passages: tuple[CanonPassage, ...]
    source_kind: SourceKind = SourceKind.CANON

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
        plainly so no single one dominates. VAULT passages carry the same absorb
        contract with own-notes wording — they are the user's material, not a
        curated shelf.
        """
        if not self.passages:
            return ""
        body = "\n\n".join(
            passage.text.strip() for passage in self.passages if passage.text.strip()
        )
        if not body:
            return ""
        if self.source_kind is SourceKind.VAULT:
            return (
                "## The User's Own Notes to Draw On\n\n"
                "The following passages are drawn from the user's own vault notes — "
                "their material, in their words. Let what they have already written "
                "inform your reasoning and tone — but do NOT quote the passages, name "
                "the notes, or cite them inline. They are context you have absorbed, "
                "not sources to attribute.\n\n"
                f"{body}"
            )
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
        VAULT passages carry the identical contract with note-title/path anchors.
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
        if self.source_kind is SourceKind.VAULT:
            return (
                "## The User's Vault Notes\n\n"
                "The passages below were retrieved from the user's own vault notes for "
                "this conversation. You MAY discuss them openly — name the note, engage "
                "with what the user wrote, and quote it **verbatim** when they want to "
                "see or verify their own words.\n\n"
                "Faithfulness (non-negotiable):\n"
                "- Quote ONLY the text in the passages below — never reconstruct a quote from memory.\n"
                "- When you quote, attribute it to its note and cite the note title and path shown "
                "for that passage.\n"
                "- Never invent a quote, a note, or a path. If these notes hold nothing on the "
                "user's question, say so plainly rather than fabricate.\n\n"
                f"{body}"
            )
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

    def to_teaching_block(self, *, preserve_method: bool = True) -> str:
        """Render passages to GROUND Socratic guidance — cite, quote sparingly, keep the method.

        The teaching-time counterpart to ``to_discussion_block`` (Askesis-canon
        integration, ADR-077): passages from the readings a learning step cites,
        framed to sharpen the guide's questions rather than hand over answers.
        Carries the ADR-076 faithfulness contract verbatim — quote only the
        text below, cite only the location shown, never fabricate. ``""`` if
        no passage.

        ``preserve_method=False`` (Codex #613 P2) swaps the "ask a better
        question, not recite" paragraph for a direct-answer framing — used when
        the guidance mode PROMISES direct answers (DIRECT), so the readings
        ground the answer instead of contradicting the mode. The faithfulness
        contract is identical in both framings.
        """
        if not self.passages:
            return ""
        entries = [
            f"### {p.citation_line()}\n\n{p.text.strip()}" for p in self.passages if p.text.strip()
        ]
        if not entries:
            return ""
        body = "\n\n".join(entries)
        if preserve_method:
            grounding = (
                "Ground your Socratic guidance in them — let a passage sharpen the question you "
                "ask, the analogy you offer, the distinction you draw."
            )
            method_paragraph = (
                "Do not surrender the method: a passage that states the answer is a reason to "
                "ask a better question, not to recite it. If the readings hold nothing on the "
                "learner's point, guide from the curriculum and say so — never invent a passage, "
                "chapter, or section."
            )
        else:
            grounding = (
                "Ground your answer in them — let a passage sharpen the explanation you give, "
                "the analogy you offer, the distinction you draw."
            )
            method_paragraph = (
                "Answer directly, drawing on these readings when they cover the learner's "
                "point. If they hold nothing on it, answer from the curriculum and say so — "
                "never invent a passage, chapter, or section."
            )
        return (
            "## Readings for This Step\n\n"
            f"These passages are from the readings this learning step cites. {grounding} "
            "When you lean on a specific idea, name its book and cite the location shown. Quote "
            "**verbatim and sparingly** — only the text below, never from memory — when the "
            "exact words matter.\n\n"
            f"{method_paragraph}\n\n"
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
                source_kind=self.source_kind,
            )
            for uid, locators in by_book.items()
        )
