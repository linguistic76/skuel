"""
Whose Zone — the app default, a user's choice, the request's zone
=================================================================

A calendar value — which day it is, how a moment reads — belongs to a zone
(ADR-089 §3). The zone is the user's own choice (``UserPreferences.timezone``,
an IANA name), else the app default ``SKUEL_TIMEZONE``, which also serves
system work that acts for no user.

- **In a request:** ``AuthContextMiddleware`` (adapters/inbound/auth/
  context_middleware.py) resolves the signed-in user's zone once per request,
  from the choice it reads out of the graph in the session-validation round
  trip, and sets ``current_zone_var``; ``current_zone()`` reads it back. The
  choice is never mirrored into the cookie session, so a change in Settings
  reaches every device on its next request.
- **Outside a request:** no middleware has run, and ``current_zone()`` is the
  app default. Work done for a named user (a vault sync for the vault's owner,
  a report generated for a user) resolves that user's zone explicitly
  (``UserService.get_user_zone``).
- **A zone name** is valid when zoneinfo lists it (``zone_names()``). The
  Settings door, the request model and the DTO parse refuse any other name
  (``validated_zone_name``); a stored choice is resolved leniently
  (``zone_for``), so no request fails over a preference.

The helpers that take a zone — today in it, now in it, the day of an instant
in it, a day's UTC bounds in it — live in ``core/utils/timestamp_helpers.py``.

Lives in ``core/utils`` for the reason ``auth_context`` does: the middleware
(adapters → core) writes the context, and readers anywhere in core read it.

See: /docs/decisions/ADR-089-instants-utc-days-in-a-zone.md
"""

from __future__ import annotations

import os
import zoneinfo
from contextvars import ContextVar
from functools import cache
from typing import Final
from zoneinfo import ZoneInfo

from core.utils.logging import get_logger

logger = get_logger("skuel.zone")

#: The environment variable naming the app default zone.
TIMEZONE_ENV_VAR: Final = "SKUEL_TIMEZONE"

#: The app default when ``SKUEL_TIMEZONE`` is unset or blank.
DEFAULT_TIMEZONE: Final = "America/Vancouver"

# ``localtime`` is the host's own zone under another name, listed by zoneinfo
# wherever the host's zone directory carries the link. It is not an IANA name,
# and a choice naming it would follow whichever machine runs the app.
_HOST_ALIASES: Final = frozenset({"localtime"})


@cache
def zone_names() -> frozenset[str]:
    """Every name a zone choice may hold: the IANA zones zoneinfo can load.

    ``zoneinfo.available_timezones()`` walks the zone directories, so the set is
    built once per process.
    """
    return frozenset(zoneinfo.available_timezones() - _HOST_ALIASES)


def validated_zone_name(value: str | None) -> str | None:
    """A zone choice as stored: None for no choice, else a name zoneinfo lists.

    A blank value is no choice — it follows the app default. Surrounding
    whitespace is dropped.

    Raises:
        ValueError: the value names no zone zoneinfo lists.
    """
    if value is None:
        return None
    name = value.strip()
    if not name:
        return None
    if name not in zone_names():
        raise ValueError(
            f"Unknown time zone {name!r}: expected an IANA zone name such as 'Asia/Bangkok'"
        )
    return name


def configured_zone_name() -> str:
    """The app default zone's name: ``SKUEL_TIMEZONE``, or ``DEFAULT_TIMEZONE`` when unset or blank.

    Read as configured, not validated: the config validation refuses to boot on
    a name zoneinfo does not list (``core/config/validation.py``), and
    ``default_zone()`` refuses to build one.
    """
    return os.getenv(TIMEZONE_ENV_VAR, "").strip() or DEFAULT_TIMEZONE


def default_zone() -> ZoneInfo:
    """The app default zone — the zone of anyone who has not chosen one.

    Raises:
        ValueError: ``SKUEL_TIMEZONE`` names no zone zoneinfo lists.
    """
    name = configured_zone_name()
    if name not in zone_names():
        raise ValueError(
            f"{TIMEZONE_ENV_VAR}={name!r} is not an IANA time zone name "
            "(for example America/Vancouver or Asia/Bangkok)"
        )
    return ZoneInfo(name)


def zone_for(choice: str | None) -> ZoneInfo:
    """The zone a user's stored choice names; the app default when there is none.

    A stored name zoneinfo does not list reads as no choice, with a warning:
    the doors refuse such a name, and resolving one must never fail a request.
    """
    if choice:
        if choice in zone_names():
            return ZoneInfo(choice)
        logger.warning(
            "Stored time zone %r is not an IANA zone name; following the app default", choice
        )
    return default_zone()


# Scope is per request/task — set (and reset) by AuthContextMiddleware.dispatch.
current_zone_var: ContextVar[ZoneInfo | None] = ContextVar("current_zone_var", default=None)


def current_zone() -> ZoneInfo:
    """The zone of the in-flight request; the app default outside one."""
    return current_zone_var.get() or default_zone()


__all__ = [
    "DEFAULT_TIMEZONE",
    "TIMEZONE_ENV_VAR",
    "configured_zone_name",
    "current_zone",
    "current_zone_var",
    "default_zone",
    "validated_zone_name",
    "zone_for",
    "zone_names",
]
