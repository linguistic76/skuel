"""Status and count pills render through ``Badge()`` (UI_COMPONENT_PATTERNS § Badges).

Each pin renders a surface and reads its pill's class list: Badge's base
classes, the palette of the variant the surface's state maps to, and the size.
"""

import html
import re
from typing import cast

import pytest
from fasthtml.common import to_xml

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.pipeline import ReportSource
from core.models.enums.principle_enums import AlignmentLevel
from core.models.report.entry_report import EntryReport
from core.models.shared.dual_track import DualTrackResult
from core.ports.query_types import KnowledgeHealthReport
from ui.admin.pages import _readiness_banner
from ui.dual_track_card import gap_card, render_checkin_trend
from ui.feedback import _BADGE_COLORS, BadgeT
from ui.finance.invoice_views import InvoiceViews
from ui.finance.types import InvoiceRow
from ui.patterns.hub import HubCard, HubCardData
from ui.patterns.report_item import render_report_item
from ui.user_entry.forms import _feedback_question, _share_question

BADGE_BASE = {"inline-flex", "items-center", "rounded-full", "border", "font-medium"}


def _pill(xml: str, text: str) -> set[str]:
    """The class tokens of the one ``<span>`` whose whole text is ``text``."""
    escaped = re.escape(html.escape(text, quote=False))
    matches = re.findall(rf'<span class="([^"]*)">{escaped}</span>', xml)
    assert len(matches) == 1, f"expected one {text!r} pill, found {len(matches)}"
    return set(matches[0].split())


def _assert_badge(tokens: set[str], variant: BadgeT, *size: str) -> None:
    assert tokens >= BADGE_BASE
    assert set(_BADGE_COLORS[variant.value].split()) <= tokens
    assert set(size) <= tokens


@pytest.mark.parametrize(
    ("ready", "text", "variant"),
    [(True, "GDS-ready", BadgeT.success), (False, "Building density", BadgeT.warning)],
)
def test_knowledge_health_readiness_pill(ready: bool, text: str, variant: BadgeT) -> None:
    # The banner reads only these two fields of the report.
    report = cast("KnowledgeHealthReport", {"gds_readiness_score": 0.42, "gds_ready": ready})
    _assert_badge(_pill(to_xml(_readiness_banner(report)), text), variant, "text-sm", "px-3")


@pytest.mark.parametrize(
    ("status", "variant"),
    [
        ("draft", BadgeT.neutral),
        ("sent", BadgeT.info),
        ("pending", BadgeT.warning),
        ("paid", BadgeT.success),
        ("overdue", BadgeT.error),
        ("cancelled", BadgeT.secondary),
        ("unheard-of", BadgeT.neutral),
    ],
)
def test_invoice_status_pill(status: str, variant: BadgeT) -> None:
    row = InvoiceRow(
        uid="invoice_abc",
        invoice_type="outgoing",
        counterparty="Acme",
        invoice_date="2026-10-01",
        total=10.0,
        status=status,
    )
    xml = to_xml(InvoiceViews._render_invoice_table([row]))
    _assert_badge(_pill(xml, status.upper()), variant, "text-xs")


def test_ai_report_pill() -> None:
    report = EntryReport(
        uid="er_1",
        entity_type=EntityType.ENTRY_REPORT,
        title="AI Feedback",
        user_uid="user_student",
        status=EntityStatus.COMPLETED,
        processor_type=ReportSource.LLM,
        content="Good work.",
        subject_uid="ue_1",
    )
    tokens = _pill(to_xml(render_report_item(report)), "AI")
    _assert_badge(tokens, BadgeT.info, "text-10", "uppercase")


@pytest.mark.parametrize(
    ("direction", "text", "variant"),
    [
        ("aligned", "In sync", BadgeT.success),
        ("user_higher", "You rate yourself higher than the data", BadgeT.warning),
        ("system_higher", "You're doing better than you think", BadgeT.info),
        ("sideways", "—", BadgeT.neutral),
    ],
)
def test_perception_gap_pills(direction: str, text: str, variant: BadgeT) -> None:
    trend = to_xml(render_checkin_trend([{"gap_direction": direction, "perception_gap": 0.2}]))
    _assert_badge(_pill(trend, text), variant)

    result = DualTrackResult[AlignmentLevel](
        entity_uid="principle.integrity",
        entity_type="principle",
        user_level=AlignmentLevel.ALIGNED,
        user_score=1.0,
        user_evidence="",
        user_reflection=None,
        system_level=AlignmentLevel.MOSTLY_ALIGNED,
        system_score=0.75,
        system_evidence=(),
        perception_gap=0.25,
        gap_direction=direction,
        insights=(),
        recommendations=(),
    )
    _assert_badge(_pill(to_xml(gap_card("Alignment", result)), text), variant)


def test_hub_card_count_pill() -> None:
    card = HubCardData(icon="📚", name="Library", href="/library", description="", badge=5)
    _assert_badge(_pill(to_xml(HubCard(card)), "5"), BadgeT.primary, "ml-auto")


def test_submit_form_state_pills() -> None:
    needs = to_xml(_feedback_question(has_exercise=False, teacher_groups=[]))
    _assert_badge(_pill(needs, "Needs an exercise"), BadgeT.warning, "text-10", "uppercase")

    soon = to_xml(_share_question(None, portfolio_mode="coming_soon"))
    _assert_badge(_pill(soon, "Coming soon"), BadgeT.warning, "text-10", "uppercase")
