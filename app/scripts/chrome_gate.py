"""The chrome snapshot gate — real routes, mocked services, rendered in
headless Chrome at 320/375/640/768/1440 for three personas (member, teacher,
admin). Every PR that touches the global chrome (navbar, bottom nav, sidebar,
section nav, BasePage geometry) runs it BEFORE and AFTER and reports both.

Asserts INVARIANTS, never pixels (the font is the host's fallback):
  - document.scrollWidth == document.clientWidth   (nothing overflows the page)
  - below lg, the [aria-current="page"] link of the section nav lies fully inside
    the row's visible box (the centring script did its job)
  - at lg+, the section nav is display:none and the desktop <nav> shows the same
    current link
  - at lg+, the desktop sidebar's top equals the navbar's bottom (no strip, no overlap)
  - a near-empty page (the admin page here) has no phantom vertical scroll:
    document.scrollHeight == document.clientHeight at every width
  - a Tasks+ page's row and desktop sidebar both carry the Events row (/events)
  - the Tasks+ desktop sidebar carries the badge loader with hx-trigger="intersect once"
    (never "load"); a non-Tasks+ sidebar page (admin) carries no badge request at all
  - below sm, the bottom nav's CONTENT box is >= 44px tall and the main content's
    bottom padding clears the bar — both measured twice: as rendered (headless
    Chrome resolves env(safe-area-inset-bottom) to 0) and with a 34px inset
    EMULATED by setting the bar's padding-bottom inline (the iPhone home
    indicator's value). A real device's env() is not measured here.
  One navbar, one rule (three personas: member, pure teacher, admin):
  - below sm the bottom nav renders for EVERY role with exactly four tabs
  - exactly one global item is lit on the visible chrome surface (centre links
    at sm+, bottom tabs below), keyed by section: Tasks+ on every Tasks+ page,
    nothing doubled (not Today+Tasks+, not Calendar+Monthly)
  - no href="#" anywhere in the chrome
  - the navbar never overflows its row — measured at 640, where an admin's
    bar carries six centre links plus the icon cluster
  - the role doors: Admin/Teaching centre links per role at sm+, and the
    same set as sm:hidden rows on /settings below sm

Phone widths render through an <iframe> wrapper because headless Chrome clamps
its window to 500px wide; the page postMessages its measurements up.

Usage:  uv run python scripts/chrome_gate.py [out_dir]
Writes <out_dir>/<page>_<width>.png beside the rendered HTML; exit 0 = GREEN.
Record: /docs/roadmap/done/tasks-plus-one-chrome.md
"""

import inspect
import json
import subprocess
import sys
import traceback
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))

from fasthtml.common import fast_app
from starlette.testclient import TestClient

from core.utils.auth_context import AuthState
from core.utils.result_simplified import Result

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/chrome_gate")
OUT.mkdir(parents=True, exist_ok=True)
STATIC = (APP_ROOT / "static").as_uri() + "/"
WIDTHS = (320, 375, 640, 768, 1440)

app, rt = fast_app(pico=False, default_hdrs=False)


def fake_user(_r):
    return "user_x"


import ui.layouts.navbar as nb

PERSONAS = {
    "member": AuthState(user_uid="user_x", is_admin=False, is_teacher=False),
    "teacher": AuthState(user_uid="user_x", is_admin=False, is_teacher=True),
    "admin": AuthState(user_uid="user_x", is_admin=True, is_teacher=True),
}
state = PERSONAS["member"]
nb.current_auth_state = lambda: state

import ui.settings.page as sp

sp.current_auth_state = lambda: state

# /tasks
import adapters.inbound.activity_ui_factory as auf
import adapters.inbound.tasks_ui as tu

auf.require_authenticated_user = fake_user
tu.require_authenticated_user = fake_user
tu.create_tasks_ui_routes(app, rt, MagicMock(), MagicMock())

# /events — the Events row lights on its own page
import adapters.inbound.events_ui as ev

ev.require_authenticated_user = fake_user
ev.create_events_ui_routes(app, rt, MagicMock(), MagicMock())

# /gradebook
import adapters.inbound.user_entry_ui as ue

ue.require_authenticated_user = fake_user
params = list(inspect.signature(ue.create_user_entry_ui_routes).parameters)[2:]
orch = MagicMock()
orch.get_student_exchange_summaries = AsyncMock(
    return_value=Result.ok({"exercises": [], "other_feedback": []})
)
orch.get_activity_report_history = AsyncMock(return_value=Result.ok([]))
kw = {p: MagicMock() for p in params}
kw["orchestrator"] = orch
ue.create_user_entry_ui_routes(app, rt, **kw)

# /cal/week/<date>
import adapters.inbound.calendar_ui as cu

cu.require_authenticated_user = fake_user
cu.create_calendar_ui_routes(app, rt, MagicMock())

# /today
import adapters.inbound.today_routes as tr

tr.require_authenticated_user = fake_user
today_ctx = {
    "today_iso": date.today().isoformat(),
    "date_label": "Saturday · September 19",
    "heading": "Today",
    "is_today": True,
    "can_quick_add": True,
    "overdue": [],
    "tasks": [],
    "events": [],
    "habits": [],
    "milestones": [],
    "choices": [],
}
services = MagicMock()
services.today_orchestrator.build_context = AsyncMock(return_value=Result.ok(today_ctx))
tr.create_today_routes(app, rt, services)

# /settings
import adapters.inbound.settings_routes as sr

sr.require_authenticated_user = fake_user
settings_services = MagicMock()
sr.create_settings_routes(app, rt, settings_services)

# /admin — the real @require_admin route: the role gate fetches the user and
# checks has_permission, so the mocked user service answers with an admin.
import adapters.inbound.admin_dashboard_ui as adu
import adapters.inbound.auth.roles as roles

roles.require_authenticated_user = fake_user
admin_user = MagicMock()
admin_user.has_permission = lambda _role: True
admin_user.display_name = "Mike"
admin_user.title = "Mike"
admin_orch = MagicMock()
admin_orch.user_service.get_user = AsyncMock(return_value=Result.ok(admin_user))
admin_orch.get_system_status = AsyncMock(return_value={"status": "healthy", "healthy": True})
adu.create_admin_dashboard_routes(app, rt, admin_orch, MagicMock())

# /profile/shared — the one route left under the retired hub's prefix; it
# lights the inbox icon and nothing else. /profile itself is a 404, no redirect.
import adapters.inbound.user_profile_ui as pu

pu.require_authenticated_user = fake_user
sharing_services = MagicMock()
sharing_services.sharing.get_shared_with_me = AsyncMock(return_value=Result.ok([]))
pu.setup_user_profile_routes(rt, sharing_services)

today = date.today()
PAGES = {
    "today": "/today",
    "tasks": "/tasks",
    "events": "/events",
    "gradebook": "/gradebook",
    "cal_week": f"/cal/week/{today.isoformat()}",
    "cal_month": f"/cal/month/{today.year}/{today.month}",
    "settings": "/settings",
    "admin": "/admin",
    "shared": "/profile/shared",
}
# Which persona renders which page. Every Tasks+ page is rendered as a member;
# the teacher and admin personas render the landing, /settings (their role
# rows) and, for the admin, the real /admin route.
PERSONA_PAGES = {
    "member": [
        "today",
        "tasks",
        "events",
        "gradebook",
        "cal_week",
        "cal_month",
        "settings",
        "shared",
    ],
    "teacher": ["today", "settings"],
    "admin": ["today", "settings", "admin"],
}
TASKS_PLUS = {"today", "tasks", "events", "gradebook", "cal_week", "cal_month"}

GATE_JS = """
<script>
window.addEventListener('load', function () {
  var doc = document.documentElement;
  var row = document.querySelector('.section-nav ul');
  var cur = row && row.querySelector('[aria-current="page"]');
  var desk = document.querySelector('nav[aria-label$=" sidebar"]');
  var deskCur = desk && desk.querySelector('[aria-current="page"]');
  var r = {
    width: window.innerWidth,
    scrollWidth: doc.scrollWidth, clientWidth: doc.clientWidth,
    rowVisible: !!row && getComputedStyle(row).display !== 'none' && row.clientWidth > 0,
    rowScrollWidth: row ? row.scrollWidth : null, rowClientWidth: row ? row.clientWidth : null,
    rowScrollLeft: row ? row.scrollLeft : null,
    overflowAttr: row ? row.parentElement.hasAttribute('data-overflow') : null,
    atEndAttr: row ? row.parentElement.hasAttribute('data-at-end') : null,
    current: cur ? cur.getAttribute('href') : null,
    currentInside: null,
    deskVisible: !!desk && getComputedStyle(desk).display !== 'none',
    deskCurrent: deskCur ? deskCur.getAttribute('href') : null,
    helpCircles: document.querySelectorAll('svg path[d^="M9.09 9a3 3 0 0 1 5.83 1"]').length,
    rowHasEvents: !!(row && row.querySelector('a[href="/events"]')),
    deskHasEvents: !!(desk && desk.querySelector('a[href="/events"]')),
    badgeLoaders: document.querySelectorAll('[hx-get="/api/sidebar/badges"]').length,
    deskTrigger: desk ? desk.getAttribute('hx-trigger') : null,
    deskBadgeGet: desk ? desk.getAttribute('hx-get') : null,
    scrollHeight: doc.scrollHeight, clientHeight: doc.clientHeight,
    navBottom: null, sideTop: null,
    bottomNav: null,
    hashLinks: 0, topOverflow: null, centreVisible: null, centreLinks: [], centreLit: [],
    tabs: [], tabsLit: [], tabsVisible: null, iconLit: [], tallLinks: 0,
    settingsRows: [],
  };
  var top = document.querySelector('nav[aria-label="Main navigation"]');
  if (top) { r.navBottom = Math.round(top.getBoundingClientRect().bottom * 100) / 100; }
  var bar0 = document.querySelector('nav[aria-label="Primary navigation"]');
  function visible(el) { return !!el && getComputedStyle(el).display !== 'none'; }
  function hrefs(nodes) { return Array.prototype.map.call(nodes, function (a) { return a.getAttribute('href'); }); }
  if (top) {
    r.hashLinks = top.querySelectorAll('a[href="#"]').length + (bar0 ? bar0.querySelectorAll('a[href="#"]').length : 0);
    var row = top.firstElementChild;
    r.topOverflow = { scroll: row.scrollWidth, client: row.clientWidth, height: top.offsetHeight };
    var centre = top.querySelector('div[class~="sm:flex"]');
    r.centreVisible = visible(centre);
    if (centre) {
      var links = Array.prototype.filter.call(centre.querySelectorAll('a'), visible);
      r.centreLinks = hrefs(links);
      r.centreLit = hrefs(links.filter(function (a) { return a.getAttribute('aria-current') === 'page'; }));
      links.forEach(function (a) { if (a.offsetHeight > 40) { r.tallLinks++; } });
    }
    var cluster = top.querySelector('div.flex.items-center.justify-end');
    r.iconLit = hrefs(cluster.querySelectorAll('a[aria-current="page"]'));
  }
  if (bar0) {
    r.tabsVisible = visible(bar0);
    r.tabs = hrefs(bar0.querySelectorAll('a'));
    r.tabsLit = hrefs(bar0.querySelectorAll('a[aria-current="page"]'));
  }
  var mainEl = document.getElementById('main-content');
  if (mainEl) {
    var rows = Array.prototype.filter.call(mainEl.querySelectorAll('a'), function (a) {
      var h = a.getAttribute('href');
      return h === '/logout' || h === '/admin' || h === '/teaching/students';
    });
    r.settingsRows = hrefs(rows);
    r.settingsRowsVisible = hrefs(rows.filter(visible));
  }
  if (desk && r.deskVisible) { r.sideTop = Math.round(desk.getBoundingClientRect().top * 100) / 100; }
  var bar = document.querySelector('nav[aria-label="Primary navigation"]');
  var main = document.getElementById('main-content');
  if (bar && getComputedStyle(bar).display !== 'none') {
    function measure(inset) {
      if (inset !== null) { bar.style.paddingBottom = inset + 'px'; }
      var cs = getComputedStyle(bar);
      var tab = bar.querySelector('a');
      return {
        height: bar.offsetHeight,
        contentBox: bar.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom),
        tabHeight: tab ? tab.offsetHeight : null,
        mainPadBottom: main ? parseFloat(getComputedStyle(main).paddingBottom) : null,
      };
    }
    r.bottomNav = { real: measure(null), emulated34: measure(34) };
    // Headless resolves env() to 0, so the inset can only be emulated on the
    // bar; main's clearance under a real inset is main's measured padding plus
    // the inset ONLY IF main declares the env() term itself — record that.
    r.mainFollowsInset = !!(main && (main.getAttribute('class') || '').indexOf('env(safe-area-inset-bottom)') !== -1);
  }
  if (cur && r.rowVisible) {
    var rb = row.getBoundingClientRect(), cb = cur.getBoundingClientRect();
    r.currentInside = cb.left >= rb.left - 0.5 && cb.right <= rb.right + 0.5;
    r.currentBox = [Math.round(cb.left), Math.round(cb.right)];
    r.rowBox = [Math.round(rb.left), Math.round(rb.right)];
  }
  if (window.parent !== window) { window.parent.postMessage(JSON.stringify(r), '*'); return; }
  var pre = document.createElement('pre'); pre.id = 'gate-result';
  pre.textContent = JSON.stringify(r); document.body.appendChild(pre);
});
</script>
"""

# Headless Chrome clamps its window to 500px wide, so a phone width is emulated
# through an iframe — an iframe has its own viewport, so media queries and
# innerWidth inside it are the iframe's width. The page posts its result up.
FRAME = """<!doctype html><html><body style="margin:0">
<iframe id="f" style="width:{w}px;height:1000px;border:0" src="{src}"></iframe>
<script>
window.addEventListener('message', function (e) {{
  var pre = document.createElement('pre'); pre.id = 'gate-result';
  pre.textContent = e.data; document.body.appendChild(pre);
}});
</script></body></html>"""


def write_html(name: str, html: str) -> Path:
    html = html.replace('href="/static/', f'href="{STATIC}').replace(
        'src="/static/', f'src="{STATIC}'
    )
    html = html.replace("</body>", GATE_JS + "</body>")
    path = OUT / f"{name}.html"
    path.write_text(html)
    return path


rendered: dict[str, Path] = {}
client = TestClient(app)
retired = client.get("/profile", follow_redirects=False)
assert retired.status_code == 404 and "location" not in retired.headers, (
    "GET /profile must be a real 404, not a redirect",
    retired.status_code,
)
print("ok  GET /profile → 404 (no redirect)")
failures = 0
for persona, page_names in PERSONA_PAGES.items():
    state = PERSONAS[persona]
    for page in page_names:
        name = f"{persona}_{page}"
        try:
            r = client.get(PAGES[page])
            assert r.status_code == 200, (name, r.status_code, r.text[:300])
            rendered[name] = write_html(name, r.text)
        except (
            Exception
        ):  # safety-net: a page that fails to render is a gate failure, not a skipped page
            # Every viewport check of this page is lost with it, so the run
            # must go RED here — otherwise a raising route reads as GREEN.
            failures += 1
            print(f"FAIL {name}: route did not render")
            traceback.print_exc()

EXPECTED_ROLE_DOORS = {
    "member": [],
    "teacher": ["/teaching/students"],
    "admin": ["/teaching/students", "/admin"],
}
ICON_DOORS = ["/today", "/explore/library", "/path-steps", "/submissions"]

for name, html_path in rendered.items():
    persona, page = name.split("_", 1)
    is_sidebar_page = page not in ("settings", "shared")
    for w in WIDTHS:
        png = OUT / f"{name}_{w}.png"
        target = html_path
        if w < 500:
            target = OUT / f"{name}_{w}_frame.html"
            target.write_text(FRAME.format(w=w, src=html_path.name))
        base = [
            "google-chrome",
            "--headless=new",
            "--no-sandbox",
            "--hide-scrollbars",
            "--allow-file-access-from-files",
            f"--window-size={max(w, 500)},1000",
            "--virtual-time-budget=4000",
        ]
        subprocess.run([*base, f"--screenshot={png}", target.as_uri()], capture_output=True)
        dom = subprocess.run(
            [*base, "--dump-dom", target.as_uri()], capture_output=True, text=True
        ).stdout
        start = dom.find('<pre id="gate-result">')
        if start < 0:
            print(f"{name}@{w}: NO GATE RESULT")
            failures += 1
            continue
        res = json.loads(
            dom[start + len('<pre id="gate-result">') : dom.index("</pre>", start)].replace(
                "&quot;", '"'
            )
        )
        problems = []
        if res["scrollWidth"] != res["clientWidth"]:
            problems.append(f"page overflows {res['scrollWidth']} > {res['clientWidth']}")
        if is_sidebar_page:
            # Both surfaces render the same SidebarItem list, so both must mark
            # the current page and agree on which it is — a missing mark is a
            # failure, never a skipped check.
            if not res["current"]:
                problems.append("section nav has no [aria-current=page] link")
            if not res["deskCurrent"]:
                problems.append("desktop sidebar has no [aria-current=page] link")
            if res["current"] and res["deskCurrent"] and res["current"] != res["deskCurrent"]:
                problems.append(
                    f"section nav current {res['current']} != desktop current {res['deskCurrent']}"
                )
            if w < 1024:
                if not res["rowVisible"]:
                    problems.append("section nav not visible below lg")
                elif res["current"] and res["currentInside"] is not True:
                    problems.append(
                        f"current link {res['current']} outside row {res.get('currentBox')} vs {res.get('rowBox')}"
                    )
                if res["deskVisible"]:
                    problems.append("desktop sidebar visible below lg")
            else:
                if res["rowVisible"]:
                    problems.append("section nav visible at lg+")
                if not res["deskVisible"]:
                    problems.append("desktop sidebar hidden at lg+")
            if w >= 1024 and res["sideTop"] != res["navBottom"]:
                problems.append(f"sidebar top {res['sideTop']} != navbar bottom {res['navBottom']}")
        if res["helpCircles"]:
            problems.append(f"{res['helpCircles']} help-circle fallback icon(s)")
        if page in TASKS_PLUS:
            if not res["rowHasEvents"] or not res["deskHasEvents"]:
                problems.append(
                    f"Events row missing (row={res['rowHasEvents']} desk={res['deskHasEvents']})"
                )
            if res["badgeLoaders"] != 1 or res["deskBadgeGet"] != "/api/sidebar/badges":
                problems.append(
                    f"badge loader count {res['badgeLoaders']} on the Tasks+ desktop sidebar"
                )
            if res["deskTrigger"] != "intersect once":
                problems.append(f"badge loader trigger {res['deskTrigger']!r} != 'intersect once'")
        elif res["badgeLoaders"]:
            problems.append(f"{res['badgeLoaders']} badge loader(s) on a non-Tasks+ page")
        if page in ("admin", "settings", "shared") and res["scrollHeight"] != res["clientHeight"]:
            problems.append(
                f"phantom vertical scroll {res['scrollHeight']} > {res['clientHeight']} on a near-empty page"
            )
        # --- one navbar, one rule ---
        if res["hashLinks"]:
            problems.append(f'{res["hashLinks"]} href="#" link(s) in the chrome')
        to = res["topOverflow"]
        if to and to["scroll"] > to["client"]:
            problems.append(f"navbar row overflows {to['scroll']} > {to['client']}")
        if to and to["height"] != 56:
            problems.append(f"navbar box {to['height']}px != 56 (a centre link wrapped?)")
        if res["tallLinks"]:
            problems.append(f"{res['tallLinks']} centre link(s) taller than one line")
        # The role doors are centre links at lg+ only (they do not fit beside
        # the section doors at 640); below lg they are /settings rows.
        expected_centre = ICON_DOORS + (EXPECTED_ROLE_DOORS[persona] if w >= 1024 else [])
        if w >= 640 and res["centreLinks"] != expected_centre:
            problems.append(f"centre links {res['centreLinks']} != {expected_centre}")
        if res["tabs"] != ICON_DOORS:
            problems.append(f"bottom tabs {res['tabs']} != {ICON_DOORS}")
        expected_lit = (
            ["/today"]
            if page in TASKS_PLUS
            else ([] if page in ("settings", "shared") else ["/admin"])
        )
        expected_icon_lit = {"settings": ["/settings"], "shared": ["/profile/shared"]}.get(page, [])
        if w >= 640 and res["centreLit"] != [h for h in expected_lit if h in expected_centre]:
            problems.append(f"centre lit {res['centreLit']} != {expected_lit}")
        if res["tabsLit"] != [h for h in expected_lit if h in ICON_DOORS]:
            problems.append(
                f"tabs lit {res['tabsLit']} != {[h for h in expected_lit if h in ICON_DOORS]}"
            )
        if res["iconLit"] != expected_icon_lit:
            problems.append(f"icon cluster lit {res['iconLit']} != {expected_icon_lit}")
        if w < 640:
            if res["centreVisible"] or not res["tabsVisible"]:
                problems.append(
                    f"below sm: centre visible={res['centreVisible']} tabs visible={res['tabsVisible']}"
                )
        else:
            if not res["centreVisible"] or res["tabsVisible"]:
                problems.append(
                    f"sm+: centre visible={res['centreVisible']} tabs visible={res['tabsVisible']}"
                )
        lit_visible = (res["tabsLit"] if w < 640 else res["centreLit"]) + res["iconLit"]
        if len(lit_visible) > 1:
            problems.append(
                f"{len(lit_visible)} global items lit on the visible surface: {lit_visible}"
            )
        if page == "settings":
            expected_rows = ["/logout"] + EXPECTED_ROLE_DOORS[persona]
            if res["settingsRows"] != expected_rows:
                problems.append(f"/settings rows {res['settingsRows']} != {expected_rows}")
            # Each row is visible exactly below the width its top-bar counterpart
            # appears at: sign-out below sm, the role doors below lg.
            expected_visible = (["/logout"] if w < 640 else []) + (
                EXPECTED_ROLE_DOORS[persona] if w < 1024 else []
            )
            if res["settingsRowsVisible"] != expected_visible:
                problems.append(
                    f"/settings rows visible {res['settingsRowsVisible']} != {expected_visible}"
                )
        bn = res["bottomNav"]
        if w < 640:
            if bn is None:
                problems.append("no bottom nav below sm")
            else:
                if not res.get("mainFollowsInset"):
                    problems.append(
                        "main padding does not declare env(safe-area-inset-bottom) — "
                        "the bar grows with the inset, the content clearance would not"
                    )
                for label, inset in (("real", 0), ("emulated34", 34)):
                    m = bn[label]
                    if m["contentBox"] < 44:
                        problems.append(
                            f"bottom nav content box {m['contentBox']}px < 44 ({label})"
                        )
                    # `+ inset` is main's clearance under the emulated inset —
                    # valid only because mainFollowsInset is asserted above.
                    if m["mainPadBottom"] is not None and m["mainPadBottom"] + inset < m["height"]:
                        problems.append(
                            f"main padding {m['mainPadBottom']}+{inset} < bottom nav {m['height']} ({label})"
                        )
        elif bn is not None:
            problems.append("bottom nav visible at sm+")
        status = "ok " if not problems else "FAIL"
        failures += bool(problems)
        geo = f"h={res['scrollHeight']}/{res['clientHeight']}"
        if w >= 1024:
            geo += f" side={res['sideTop']} nav={res['navBottom']}"
        elif res["bottomNav"]:
            m, e = res["bottomNav"]["real"], res["bottomNav"]["emulated34"]
            geo += f" bar={m['height']}/{m['contentBox']}→{e['height']}/{e['contentBox']} pad={m['mainPadBottom']}"
        lit = res["tabsLit"] if w < 640 else res["centreLit"]
        print(
            f"{status} {name}@{w}: current={res['current'] or res['deskCurrent']} lit={lit + res['iconLit']} row={res['rowScrollLeft']}/{res['rowClientWidth']}/{res['rowScrollWidth']} nav={to['scroll'] if to else None}/{to['client'] if to else None} {geo} {'; '.join(problems)}"
        )

print(f"\n{'GATE GREEN' if not failures else f'GATE RED ({failures})'} — shots in {OUT}")
sys.exit(1 if failures else 0)
