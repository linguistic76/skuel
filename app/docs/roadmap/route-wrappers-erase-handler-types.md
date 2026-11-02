---
title: "Route Wrappers Erase a Handler's Type"
updated: 2026-11-02
status: "open — registered, not built; nothing reads the erased type"
registered: 2026-11-02
trigger: "code reads the type of a name an @rt-decorated handler binds (calls it, passes it on, reads its return), so a wrapper's Any reaches a checked site"
check: "AST over adapters/, ui/, scripts/, services_bootstrap/, core/: loads of the name an @rt-decorated def binds, in the scope that binds it, and rt(...)(f) results that are used rather than discarded — 0 and 0 across 510 decorated handlers"
---

# Route Wrappers Erase a Handler's Type

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

`RouteDecorator` (`adapters/inbound/fasthtml_types.py`) promises that `rt(path)` returns a
decorator of type `Callable[[Callable[P, R]], Callable[P, R]]`: the name a decorated handler
binds calls like the handler, with the same parameters and the same return type.
`tests/unit/adapters/test_route_param_types.py` checks the real `rt` keeps that promise. But `rt`
decorates whatever sits directly below it, and a wrapper there passes on only what its own
annotation keeps. Each wrapper found there erases at least the handler's return type before `rt`
sees it.

## Today

What sits directly under each of the 510 `@rt` decorations (`rt` 507, `self.rt` 3) in
`adapters/`, `ui/` and `scripts/`:

| Under `@rt` | Count | Annotation | What `rt` receives |
|---|---|---|---|
| the handler itself | 161 | — | the handler's own `P` and `R` |
| `csrf_protected` | 153 | `Callable[..., Awaitable[Any]] -> Callable[..., Awaitable[Any]]` (`adapters/inbound/csrf.py:222`) | `(*Any, **Any) -> Awaitable[Any]` |
| `boundary_handler` | 128 | `-> Callable[[Callable[P, Awaitable[Any]]], Callable[P, Coroutine[Any, Any, Any]]]` (`adapters/inbound/boundary.py:169`) | `P` kept; `R` is `Any` |
| `require_admin` / `require_role` / `require_teacher` | 32 / 26 / 4 | inner `decorator(func: Callable) -> Callable` (`adapters/inbound/auth/roles.py:304`) | `(*Any, **Any) -> Any` |
| `ui_boundary_handler` | 5 | `Callable[[Callable[P, Any]], Callable[P, Any]]` (`adapters/inbound/boundary.py:219`) | `P` kept; `R` is `Any` |
| `rate_limited_ip` | 1 | `-> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]` (`adapters/inbound/rate_limit.py:153`) | `(*Any, **Any) -> Awaitable[Any]` |

So 161 of 510 decorated handlers reach `rt` with their full type, and 133 more keep their
parameters.

Nothing reads what is lost. Every decorated handler is registered for the registration alone: no
first-party code loads the name a decorated handler binds, and no `rt(...)(f)` result is used. A
handler's own annotation is still checked against its body whatever wraps it. What the wrappers
erase is only the type of the name the decoration binds, and today nobody reads that name.

## What closing it takes (not ruled)

- `csrf_protected` and `rate_limited_ip` call the handler and return its result, so they could
  carry `Callable[P, Awaitable[R]] -> Callable[P, Coroutine[Any, Any, R]]`.
- `require_admin` / `require_role` / `require_teacher` change the signature. They drop
  `current_user` and publish a `__signature__` without it. `Concatenate` cannot remove a keyword
  parameter, so at most `R` passes through them.
- `boundary_handler` and `ui_boundary_handler` change `R` by design: they turn a `Result[T]` into
  a response. `P` already passes through them.

Until something reads the bound name, typing these wrappers buys nothing a check can see. The
first reader is the trigger.
