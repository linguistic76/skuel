# SKUEL Domain Events

Events are how services stay decoupled: a publisher states what happened, and subscribers
react without the publisher knowing they exist. Everything below is a rule you can check;
nothing here is a catalog, because a hand-maintained catalog drifts (see the note at the end).

## The four rules

1. **Name it `{domain}.{action}`** — lowercase, dot-separated, singular domain, past-tense
   action. `task.completed`, never `TaskCompleted` / `task_completed` / `task.complete`.
   Prefer the specific action (`task.priority_changed`) over `task.updated`, which means
   "several fields moved at once". The one sanctioned plural is a bulk event, where the
   plural *is* the meaning: `tasks.bulk_completed` and `habits.bulk_completed`.

2. **Declare `event_type` as a `ClassVar`, never a `@property`.** It is a fact about the
   class, and that is what lets `EVENT_REGISTRY` be derived by comprehension instead of
   hand-maintained. `BaseEvent.__init_subclass__` rejects a subclass that does not declare
   its own.

3. **A new `*_events.py` module MUST be imported in `core/events/__init__.py`.** This is the
   one gap a comprehension cannot close — it cannot see what nobody imports.
   `tests/unit/test_event_registry_derivation.py` fails when it is missed.

4. **Never pass `occurred_at`.** `BaseEvent` defaults it to `datetime.now()` via a `kw_only`
   field. Override it only in tests or event replay. ⚠ Subscribers read it directly, so an
   event published for a backfilled or future occurrence stamps it as happening *now*.

## Where to look

| You want | Go to |
|----------|-------|
| The live catalog of every event type | `list_event_types()` — derived, never stale |
| How to define, publish, subscribe | `core/events/base.py` (module docstring) |
| Who subscribes to what | `git grep -n '\.subscribe('` — see the note below |
| The event bus itself | `adapters/infrastructure/event_bus.py` |
| The pattern in full | `docs/patterns/event_driven_architecture.md` |

Publish through the helper, which logs and swallows nothing:

```python
from core.events import publish_event

await publish_event(self.event_bus, TaskCompleted(task_uid=uid, user_uid=user_uid), self.logger)
```

Handlers are named `handle_{event_name}` and must be **idempotent** — an event may be
delivered more than once, and a handler that accumulates rather than derives will double-count.

### Where subscriptions live

`services_bootstrap/_event_wiring.py` holds most of them, but it is **not** the only site, and
auditing an event's consumers by reading it alone will miss live handlers. Components that own
their own handlers subscribe themselves — the embedding worker, the metrics handler, the
FULL-tier intelligence hub, the analytics/AI service bases. `git grep -n '\.subscribe('` is the
answer that stays true; this file deliberately does not list the sites, for the reason below.

## Why there is no event table here

There used to be one. It listed 22 events with a "Subscribers" column, of which 4 named no
real event and 85 real events were missing — and the file it lived in described five event
modules as "(to be created)" that had shipped in the same commit as the README itself.

That is not staleness. It is a **plan mistaken for documentation**: a pre-implementation
migration doc (it carried a four-week timeline and a target completion date) that shipped
alongside its own implementation and was never retired. Seven commits touched it afterwards
and each fixed the row its author came for, leaving the frame intact.

A per-domain publisher/subscriber table has no mechanism keeping it honest: nothing imports
it, nothing greps it, no test fails when it drifts. `list_event_types()` and a `git grep` over
the wiring cannot drift, because they *are* the thing — they read the code rather than describe
it. Point at them instead.

If a catalog is ever genuinely wanted, generate it and drift-test it — the precedent is
`docs/reference/GRAPH_CONTRACT.yaml` (`scripts/generate_graph_contract.py`). Do not
hand-write one back.
