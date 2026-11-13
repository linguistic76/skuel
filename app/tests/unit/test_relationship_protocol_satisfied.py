"""``UnifiedRelationshipService`` has every member ``BaseRelationshipOperations`` declares.

Two services take a domain's relationship service under the protocol and are handed
``facade.relationships`` by the composition root. A member the protocol declares
under other parameter names than the service's is one no caller could use through
the protocol, and it makes the service fail the protocol under the type checker.
"""

import inspect

from core.ports.domain_protocols import BaseRelationshipOperations
from core.services.relationships import UnifiedRelationshipService


def _protocol_members(protocol: type) -> dict[str, list[str]]:
    return {
        name: list(inspect.signature(member).parameters)
        for name, member in vars(protocol).items()
        if inspect.isfunction(member) and not name.startswith("_")
    }


def mismatches(protocol: type, implementer: type) -> list[str]:
    """Each protocol member the implementer lacks or declares under other parameters."""
    wrong = []
    for name, parameters in _protocol_members(protocol).items():
        member = getattr(implementer, name, None)
        if member is None:
            wrong.append(f"{name}: missing")
        elif list(inspect.signature(member).parameters) != parameters:
            wrong.append(f"{name}: {list(inspect.signature(member).parameters)}")
    return wrong


def test_the_service_has_every_protocol_member_under_the_same_parameters() -> None:
    assert _protocol_members(BaseRelationshipOperations)
    assert mismatches(BaseRelationshipOperations, UnifiedRelationshipService) == []


def test_a_missing_and_a_renamed_member_are_both_named() -> None:
    """The control: the comparison refuses a member it cannot match."""

    class Renamed:
        async def get_related_uids(self, key: str, uid: str) -> None: ...

    class Empty: ...

    assert mismatches(BaseRelationshipOperations, Renamed) == [
        "get_related_uids: ['self', 'key', 'uid']"
    ]
    assert mismatches(BaseRelationshipOperations, Empty) == ["get_related_uids: missing"]
