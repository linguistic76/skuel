---
title: "Reading-Plan Capability Tray — a step's \"What this step adds\" waits on what starting one means"
updated: 2026-11-27
status: "staged — Mike's ruling 2026-11-27: register, no code change to the tray"
registered: 2026-11-27
ruled: 2026-11-27
trigger: "A ruling on what starting a step's capability does (what it writes, and for whom); or a step authored with a capability for the tray to carry"
check: "grep -n '\"capabilities\"' core/orchestrator/explore_orchestrator.py — a producer that sends anything but [] is a live tray; grep -rn 'capabilities/' adapters/inbound — a route there is the door the button posts to"
---

# Reading-Plan Capability Tray — a step's "What this step adds" waits on what starting one means

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

**What exists.** The reading plan's active-step card (`ui/explore/reading_plan.py`, `_ps_capabilities`)
renders a tray headed *What this step adds*: one button per capability the step carries, styled by its
`kind` (`_CAP_STYLES`: `practice`, `apply`, and a muted fallback for any other kind), with a `locked`
state. An unlocked button posts to `/explore/path-steps/{ps_uid}/capabilities/{kind}/start`
(`_ps_capability_button`, `hx-swap="none"`).

**Why nothing renders.** The producer, `ExploreOrchestrator.get_reading_plan`
(`core/orchestrator/explore_orchestrator.py`), always sends `"capabilities": []`, so the tray
collapses to an empty `Div` on every step. No route answers the button's URL: nothing is registered
under `/explore/path-steps/…`. The button would answer 404 if it ever rendered. No instrument reports
this. `tests/unit/ui/test_hx_targets_registered.py` reads `hx_*` keywords and literal
`**{"hx-…": …}` splats. The button's target is a key assigned into a dict that is splatted later
(`htmx_attrs["hx-post"] = f"…"`), which is neither shape, so the census does not even count it as
opaque. And because the producer's list is always empty, no page ever shows the button.

**The open question: what starting a capability does.** The tray's copy says the tray "belongs to the
step" and that another step "might add an assessment, a journal, or nothing at all". So a capability
is per-step authored content. But nothing in the curriculum names one: no PathStep field, no edge,
and no vault frontmatter key carries a capability or its `kind`. The closest live mechanisms each
answer part of the question, and none answers all of it:

- **Engagement** (`PsEngagementService`, the step's Activity templates spawning the learner's own
  instances) is what *practice* and *apply* do today. It is started from the step page, behind the
  prerequisite gate, and not per kind.
- **Exercises** (`HAS_EXERCISE`) are the step's assessment, reached from the PathStep page's learning
  loop, not from the reading plan.
- **Embedded forms** (`EMBEDS_FORM`) are staged on their own ([Embedded Forms Fragment](embedded-forms-fragment-staged.md)).

The ruling needed is what a capability is (an authored list on the step, or a view the producer derives
from the edges above), what the *start* write is for each kind, and whether it passes the
prerequisite gate the way every other start door does (`PsPrerequisiteGate`).

**What completes the entry:** a producer that fills `capabilities` from that answer, plus a
registered route the button posts to (or a button that links to an existing door instead). Each
start write goes through the gate. **What retires it the other way:** a ruling that the step page's
engagement and learning-loop doors are the only ways in. Then `_ps_capabilities`,
`_ps_capability_button`, `_CAP_STYLES` and the producer's `"capabilities"` key go together under
One Path Forward.
