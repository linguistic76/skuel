"""A Ku carries the complexity its curriculum file authored, or ``None``.

A Ku reaches a model through two converters: the backend's type-hint mapper
(``from_neo4j_node``) and the DTO path (``KuDTO.from_dict`` → ``Ku.from_dto``). Each
must turn a stored ``complexity`` into a ``KuComplexity`` and leave an unauthored one
``None`` (never a stand-in such as MEDIUM). A value outside the vocabulary is never
read as absent: both paths refuse it.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.persistence.neo4j.neo4j_mapper import UnreadableStoredValueError, from_neo4j_node
from core.models.enums import KuComplexity
from core.models.ku.ku import Ku
from core.models.ku.ku_dto import KuDTO

_ABSENT = object()


def _node(**properties: Any) -> dict[str, Any]:  # boundary: neo4j node properties
    return {"uid": "ku.test.complexity", "title": "Complexity", "entity_type": "ku", **properties}


class TestMapperPath:
    def test_a_stored_complexity_reads_as_the_enum(self) -> None:
        ku = from_neo4j_node(_node(complexity="basic"), Ku)

        assert getattr(ku, "complexity", _ABSENT) is KuComplexity.BASIC

    def test_an_unauthored_complexity_reads_as_none(self) -> None:
        ku = from_neo4j_node(_node(), Ku)

        assert getattr(ku, "complexity", _ABSENT) is None

    def test_a_value_outside_the_vocabulary_is_refused(self) -> None:
        with pytest.raises(UnreadableStoredValueError) as refused:
            from_neo4j_node(_node(complexity="bogus"), Ku)

        assert (refused.value.uid, refused.value.field) == ("ku.test.complexity", "complexity")


class TestDtoPath:
    def test_from_dict_parses_the_enum_and_the_model_keeps_it(self) -> None:
        dto = KuDTO.from_dict(_node(complexity="advanced"))

        assert getattr(dto, "complexity", _ABSENT) is KuComplexity.ADVANCED
        assert getattr(Ku.from_dto(dto), "complexity", _ABSENT) is KuComplexity.ADVANCED

    def test_an_unauthored_complexity_stays_none_through_the_dto(self) -> None:
        dto = KuDTO.from_dict(_node())

        assert getattr(dto, "complexity", _ABSENT) is None
        assert getattr(Ku.from_dto(dto), "complexity", _ABSENT) is None

    def test_a_value_outside_the_vocabulary_is_refused(self) -> None:
        with pytest.raises(ValueError):
            KuDTO.from_dict(_node(complexity="bogus"))

    def test_round_trip_model_to_dict_and_back(self) -> None:
        ku = from_neo4j_node(_node(complexity="medium"), Ku)

        as_dict = ku.to_dto().to_dict()
        assert as_dict.get("complexity", _ABSENT) == "medium"

        back = Ku.from_dto(KuDTO.from_dict(as_dict))
        assert getattr(back, "complexity", _ABSENT) is KuComplexity.MEDIUM

    def test_update_from_parses_complexity(self) -> None:
        dto = KuDTO.from_dict(_node())

        dto.update_from({"complexity": "basic"})

        assert getattr(dto, "complexity", _ABSENT) is KuComplexity.BASIC
