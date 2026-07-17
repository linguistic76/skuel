"""Every EntityType must have full status-map coverage.

EntityType.INTERACTION was present in _DEFAULT_STATUS_BY_TYPE but missing
from _VALID_STATUSES_BY_TYPE, so ``valid_statuses()`` (and type-aware
``can_transition_to()``) raised KeyError for Interaction entities — found
during the ENUM_ARCHITECTURE doc currency pass. This guard keeps the two
maps in lockstep with the enum: a new EntityType value fails here until
both maps cover it.
"""

from core.models.enums import EntityType


class TestEntityTypeStatusCoverage:
    def test_every_entity_type_has_valid_statuses(self) -> None:
        for et in EntityType:
            statuses = et.valid_statuses()  # KeyError = missing map entry
            assert statuses, f"{et.value} has an empty valid-status set"

    def test_every_default_status_is_valid(self) -> None:
        for et in EntityType:
            assert et.default_status() in et.valid_statuses(), (
                f"{et.value}: default {et.default_status().value} not in its valid_statuses()"
            )
