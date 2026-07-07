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
  `PathStep` (`core/models/pathways/path_step.py`) — mirrors `nous` exactly:
  multi-valued, kebab-case, empty = deliberately unassigned. Authored in vault YAML
  directly under the `nous:` block.
- **Vocabulary is graph-derived, never hardcoded.** A sub-topic exists (and renders as
  a faucet option) only once ≥1 entity carries it (with a parent `nous`); deleting the
  last carrier removes it. Backed by `KuBackend.nous_subtopic_pairs` (co-occurring
  `nous` + `nous_subtopic` across `:Ku` + `:PathStep`) via
  `KuService.list_nous_subtopics()` — the SAME source as the dependent map below, so the
  flat list and the map can never disagree.
- **Fail-soft:** with no authored data the vocabulary is empty, so the search `<select>`
  (`ui/search/components.py::_render_nous_subtopic_select`) and the Askesis scope
  selector (`ui/askesis/chat.py`) render nothing rather than an empty control.
- **Search filter:** `SearchRequest.nous_subtopic` → property filter (array membership)
  in `core/models/search_request.py`.
- **Dependent dropdown (/search):** picking a NOUS topic narrows the sub-topic options
  to those authored alongside it. The `nous → subtopics` map is graph-derived
  (`KuBackend.nous_subtopic_pairs` → `KuService.nous_subtopic_map`, distinct co-occurring
  pairs across `:Ku` + `:PathStep`). Wiring is pure HTMX: the sub-topic column
  (`_render_nous_subtopic_select`) listens for `change from:[name='nous']` and re-fetches
  `GET /search/subtopics?nous=…`, swapping its innerHTML with the scoped
  `render_nous_subtopic_inner` fragment — no Alpine window-global seeding. The NOUS
  `<select>` drops `nous_subtopic` from its results include so a topic switch re-scopes
  cleanly instead of carrying a now-orphaned sub-topic. Fail-soft: a topic with no
  sub-topics yields just "All Sub-topics".

## Authoring & changing the ontology

Edit `nous_subtopic:` frontmatter in the content vault, then re-sync
(`./dev vault-sync --vault content`). The faucets follow the graph. The taxonomy
reference lives with the content (vault), not here.

**See:** `docs/architecture/SEARCH_ARCHITECTURE.md`,
`docs/architecture/CURRICULUM_GROUPING_PATTERNS.md`
