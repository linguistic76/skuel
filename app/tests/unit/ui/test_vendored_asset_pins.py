"""Pin the vendored-asset version constants to the service worker's precache list.

Why this exists
---------------
Three copies of one fact — which version of HTMX, Alpine and the Chart.js date
adapter this app serves — sit in three files: the ``*_VERSION`` constants in
``ui/theme.py``, the versioned filenames in ``static/service-worker.js``'s
``PRECACHE_URLS``, and the files themselves under ``static/vendor/``. Until this
module they were held in sync by a warning in CLAUDE.md ("upgrading Alpine/HTMX
touches two files"), which is the weakest possible remedy: a discipline a human
must remember.

The cost of forgetting is not a stale asset. ``install`` calls
``cache.addAll(PRECACHE_URLS)``, which rejects **wholesale** on a single 404 — so
one missed filename breaks service-worker installation for every PWA client, and
does it silently in the browser rather than loudly in CI.

Three directions, all cheap:

1. Every ``PRECACHE_URLS`` entry resolves to a file on disk. This is the
   ``addAll`` contract stated as an assertion.
2. Every ``/static/`` asset ``ui/theme.py`` emits from a ``*_VERSION`` constant is
   in ``PRECACHE_URLS``. This is the direction the CLAUDE.md warning describes.
3. Every ``*_VERSION`` constant is actually used to build a URL. A version
   constant nothing reads is a catalog copy with no reader — it cannot drift into
   a broken precache, but it also states a fact nothing checks. (``CHARTJS_VERSION``
   was exactly that, and was deleted rather than exempted.)

This module's inputs reach CI through ci.yml's ``py`` filter, which lists
``app/static/service-worker.js`` and ``app/static/vendor/**`` explicitly — they
are not Python, so ``app/**/*.py`` does not match them and a bare vendor bump
would otherwise skip ``unit_tests`` entirely. The render smoke test is not a
substitute: ``smoke_test.py`` stubs service-worker registration.

Not asserted: that ``PRECACHE_URLS`` covers everything ``theme.py`` emits.
``output.css`` is deliberately absent — it is a build artifact, and
``cacheFirst()`` caches every ``/static/`` response anyway, which is why
``CACHE_VERSION`` and not precache membership is what a change to it must bump.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[3]
THEME = APP_ROOT / "ui" / "theme.py"
SERVICE_WORKER = APP_ROOT / "static" / "service-worker.js"
STATIC = APP_ROOT / "static"

# Extraction floors: an extractor regression that returns an empty list must fail
# loudly, not agree vacuously with an equally empty other side.
MIN_PRECACHE_URLS = 10
MIN_VERSION_CONSTANTS = 3

_PRECACHE_RE = re.compile(r"const PRECACHE_URLS\s*=\s*\[(?P<body>.*?)\];", re.DOTALL)
_URL_RE = re.compile(r"'(?P<url>[^']+)'")
_VERSION_CONST_RE = re.compile(
    r"^(?P<name>[A-Z][A-Z0-9_]*_VERSION)\s*=\s*\"(?P<value>[^\"]+)\"", re.MULTILINE
)
# A `/static/...` path in theme.py built by interpolating a version.
_VERSIONED_SRC_RE = re.compile(r'f"(?P<url>/static/[^"]*\{(?P<var>[A-Za-z_]+)\}[^"]*)"')


def precache_urls() -> list[str]:
    match = _PRECACHE_RE.search(SERVICE_WORKER.read_text(encoding="utf-8"))
    assert match is not None, "PRECACHE_URLS array not found in static/service-worker.js"
    return [m.group("url") for m in _URL_RE.finditer(match.group("body"))]


def version_constants() -> dict[str, str]:
    return {
        m.group("name"): m.group("value")
        for m in _VERSION_CONST_RE.finditer(THEME.read_text(encoding="utf-8"))
    }


def versioned_asset_urls() -> dict[str, str]:
    """``/static/`` URLs ``theme.py`` builds from a version, keyed by the URL.

    The interpolated name is either the constant itself
    (``CHARTJS_ADAPTER_VERSION``) or the keyword parameter it defaults
    (``htmx_version``); both resolve by uppercasing, which is what the naming
    convention buys. A name that resolves to no constant fails loudly rather
    than dropping the asset from coverage.
    """
    source = THEME.read_text(encoding="utf-8")
    constants = version_constants()
    resolved: dict[str, str] = {}
    for match in _VERSIONED_SRC_RE.finditer(source):
        name = match.group("var").upper()
        assert name in constants, (
            f"ui/theme.py interpolates {{{match.group('var')}}} into {match.group('url')!r}, "
            f"but no constant {name} exists — this extractor resolves a version by "
            "uppercasing the interpolated name."
        )
        url = match.group("url").replace(f"{{{match.group('var')}}}", constants[name])
        resolved[url] = name
    return resolved


def static_path(url: str) -> Path:
    """The file a served URL maps to. ``/offline.html`` is served from ``static/``."""
    return STATIC / url.removeprefix("/static/").removeprefix("/")


def test_extraction_is_above_the_floor() -> None:
    urls = precache_urls()
    assert len(urls) >= MIN_PRECACHE_URLS, (
        f"only {len(urls)} precache URLs parsed — the extractor regressed, not the list."
    )
    assert len(set(urls)) == len(urls), f"PRECACHE_URLS repeats an entry: {sorted(urls)}"
    assert len(version_constants()) >= MIN_VERSION_CONSTANTS, (
        "fewer than three *_VERSION constants parsed from ui/theme.py"
    )


@pytest.mark.parametrize("url", precache_urls())
def test_every_precache_url_exists_on_disk(url: str) -> None:
    """``cache.addAll`` rejects wholesale on one 404 — a missing file breaks install."""
    assert static_path(url).is_file(), (
        f"PRECACHE_URLS names {url!r}, which is not a file under static/. "
        "cache.addAll() rejects the WHOLE list on a single 404, so this breaks "
        "service-worker installation for every PWA client."
    )


@pytest.mark.parametrize(("url", "constant"), sorted(versioned_asset_urls().items()))
def test_versioned_assets_are_precached(url: str, constant: str) -> None:
    """The CLAUDE.md warning, enforced: bumping a version touches two files."""
    assert static_path(url).is_file(), (
        f"ui/theme.py serves {url!r} (from {constant}) but no such file is vendored — "
        f"bump {constant} and drop the matching file into static/vendor/ together."
    )
    assert url in precache_urls(), (
        f"ui/theme.py serves {url!r} (from {constant}) but static/service-worker.js "
        f"does not precache it. Update PRECACHE_URLS and bump CACHE_VERSION."
    )


def test_every_version_constant_builds_a_url() -> None:
    """A version constant nothing reads states a fact nothing can check."""
    used = set(versioned_asset_urls().values())
    unread = sorted(set(version_constants()) - used)
    assert not unread, (
        f"*_VERSION constants in ui/theme.py that build no asset URL: {unread}. "
        "Delete them — a version nobody reads is a copy of a fact with no reader "
        "(CHARTJS_VERSION was one, and said '4' beside a vendored Chart.js 4.5.1)."
    )
