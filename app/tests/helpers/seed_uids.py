"""The uid of a user a test seeds: generated, read by name.

A user uid is generated — ``user_{16 hex}`` (``core/utils/uid_grammar.py``); the
username is only its ``title`` — and the integration census fails a test that
writes a uid outside the grammar (``tests/integration/_graph_census.py``). A test
names its user and seeds ``seed_user_uid(name)``, the hash of that name: the same
uid every run, so a fixture and the test that reads it agree by name.

An entity seed needs no helper: it takes the authored shape, ``{prefix}.{slug}``
or ``{prefix}.{ns}.{slug}`` (``task.write-report``). Whether it has an owner does
— ``seed_owner``: what a user owns has one, curriculum and curated content none.
"""

from core.models.enums.entity_enums import ContentOrigin, EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.type_hints import UserUID
from core.utils.uid_grammar import hashed_uid

#: The domain labels of what a user owns: every type that is neither curriculum nor
#: curated content (``EntityType.content_origin``). Any other label has no owner.
USER_OWNED_LABELS = frozenset(
    NeoLabel[t.name].value
    for t in EntityType
    if t.content_origin() not in (ContentOrigin.CURRICULUM, ContentOrigin.CURATED)
)


def seed_user_uid(name: str) -> UserUID:
    """The generated uid of the test user called ``name``."""
    return UserUID(hashed_uid("user", "seed", name))


def seed_owner(label: str, owner: UserUID) -> UserUID | None:
    """``owner`` for a node under a label a user owns, ``None`` for any other.

    ``label`` may carry the base label (``Entity:Task``); its last segment decides.
    """
    return owner if label.split(":")[-1] in USER_OWNED_LABELS else None
