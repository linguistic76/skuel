"""The uid of a user a test seeds: generated, read by name.

A user uid is generated — ``user_{16 hex}`` (``core/utils/uid_grammar.py``); the
username is only its ``title`` — and the integration census fails a test that
writes a uid outside the grammar (``tests/integration/_uid_census.py``). A test
names its user and seeds ``seed_user_uid(name)``, the hash of that name: the same
uid every run, so a fixture and the test that reads it agree by name.

An entity seed needs no helper: it takes the authored shape, ``{prefix}.{slug}``
or ``{prefix}.{ns}.{slug}`` (``task.write-report``).
"""

from core.models.type_hints import UserUID
from core.utils.uid_grammar import hashed_uid


def seed_user_uid(name: str) -> UserUID:
    """The generated uid of the test user called ``name``."""
    return UserUID(hashed_uid("user", "seed", name))
