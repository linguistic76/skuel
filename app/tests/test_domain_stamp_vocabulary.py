"""
Guard: every search-result ``_domain`` producer stamps ONE vocabulary.
=====================================================================

PR #536 had to normalize three ``_domain`` vocabularies at the render boundary
(EntityType values, Services attr names, and lowered entity labels). This arc
deleted the root cause: every SearchRouter producer now stamps
``EntityType.value``.

The three producers:
- ``SearchOperationsMixin.graph_aware_faceted_search`` → ``self.entity_type_value``
  (resolves to ``DomainConfig.get_entity_type_value()``)
- ``SearchRouter._cross_domain_search`` text sweep → ``entity_type.value``
- ``SearchRouter._simple_domain_search`` / ``_faceted_sweep`` → ``entity_type.value``

If ``DomainConfig.get_entity_type_value()`` equals ``entity_type.value`` for
every searchable domain, the mixin producer agrees with the sweep producers.
This test pins that agreement so a producer can't silently drift back.
"""

import pytest

from core.models.entity_types import ENTITY_TYPE_CLASS_MAP
from core.models.enums.entity_enums import EntityType
from core.services.domain_config import DomainConfig

# The 12 searchable domains (SearchRouter); Ku joined as the 12th (#536).
SEARCHABLE_DOMAINS = [
    EntityType.TASK,
    EntityType.GOAL,
    EntityType.HABIT,
    EntityType.EVENT,
    EntityType.CHOICE,
    EntityType.PRINCIPLE,
    EntityType.KU,
    EntityType.PATH_STEP,
    EntityType.LEARNING_PATH,
    EntityType.EXERCISE,
    EntityType.REVISED_EXERCISE,
    EntityType.USER_ENTRY,
]


@pytest.mark.parametrize("entity_type", SEARCHABLE_DOMAINS)
def test_config_stamps_entity_type_value(entity_type: EntityType) -> None:
    """The mixin producer resolves the same string the sweep producers stamp."""
    model_class = ENTITY_TYPE_CLASS_MAP[entity_type]
    config = DomainConfig(
        dto_class=model_class,  # unused by get_entity_type_value
        model_class=model_class,
        search_fields=("title",),
    )
    # Mixin producer vocabulary == cross-domain / faceted producer vocabulary.
    assert config.get_entity_type_value() == entity_type.value


def test_unmapped_model_class_raises() -> None:
    """A model_class outside ENTITY_TYPE_CLASS_MAP fails loud, not silent."""

    class NotAnEntity:
        pass

    config = DomainConfig(
        dto_class=NotAnEntity,
        model_class=NotAnEntity,
        search_fields=("title",),
    )
    with pytest.raises(ValueError, match="ENTITY_TYPE_CLASS_MAP"):
        config.get_entity_type_value()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
