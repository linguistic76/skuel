"""The periodic note's navigation column — mini month + period rail.

The sidebar is the whole navigation surface of a periodic note, so what it can
reach is what the domain can reach. Two mechanisms, pinned here:

- the **mini month**, whose day cells open daily notes and whose leading ISO-week
  rail opens weekly notes — the same two doors ``create_month_grid`` carries
- the **period rail**, one row per period kind: open it, or step to a neighbour

The rail replaced the "up"-links ladder (#1277), which showed only the periods
*wider* than the note and could not step between notes of a kind. These assert
the shape that replaced it — five rows on every kind, and a stepper on each —
because a rail that quietly narrows to the old ladder's set would still render.
"""

from datetime import date, datetime

from fasthtml.common import Div, to_xml

from core.models.enums.entity_enums import EntityStatus
from core.models.user_entry.user_entry import UserEntry
from ui.journals.chat_page import PeriodicNotePage
from ui.journals.period_links import PERIOD_KINDS


def _sidebar(kind: str, period_key: str) -> str:
    created = datetime(2026, 9, 5, 8, 0)
    entry = UserEntry(
        uid=f"ue:{kind}:user_test:{period_key}",
        user_uid="user_test",
        title=f"{kind.title()} Note",
        content="",
        status=EntityStatus.ACTIVE,
        created_at=created,
        updated_at=created,
        metadata={"entry_kind": kind, "period_key": period_key},
    )
    return to_xml(PeriodicNotePage(entry=entry, initial_workspace=Div("workspace")))


# ---------------------------------------------------------------------------
# The mini month's two doors
# ---------------------------------------------------------------------------


def test_the_week_rail_links_every_rendered_row_to_its_weekly_note() -> None:
    """September 2026 renders as five Monday-first rows, weeks 36-40. A missing
    row means the rail is deriving the number from something other than the
    row's own days."""
    xml = _sidebar("monthly", "2026-09")

    for week in range(36, 41):
        assert f'href="/journals/weekly/2026/{week}"' in xml


def test_the_week_rail_uses_the_iso_year_at_a_year_boundary() -> None:
    """January 2027 opens in ISO week 53 of *2026*; a calendar-year number
    would mint week 53 of 2027, a period no parser accepts as that week."""
    xml = _sidebar("monthly", "2027-01")

    assert 'href="/journals/weekly/2026/53"' in xml


def test_day_cells_open_daily_notes() -> None:
    xml = _sidebar("monthly", "2026-09")

    assert 'href="/journals/daily/2026-09-01"' in xml
    assert 'href="/journals/daily/2026-09-30"' in xml


# ---------------------------------------------------------------------------
# The period rail
# ---------------------------------------------------------------------------


def test_every_kind_of_note_shows_every_period_row() -> None:
    """The rail does not change shape with the note being read — that is what
    makes one prev/next mechanism learnable instead of five."""
    for kind in PERIOD_KINDS:
        xml = _sidebar(kind, {"daily": "2026-09-05", "weekly": "2026-W36"}.get(kind, "2026"))
        for name in ("Daily note", "Weekly note", "Monthly note", "Quarterly note", "Yearly note"):
            assert name in xml, f"{kind} note is missing the {name} row"


def test_each_row_steps_backward_and_forward_from_the_note_period() -> None:
    """A monthly note for September 2026: the monthly row opens September and
    its arrows reach August and October, and every wider row steps too."""
    xml = _sidebar("monthly", "2026-09")

    for href in (
        "/journals/monthly/2026/8",
        "/journals/monthly/2026/9",
        "/journals/monthly/2026/10",
        "/journals/quarterly/2026/2",
        "/journals/quarterly/2026/3",
        "/journals/quarterly/2026/4",
        "/journals/yearly/2025",
        "/journals/yearly/2026",
        "/journals/yearly/2027",
    ):
        assert f'href="{href}"' in xml


def test_stepping_a_wider_row_crosses_the_year_the_calendar_hides() -> None:
    """A January note's month/quarter arrows leave 2026 backwards. The mini
    month shows only January, so nothing on screen says which year the arrow
    lands in — the label and accessible name have to."""
    xml = _sidebar("monthly", "2026-01")

    assert 'href="/journals/monthly/2025/12"' in xml
    assert 'href="/journals/quarterly/2025/4"' in xml
    assert "Previous monthly note — December 2025" in xml


def test_the_note_own_row_is_marked_current() -> None:
    """Exactly one row — a rail that marked none would read as "you are
    nowhere", and one that marked several as a bug in the kind match."""
    xml = _sidebar("quarterly", "2026-Q3")

    assert xml.count('aria-current="page"') == 1
    assert 'aria-label="Quarterly note — Q3 2026" aria-current="page"' in xml


def test_rail_links_opt_out_of_htmx_boost() -> None:
    """Journal routes answer with a 302 redirect; boosted, HTMX swaps it into
    the current target instead of navigating."""
    xml = _sidebar("daily", "2026-09-05")

    assert xml.count('hx-boost="false"') >= len(PERIOD_KINDS) * 3


# ---------------------------------------------------------------------------
# The anchor the sidebar centres on
# ---------------------------------------------------------------------------


def test_a_quarterly_note_centres_the_calendar_on_the_quarter_first_month() -> None:
    """Q3 opens on July. A month grid cannot draw a quarter, so the rail is
    what names it — the calendar just has to start somewhere honest."""
    xml = _sidebar("quarterly", "2026-Q3")

    assert "July 2026" in xml


def test_an_unparseable_period_key_falls_back_instead_of_raising() -> None:
    """The route has already served the note by the time the sidebar renders,
    so a key the parser rejects must degrade to the current period, never to a
    500 around a page that otherwise works."""
    xml = _sidebar("daily", "not-a-date")

    today = date.today()
    assert f'href="/journals/daily/{today.isoformat()}"' in xml
