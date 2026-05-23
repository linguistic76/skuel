# Upstream: FastHTML `parse_form` crashes on an empty `application/json` body

**Status:** interim shim in place ([`adapters/inbound/fasthtml_empty_json_patch.py`](../../adapters/inbound/fasthtml_empty_json_patch.py)); upstream fix **submitted as [AnswerDotAI/fasthtml#880](https://github.com/AnswerDotAI/fasthtml/pull/880)** — remove the shim once a FastHTML release containing it is pinned.
**Affects:** `python-fasthtml` 0.12.x … latest (`main` has the identical gap, verified 2026-05-22).

## Problem

`fasthtml.core.parse_form` runs for **every** route via `_wrap_req` → `_wrap_call`,
*before* any handler/decorator, to turn the request body into the param dict. It guards an
empty `multipart/form-data` body (returns `FormData()`), but the `application/json` branch
calls `await req.json()` directly. Starlette's `request.json()` does `json.loads(b"")` on an
empty body → `JSONDecodeError`, which is uncaught → **500** before the route runs.

So any bodyless `POST` (or PUT/PATCH) sent with `Content-Type: application/json` — common
from HTTP clients/SDKs that set that header by default — 500s, even for endpoints that take
no body. Starlette deliberately won't change `request.json()` to tolerate this
([Kludex/starlette#788](https://github.com/Kludex/starlette/issues/788)), so the fix belongs
in FastHTML's `parse_form` — exactly where the empty-multipart grace already lives. It's a
recognized cross-framework bug class (e.g. [fastify/fastify#5148](https://github.com/fastify/fastify/issues/5148)).

### Current code (`fasthtml/core.py`, `nbs/api/00_core.ipynb`)

```python
async def parse_form(req: Request) -> FormData:
    "Starlette errors on empty multipart forms, so this checks for that situation"
    ctype = req.headers.get("Content-Type", "")
    if ctype.startswith("multipart/form-data"):
        try: boundary = ctype.split("boundary=")[1].strip()
        except IndexError: raise HTTPException(400, "Invalid form-data: no boundary")
        if int(req.headers.get("Content-Length", "0")) <= len(boundary) + 6: return FormData()
        return await req.form()
    await req.body()  # Cache body for non-multipart request types
    return await req.json() if ctype == 'application/json' else await req.form()
```

### Reproduction

```python
from fasthtml.common import FastHTML
from starlette.testclient import TestClient

app = FastHTML()
@app.post("/x")
async def x(request): return "ok"

TestClient(app, raise_server_exceptions=False).post(
    "/x", headers={"content-type": "application/json"}
)  # -> 500, JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

## Proposed fix

Mirror the empty-multipart guard for json: an empty json body yields `{}` (no crash),
non-empty parses as before. Reuses the already-cached body.

```python
async def parse_form(req: Request) -> FormData:
    "Starlette errors on empty multipart/json forms, so this checks for that situation"
    ctype = req.headers.get("Content-Type", "")
    if ctype.startswith("multipart/form-data"):
        try: boundary = ctype.split("boundary=")[1].strip()
        except IndexError: raise HTTPException(400, "Invalid form-data: no boundary")
        if int(req.headers.get("Content-Length", "0")) <= len(boundary) + 6: return FormData()
        return await req.form()
    body = await req.body()  # Cache body for non-multipart request types
    if ctype == 'application/json':
        return await req.json() if body else {}
    return await req.form()
```

### Contributing (FastHTML is nbdev-based)

The source of truth is the `parse_form` cell in `nbs/api/00_core.ipynb`; `fasthtml/core.py`
is generated. Edit the notebook cell, add a test cell (the reproduction above, asserting
`200`), then `nbdev_prepare` (exports → `fasthtml/core.py`, runs tests, cleans notebooks).

**Issue title:** `parse_form 500s on empty application/json body (empty multipart is guarded, json is not)`

**PR title:** `Treat an empty application/json body as {} in parse_form (mirror empty-multipart guard)`

## SKUEL interim shim — removal trigger

Until a fixed FastHTML release is pinned, [`fasthtml_empty_json_patch.py`](../../adapters/inbound/fasthtml_empty_json_patch.py)
applies the identical guard at bootstrap (`scripts/dev/bootstrap.py`, Step 0), and
`tests/unit/test_fasthtml_empty_json_patch.py` exercises the real FastHTML path.

**Automated signal:** `test_shim_is_still_required` runs the *original* (pre-shim) `parse_form`
against an empty json body. It passes while FastHTML still raises (shim doing real work) and
**fails the moment a pinned FastHTML release handles empty json natively** — the trigger to
retire the workaround, so the monkeypatch can't silently outlive its purpose.

**Removal procedure** (when that tripwire goes red — i.e. `python-fasthtml` is bumped to a release
containing the fix):
1. Delete `adapters/inbound/fasthtml_empty_json_patch.py`.
2. Delete the Step-0 call in `scripts/dev/bootstrap.py`.
3. Delete `tests/unit/test_fasthtml_empty_json_patch.py`.
4. Delete this doc.

The behavior-level tests stay green throughout (upstream produces the same result), confirming
the removal is clean.
