"""Pin ``scripts/health/route_catalog.py`` — the one route table both docs readers consume.

Two things this file exists to hold shut, each a measured defect in the instrument's
first cut:

1. **The catch-all.** ``fast_app()`` installs ``/{fname:path}.{ext:static}`` at root
   scope. Normalised it is ``/{}``, and ``/{}`` matches EVERY single-segment claim —
   ``/ku``, ``/home``, ``/sel`` all read as registered while it is present, and a scan
   built on such a catalog is green over a corpus full of them. Its absence is pinned
   by name, and the positive controls below would catch its return even if the name
   changed.
2. **The static view is not the table.** The AST extractor sees string literals only;
   the factories register through f-strings. The subset assertion prints the size of
   the gap so a shrinking one is visible, and never asserts it equal.

The runtime probe runs ONCE here, on the real tree. Every other test that needs a
catalog builds a ``RouteCatalog`` from a literal ``frozenset`` — that is the injection
seam, and it is why a throwaway docs root never has to boot the route tree.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/health/ has no __init__.py — add it to sys.path for import (matches
# test_dead_doc_links.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))

import route_catalog as rc  # type: ignore[import-not-found]

# Known-dead: each was cited as live by at least one doc on 2026-09-19 and has no
# handler. Known-live: factory-registered routes the static view cannot see.
KNOWN_DEAD = ("/ku", "/home", "/sel", "/reports", "/teaching", "/api/moc/organize")
KNOWN_LIVE_FACTORY = (
    "/tasks",
    "/api/tasks/create",
    "/api/tasks/{uid}/lateral/blocks",
    "/explore/ku/{uid}",
    "/today",
)


@pytest.fixture(scope="module")
def runtime() -> frozenset[str]:
    return rc.runtime_route_paths()


# ============================================================================
# THE RUNTIME TABLE — one probe, on the real tree
# ============================================================================


def test_runtime_table_is_the_size_of_a_real_route_tree(runtime: frozenset[str]) -> None:
    """A probe whose wiring silently failed returns a handful of infrastructure routes,
    not the application. The floor is well under the measured 891 and well over what
    a broken probe yields."""
    assert len(runtime) > 500, f"runtime route table looks empty: {len(runtime)}"
    assert all(p.startswith("/") for p in runtime)


def test_the_root_static_catch_all_is_stripped(runtime: frozenset[str]) -> None:
    """Pinned BY NAME: this is the route that made every single-segment claim match."""
    assert not any(rc.CATCH_ALL_MARKER in p for p in runtime)
    assert "/{}" not in rc.runtime_catalog().paths


@pytest.mark.parametrize("dead", KNOWN_DEAD)
def test_known_dead_route_is_not_registered(dead: str) -> None:
    """A catalog that admits a dead route hides real rot — the failure direction that
    matters, and the one the catch-all produced."""
    norm = rc.normalize(dead)
    assert norm is not None
    assert not rc.runtime_catalog().is_registered(norm), dead


@pytest.mark.parametrize("live", KNOWN_LIVE_FACTORY)
def test_known_live_factory_route_is_registered(live: str) -> None:
    """A catalog that refuses a live route turns the sweep queue into noise — and
    every one of these is invisible to the static view."""
    norm = rc.normalize(live)
    assert norm is not None
    assert rc.runtime_catalog().is_registered(norm), live


def test_static_view_is_a_strict_subset_of_the_runtime_table(
    runtime: frozenset[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """``ast_paths ⊆ runtime_paths``, gap printed, never asserted equal.

    A literal the runtime table lacks would mean a registration the probe does not
    reach (a tier branch the mock does not satisfy, or a module bootstrap no longer
    wires) — that is the assertion. The gap is the factories' share; it is printed so
    a change in it is visible in the test log, and not asserted because its exact
    size is a fact about the routes tree, not about this catalog.
    """
    static = rc.ast_route_paths()
    assert len(static) > 100, f"static extractor looks empty: {len(static)}"
    missing = sorted(static - runtime)
    assert missing == [], f"literal routes the runtime probe did not register: {missing}"
    with capsys.disabled():
        print(
            f"\nroute catalog: {len(static)} static literals ⊆ {len(runtime)} runtime paths "
            f"(gap {len(runtime - static)} factory-registered)"
        )


def test_the_probe_writes_nothing_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """The route modules log every registration at INFO; a reader's stdout is its
    report, so the wiring is captured. Cleared and rebuilt so the cache cannot hide
    a leak."""
    rc.runtime_route_table.cache_clear()
    rc.runtime_catalog.cache_clear()
    rc.runtime_route_paths()
    out, err = capsys.readouterr()
    assert out == ""
    assert err == ""


# ============================================================================
# NORMALISATION AND THE THREE RELATIONS — on a literal catalog
# ============================================================================


@pytest.mark.parametrize(
    ("raw", "norm"),
    [
        ("/tasks", "/tasks"),
        ("/tasks/", "/tasks"),
        ("/", "/"),
        ("/tasks?uid=abc#frag", "/tasks"),
        ("/api/tasks/{uid}/complete", "/api/tasks/{}/complete"),
        ("/{fname:path}.{ext:static}", "/{}"),
        ("/api/{domain}/{uid}", "/api/{}/{}"),
        ("tasks", None),
        ("", None),
    ],
)
def test_normalize(raw: str, norm: str | None) -> None:
    assert rc.normalize(raw) == norm


@pytest.fixture
def catalog() -> rc.RouteCatalog:
    return rc.RouteCatalog(
        {
            "/tasks",
            "/api/tasks/create",
            "/api/tasks/{uid}/complete",
            "/api/context/rich",
            "/library/ku",
            "/manifest.json",
        }
    )


@pytest.mark.parametrize(
    "claim",
    ["/tasks", "/tasks/", "/api/tasks/create", "/api/tasks/{task_uid}/complete", "/manifest.json"],
)
def test_is_registered_exact_and_registration_side_wildcard(
    catalog: rc.RouteCatalog, claim: str
) -> None:
    norm = rc.normalize(claim)
    assert norm is not None
    assert catalog.is_registered(norm)


def test_claim_side_wildcard_matches_a_family(catalog: rc.RouteCatalog) -> None:
    """A pattern doc's `/api/{domain}/create` describes the family `/api/tasks/create`
    belongs to — wild on the CLAIM side matches too."""
    assert catalog.is_registered("/api/{}/create")
    assert not catalog.is_registered("/api/{}/delete")


def test_wildcards_never_cross_within_one_match() -> None:
    """`/api/ku/related/{uid}` is NOT served by `/api/ku/{uid}/mark-studying`: that
    reading needs the registration's parameter to eat `related` AND the claim's
    placeholder to eat `mark-studying` — two routes, neither of which exists. Either
    direction alone still matches (instance, family)."""
    catalog = rc.RouteCatalog({"/api/ku/{uid}/mark-studying"})
    assert not catalog.is_registered("/api/ku/related/{}")
    assert catalog.is_registered("/api/ku/abc/mark-studying")  # instance
    assert catalog.is_registered("/api/{}/{}/mark-studying")  # family
    assert catalog.is_registered("/api/ku/{}/mark-studying")  # same shape
    assert not catalog.is_registered("/api/ku/{}/mark-understood")


def test_claimed_method_is_held_to_the_registration() -> None:
    """The runtime table carries verbs; a claim that writes one must be served for
    it. A method-blind catalog (bare paths) accepts any verb — the tests' seam."""
    with_verbs = rc.RouteCatalog(
        {"/api/events/{uid}/status": ["POST"], "/tasks": ["GET", "HEAD", "POST"]}
    )
    assert with_verbs.is_registered("/api/events/{}/status")
    assert with_verbs.is_registered("/api/events/{}/status", "POST")
    assert with_verbs.is_registered("/api/events/{}/status", "post")
    assert not with_verbs.is_registered("/api/events/{}/status", "PUT")
    assert not with_verbs.is_registered(
        "/api/events/abc/status", "PUT"
    )  # wildcard path, same verb rule
    assert with_verbs.methods_for("/tasks") == frozenset({"GET", "HEAD", "POST"})
    blind = rc.RouteCatalog({"/api/events/{uid}/status"})
    assert blind.is_registered("/api/events/{}/status", "PUT")
    assert blind.methods_for("/api/events/{}/status") is None


def test_two_registrations_of_one_shape_pool_their_verbs() -> None:
    catalog = rc.RouteCatalog({"/x/{a}": ["GET"], "/x/{b}": ["POST"]})
    assert catalog.is_registered("/x/{}", "GET")
    assert catalog.is_registered("/x/{}", "POST")
    assert not catalog.is_registered("/x/{}", "DELETE")


def test_runtime_table_carries_verbs_for_a_post_only_route(runtime: frozenset[str]) -> None:
    """Corpus pin: `/api/events/{uid}/status` is registered for POST alone, so the
    claim `PUT /api/events/{uid}/status` a doc makes is not matched."""
    catalog = rc.runtime_catalog()
    assert "/api/events/{}/status" in catalog.paths
    assert catalog.methods_for("/api/events/{}/status") == frozenset({"POST"})
    assert not catalog.is_registered("/api/events/{}/status", "PUT")


@pytest.mark.parametrize("claim", ["/ku", "/home", "/api/tasks", "/api/tasks/create/extra"])
def test_unregistered_paths_do_not_match(catalog: rc.RouteCatalog, claim: str) -> None:
    norm = rc.normalize(claim)
    assert norm is not None
    assert not catalog.is_registered(norm)


def test_family_prefix_is_a_strict_prefix_of_a_registration(catalog: rc.RouteCatalog) -> None:
    """Wildcards apply here too: `/api/tasks/anything` is a prefix of
    `/api/tasks/{uid}/complete`. Generous is fine for a class that is printed and never
    skipped — the relation is only ever consulted for a claim that already failed to
    match."""
    assert catalog.is_family_prefix("/api/context")
    assert catalog.is_family_prefix("/api/tasks")
    assert catalog.is_family_prefix("/api/tasks/anything")
    assert not catalog.is_family_prefix("/api/nothing")
    assert not catalog.is_family_prefix("/library/ku/deeper")


def test_relative_suffix_is_one_segment_ending_a_deeper_route(catalog: rc.RouteCatalog) -> None:
    """`/ku` ends `/library/ku`; `/create` ends `/api/tasks/create`. `/tasks` is a
    root route and `/api/create` is two segments — neither is a relative citation."""
    assert catalog.is_relative_suffix("/ku")
    assert catalog.is_relative_suffix("/create")
    assert not catalog.is_relative_suffix("/tasks")
    assert not catalog.is_relative_suffix("/api/create")
    assert not catalog.is_relative_suffix("/nothing")


def test_ast_extractor_reads_literals_only(tmp_path: Path) -> None:
    """A docstring is prose: grepping `@rt("` would register `/ghost` from the
    fixture's own docstring. And an f-string is not a literal — the static view
    cannot see `/{domain}`, which is the whole reason the runtime table exists."""
    inbound = tmp_path / "adapters" / "inbound"
    inbound.mkdir(parents=True)
    (inbound / "routes.py").write_text(
        "def register(rt, domain):\n"
        '    """Docstring example: @rt("/ghost") — prose, not a registration."""\n'
        '    @rt("/journals", methods=["GET"])\n'
        "    def journals(request):\n"
        "        return None\n"
        '    @rt(f"/{domain}")\n'
        "    def listing(request):\n"
        "        return None\n",
        encoding="utf-8",
    )
    assert rc.ast_route_paths(inbound) == frozenset({"/journals"})
    assert rc.ast_route_paths(tmp_path / "nowhere") == frozenset()
