"""A stand-in ownership verifier for driving the lateral service's writers.

Every lateral write carries an ``OwnershipVerifier``. A test whose subject is
not access (the edge's stamp, its row semantics, the shadow-uid guard) passes
this one, which admits every uid but the ones it names, so what answers is the
behaviour under test.
"""

from __future__ import annotations

from core.models.type_hints import UserUID
from core.utils.result_simplified import Errors, Result

#: The caller every such write names.
CALLER = UserUID("user_lateral_caller")


class AdmitsAllBut:
    """Admits every uid but the ones it names — a missing uid included."""

    def __init__(self, *refused: str) -> None:
        self.refused = set(refused)

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[str]:
        if uid in self.refused:
            return Result.fail(Errors.not_found("Task"))
        return Result.ok(uid)


#: A verifier that refuses nothing.
ADMITS_ALL = AdmitsAllBut()
