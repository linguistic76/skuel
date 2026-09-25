"""
AudienceSpec — the one audience vocabulary (ADR-088).

Every door that creates a ``UserEntry`` — the ``/submit`` form, the JSON API
and the vault's ``audience:`` frontmatter — speaks this vocabulary and
nothing else. ``AudienceSpec.parse`` is the one parser; ``AudienceResolver``
(``core/services/user_entry/audience_resolver.py``) is the one applier.

| Value                 | Meaning                                                       |
|-----------------------|---------------------------------------------------------------|
| ``teachers``          | a feedback request to all my teachers (SUBMITTED_TO_GROUP)    |
| ``teacher:<group>``   | a feedback request to one group's teachers                    |
| ``group:<uid>``       | a share with every member and owner of a group (SHARED_WITH_GROUP) |
| ``user:<username>``   | a share with one co-member (SHARES_WITH)                      |
| ``public``            | portfolio publication (``visibility = public``, TEACHER-gated) |
| ``private``           | no links — exclusive: it combines with no other value         |

Lists are accepted. Keyword tokens are matched case-insensitively; the
payload after the colon is preserved verbatim, because a username matches
``User.title`` exactly.

See: /docs/decisions/ADR-088-submit-and-share.md § The one audience vocabulary
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.utils.result_simplified import Errors, Result

TEACHERS = "teachers"
PUBLIC = "public"
PRIVATE = "private"
TEACHER_PREFIX = "teacher:"
GROUP_PREFIX = "group:"
USER_PREFIX = "user:"

VOCABULARY = (
    TEACHERS,
    f"{TEACHER_PREFIX}<group_uid>",
    f"{GROUP_PREFIX}<uid>",
    f"{USER_PREFIX}<username>",
    PUBLIC,
    PRIVATE,
)

_FIELD = "audience"


@dataclass(frozen=True)
class AudienceSpec:
    """A parsed audience declaration — what the author asked for, before any lookup.

    An empty spec (``AudienceSpec()``) is an absent declaration. It is not
    ``private``: ``private`` is an explicit "no links", while an absent
    declaration lets the pipeline supply its default (``teachers`` on
    ``TEACHER_REVIEW``; nothing elsewhere).
    """

    teachers: bool = False
    teacher_groups: tuple[str, ...] = ()
    share_groups: tuple[str, ...] = ()
    share_users: tuple[str, ...] = ()
    public: bool = False
    private: bool = False

    # ------------------------------------------------------------------
    # Derived views
    # ------------------------------------------------------------------

    @property
    def is_empty(self) -> bool:
        """No value was declared at all."""
        return self == AudienceSpec()

    @property
    def names_feedback_target(self) -> bool:
        """``teachers`` or a ``teacher:<group_uid>`` — a Submit (ADR-088 §1)."""
        return self.teachers or bool(self.teacher_groups)

    @property
    def names_share(self) -> bool:
        """``group:``, ``user:`` or ``public`` — a Share (ADR-088 §1)."""
        return bool(self.share_groups) or bool(self.share_users) or self.public

    @property
    def group_targets(self) -> tuple[str, ...]:
        """Every group uid the spec names, whichever verb — for a reachability check."""
        seen: dict[str, None] = {}
        for uid in (*self.teacher_groups, *self.share_groups):
            seen.setdefault(uid, None)
        return tuple(seen)

    def values(self) -> tuple[str, ...]:
        """The spec re-emitted in the vocabulary (for messages, logs and payloads)."""
        out: list[str] = []
        if self.private:
            out.append(PRIVATE)
        if self.teachers:
            out.append(TEACHERS)
        out.extend(f"{TEACHER_PREFIX}{g}" for g in self.teacher_groups)
        out.extend(f"{GROUP_PREFIX}{g}" for g in self.share_groups)
        out.extend(f"{USER_PREFIX}{u}" for u in self.share_users)
        if self.public:
            out.append(PUBLIC)
        return tuple(out)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @classmethod
    def parse(cls, raw: Any) -> Result[AudienceSpec]:
        """Parse a declaration: ``None``, one value, or a list of values.

        Every failure is a validation error on the ``audience`` field. The
        one combination rule: ``private`` is exclusive — a list that pairs it
        with any other value is an error, never a silent choice of which wins.
        """
        if raw is None:
            return Result.ok(cls())
        if isinstance(raw, AudienceSpec):
            return Result.ok(raw)
        if isinstance(raw, str):
            items: list[Any] = [raw]
        elif isinstance(raw, (list, tuple)):
            items = list(raw)
        else:
            return Result.fail(
                Errors.validation(
                    f"audience must be a value or a list of values, got {type(raw).__name__}",
                    field=_FIELD,
                )
            )

        teachers = False
        public = False
        private = False
        teacher_groups: dict[str, None] = {}
        share_groups: dict[str, None] = {}
        share_users: dict[str, None] = {}

        for item in items:
            if not isinstance(item, str):
                return Result.fail(
                    Errors.validation(
                        f"audience values must be strings, got {type(item).__name__}",
                        field=_FIELD,
                    )
                )
            value = item.strip()
            if not value:
                continue
            keyword = value.lower()
            if keyword == TEACHERS:
                teachers = True
            elif keyword == PUBLIC:
                public = True
            elif keyword == PRIVATE:
                private = True
            elif keyword.startswith(TEACHER_PREFIX):
                payload = _payload(value, TEACHER_PREFIX)
                if payload.is_error:
                    return Result.fail(payload)
                teacher_groups.setdefault(payload.value, None)
            elif keyword.startswith(GROUP_PREFIX):
                payload = _payload(value, GROUP_PREFIX)
                if payload.is_error:
                    return Result.fail(payload)
                share_groups.setdefault(payload.value, None)
            elif keyword.startswith(USER_PREFIX):
                payload = _payload(value, USER_PREFIX)
                if payload.is_error:
                    return Result.fail(payload)
                share_users.setdefault(payload.value, None)
            else:
                return Result.fail(
                    Errors.validation(
                        f"Unknown audience '{value}'. Expected one of: {', '.join(VOCABULARY)}.",
                        field=_FIELD,
                    )
                )

        spec = cls(
            teachers=teachers,
            teacher_groups=tuple(teacher_groups),
            share_groups=tuple(share_groups),
            share_users=tuple(share_users),
            public=public,
            private=private,
        )
        if private and spec != cls(private=True):
            return Result.fail(
                Errors.validation(
                    "audience 'private' combines with no other value "
                    f"(got {', '.join(spec.values())})",
                    field=_FIELD,
                )
            )
        return Result.ok(spec)


def _payload(value: str, prefix: str) -> Result[str]:
    """The part after ``prefix`` — verbatim, never empty."""
    payload = value[len(prefix) :].strip()
    if not payload:
        return Result.fail(
            Errors.validation(
                f"audience '{prefix}' must name a target (e.g. {prefix}abc)",
                field=_FIELD,
            )
        )
    return Result.ok(payload)


__all__ = [
    "GROUP_PREFIX",
    "PRIVATE",
    "PUBLIC",
    "TEACHERS",
    "TEACHER_PREFIX",
    "USER_PREFIX",
    "VOCABULARY",
    "AudienceSpec",
]
