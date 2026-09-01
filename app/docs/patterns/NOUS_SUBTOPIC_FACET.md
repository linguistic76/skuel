---
updated: 2026-08-27
---

# `nous_subtopic` Facet — Mechanism

The 2nd taxonomy level beneath `nous`: a graph-derived search facet + Askesis retrieval
scope on the curriculum corpus.

> **Content boundary:** this file documents the *mechanism* only. The *ontology* —
> which sub-topic slugs exist and what they mean — is proprietary SKUEL content and is
> **not** kept in this repo. It is authored in the private content vault as
> `nous_subtopic:` frontmatter and embodied in the graph. Do not paste the vocabulary
> here. See the content boundary guard: `scripts/audit_content_boundary.py`.

## How it works

- **Field:** `nous_subtopic: tuple[str, ...]` on `Ku` (`core/models/ku/ku.py`) and
  `PathStep` (`core/models/pathways/path_step.py`) — multi-valued, kebab-case,
  empty = deliberately unassigned. Authored in vault YAML alongside the `nous:`
  block; the two lists are fully **independent** — any lengths, any combination.
  There is deliberately NO alignment/equal-length authoring contract (ruled
  2026-07-16: no false restrictions — the design goes where whatever there is
  to share leads).
- **Pairing is co-occurrence.** A (topic, sub-topic) pair exists once ≥1 entity
  carries both, so the dependent dropdowns follow wherever the content actually
  connects them — every offered pair has at least one matching entity, and a
  sub-topic can surface under multiple topics when shared content links them.
- **Vocabulary is graph-derived, never hardcoded.** A sub-topic exists (and renders as
  a faucet option) only once ≥1 entity carries it (with a parent `nous`); deleting the
  last carrier removes it.
- **Cross-domain merge in the service layer.** Both `:Ku` and `:PathStep` author
  `nous_subtopic` independently, so a PathStep can contribute a pair no Ku carries. Each
  domain backend yields only its OWN label's pairs (`KuBackend`/`PsBackend.nous_subtopic_pairs`,
  scoped `:Ku` / `:PathStep`); `SearchRouter._nous_subtopic_pairs` merges them, and
  `nous_subtopic_map` + `list_nous_subtopics` both derive from that one merge.
  Aggregation lives in the service (SearchRouter is THE cross-domain search service),
  never in a single-domain backend. The flat list and the map share this one source, so
  they can't disagree — the flat list stays a superset of every map built at the SAME
  scope, and the column renders whenever that map has an entry.
- **The merge is SCOPED to the calling surface's result set** (`scope` on
  `_nous_subtopic_pairs`, forwarded by both wrappers; default `CURRICULUM_FACET_DOMAINS`
  = the merged `:Ku` + `:PathStep` vocabulary). A surface that does not RETURN a domain
  must not offer that domain's pairs — the option could never match. `/explore/library`
  and the Askesis composer keep the merged default — the library's catalog carries both, and
  Askesis is not a search surface at all (it reaches everything about the user, bounded by
  scopes the USER opens and closes; never narrow one of its vocabularies to match what some
  page lists — ruled 2026-08-26).
  `/search` passes `SEARCH_PAGE_FACET_DOMAINS` — derived as the intersection of the
  merged pair with `SEARCH_PAGE_ENTITY_TYPES`, so the facet scope cannot drift from the
  result scope; today that is `:Ku` alone. ⚠ A surface must pass the SAME scope to both
  wrappers: the flat list gates whether the column exists, the map supplies its options,
  and a mismatch renders a column with nothing to offer (gate wider) or hides one whose
  map has entries (gate narrower). See
  [`docs/roadmap/done/search-facet-redesign.md`](../roadmap/done/search-facet-redesign.md).
- **Fail-soft:** with no authored data the vocabulary is empty, so the search `<select>`
  (`ui/search/components.py::_render_nous_subtopic_select`) and the Askesis scope
  selector (`ui/askesis/chat.py`) render nothing rather than an empty control. A failing
  domain contributes nothing rather than erroring the whole vocabulary.
- **Search filter:** `SearchRequest.nous_subtopic` → property filter (array membership)
  in `core/models/search_request.py`. The filter itself stays independent array
  membership; the gated dropdown is what keeps the offered combinations honest.
- **Dependent dropdown (/search):** sub-topics go deeper into ONE topic, so the control
  is gated — it starts disabled ("Choose a Nous first"; the flat vocabulary acts only
  as the render gate), and picking a NOUS topic narrows the options to those authored
  UNDER it, via `SearchRouter.nous_subtopic_map`. Wiring is pure HTMX: the sub-topic
  column (`_render_nous_subtopic_select`) listens for `change from:[name='nous']` and
  re-fetches `GET /search/subtopics?nous=…`, swapping its innerHTML with the scoped
  `render_nous_subtopic_inner` fragment — no Alpine window-global seeding. The NOUS
  `<select>` drops `nous_subtopic` from its results include so a topic switch re-scopes
  cleanly instead of carrying a now-orphaned sub-topic. "All Nous" resets the control
  to the disabled gate (the flat cross-topic list is never offered); a topic with no
  sub-topics yields a disabled "All Sub-topics".
- **Dependent selector (Askesis):** same dependency, Alpine-native — the topic can also
  change via the scope chip's × (a plain state write with no DOM change event), so an
  HTMX-on-change swap would miss it. `render_askesis_shell` inlines the map into root
  x-data (`nousSubtopicMap`); the sub-topic `<select>` renders its options client-side
  (`x-for` over `nousSubtopicMap[selectedNous]`, `:selected` re-asserts the seeded value
  after the dynamic options render), is `:disabled` until a topic is picked, and a root
  `x-effect` clears a sub-topic the moment it no longer co-occurs with the selected topic.
  The `/askesis?nous=…&nous_subtopic=…` handoff params are validated DEPENDENTLY
  (sub-topic must co-occur with the seeded nous on ≥1 entity) before seeding.

## Authoring & changing the ontology

Edit `nous_subtopic:` frontmatter in the content vault, then re-sync
(`./dev vault-sync --vault content`). The faucets follow the graph. The taxonomy
reference lives with the content (vault), not here.

**See:** `docs/architecture/SEARCH_ARCHITECTURE.md`,
`docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`
