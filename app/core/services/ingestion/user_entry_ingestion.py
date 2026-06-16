"""
UserEntry ingestion helper — bridges YAML files into ``UserEntryService``.

`/upload` and `/submit` are the two front-ends on the same UserEntry creation
pipeline. This module is the bridge for the YAML-driven side: it validates
the per-file frontmatter (pipeline + audience), expands the
``audience: teachers`` default into explicit group UIDs via the
``AudienceResolver``, builds a ``UserEntryCreateRequest``, and delegates to
``UserEntryService.create_entry()`` so every downstream step (Interaction
audit, TRANSFORMS edges, sharing fan-out, compensation delete) is identical
to the form path.

See: /home/mike/.claude/plans/upload-userentry-integration.md
See: /docs/decisions/ADR-054-user-entry-unified-submissions.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.models.enums.metadata_enums import Visibility
from core.models.enums.pipeline import Pipeline
from core.models.enums.user_enums import UserRole
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from pathlib import Path

    from core.services.user_entry.audience_resolver import AudienceResolver
    from core.services.user_entry.user_entry_service import UserEntryService
    from core.services.user_service import UserService

logger = get_logger("skuel.services.ingestion.user_entry")

# /upload is YAML-only — audio pipelines need actual audio bytes, not YAML.
_AUDIO_PIPELINES: frozenset[Pipeline] = frozenset(
    {Pipeline.TRANSCRIBE, Pipeline.TRANSCRIBE_AND_STRUCTURE}
)


@dataclass(frozen=True)
class _AudienceSpec:
    """Parsed `audience:` field. Internal to this module."""

    kind: str  # "teachers" | "group" | "public" | "private"
    group_uid: str | None = None


def _parse_audience(raw: Any) -> Result[_AudienceSpec]:
    """Parse the YAML ``audience:`` field. Defaults to ``teachers`` when None."""
    if raw is None:
        return Result.ok(_AudienceSpec(kind="teachers"))
    if not isinstance(raw, str):
        return Result.fail(
            Errors.validation(
                f"audience must be a string, got {type(raw).__name__}",
                field="audience",
            )
        )
    value = raw.strip().lower()
    if value == "teachers":
        return Result.ok(_AudienceSpec(kind="teachers"))
    if value == "private":
        return Result.ok(_AudienceSpec(kind="private"))
    if value == "public":
        return Result.ok(_AudienceSpec(kind="public"))
    if value.startswith("group:"):
        group_uid = value[len("group:") :].strip()
        if not group_uid:
            return Result.fail(
                Errors.validation(
                    "audience 'group:' must include a group UID (e.g., group:group_abc)",
                    field="audience",
                )
            )
        return Result.ok(_AudienceSpec(kind="group", group_uid=group_uid))
    return Result.fail(
        Errors.validation(
            f"Unknown audience '{raw}'. Expected one of: teachers, group:<uid>, public, private.",
            field="audience",
        )
    )


def _parse_pipeline(raw: Any, file_name: str) -> Result[Pipeline]:
    """Parse and validate the ``pipeline:`` field for a UserEntry YAML."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return Result.fail(
            Errors.validation(
                f"UserEntry YAML {file_name} is missing required 'pipeline:' field. "
                "Set one of: none, teacher_review, llm_summary.",
                field="pipeline",
            )
        )
    if not isinstance(raw, str):
        return Result.fail(
            Errors.validation(
                f"pipeline must be a string, got {type(raw).__name__}",
                field="pipeline",
            )
        )
    value = raw.strip().lower()
    try:
        pipeline = Pipeline(value)
    except ValueError:
        return Result.fail(
            Errors.validation(
                f"Unknown pipeline '{raw}'. Expected one of: "
                f"{', '.join(p.value for p in Pipeline)}.",
                field="pipeline",
            )
        )
    if pipeline in _AUDIO_PIPELINES:
        return Result.fail(
            Errors.validation(
                f"pipeline='{pipeline.value}' is an audio pipeline and requires "
                "the audio-upload flow, not /upload (which is YAML-only).",
                field="pipeline",
            )
        )
    return Result.ok(pipeline)


async def build_user_entry_request(
    data: dict[str, Any],
    file_path: Path,
    user_uid: UserUID,
    audience_resolver: AudienceResolver,
    user_service: UserService | None = None,
    body: str | None = None,
) -> Result[UserEntryCreateRequest]:
    """Validate YAML + build a ``UserEntryCreateRequest`` ready for the service.

    Expands ``audience: teachers`` (the default) into explicit group UIDs by
    looking up the user's group memberships through the resolver. A user who
    is in no groups gets an empty share list — the entry is persisted but
    private (no compensation delete in that branch, since the absence of
    teachers is a state-of-the-world fact, not a sharing failure).

    ``audience: public`` is gated on ``UserRole.TEACHER`` — a REGISTERED user
    cannot publish portfolio-visible content through YAML upload. The role is
    resolved via ``user_service``; when unavailable the public audience is
    rejected (fail-closed).
    """
    pipeline_result = _parse_pipeline(data.get("pipeline"), file_path.name)
    if pipeline_result.is_error:
        return Result.fail(pipeline_result)
    pipeline = pipeline_result.value

    audience_result = _parse_audience(data.get("audience"))
    if audience_result.is_error:
        return Result.fail(audience_result)
    audience = audience_result.value

    share_with_groups: list[str] = []
    visibility: Visibility | None = None

    if audience.kind == "teachers":
        # Expand to the user's group memberships. Empty list means the user
        # has no groups; entry persists privately with no shares.
        share_with_groups = await audience_resolver.resolve_default_teachers(user_uid)
    elif audience.kind == "group":
        assert audience.group_uid is not None  # parser guarantees this
        share_with_groups = [audience.group_uid]
    elif audience.kind == "public":
        role_check = await _require_teacher_for_public(user_uid, user_service)
        if role_check.is_error:
            return Result.fail(role_check)
        visibility = Visibility.PUBLIC
    # "private" → no shares, default visibility

    # Authorization guard on raw UID references before the request is built.
    # Prevents YAML from smuggling arbitrary exercise / predecessor UIDs that
    # the uploader has no legitimate relationship to.
    fulfills_exercise_uid = data.get("fulfills_exercise_uid")
    transforms_of_uid = data.get("transforms_of_uid")
    refs_check = await audience_resolver.validate_references(
        user_uid=user_uid,
        fulfills_exercise_uid=fulfills_exercise_uid,
        transforms_of_uid=transforms_of_uid,
    )
    if refs_check.is_error:
        return Result.fail(refs_check)

    title = data.get("title") or data.get("name") or file_path.stem.replace("-", " ").title()
    tags_raw = data.get("tags") or []
    tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        return Result.fail(
            Errors.validation(
                f"metadata must be a mapping, got {type(metadata).__name__}",
                field="metadata",
            )
        )

    # Markdown body capture: a periodic note carries its checkbox lines / prose
    # in the body, not a `content:` field. Explicit `content:` wins; otherwise
    # the parsed body becomes the entry content (so EXTRACT_ACTIVITIES has the
    # `- [ ]` lines to work with downstream).
    content = data.get("content") or body
    request = UserEntryCreateRequest(
        uid=data.get("uid"),
        title=str(title),
        content=content,
        tags=tags,
        metadata=dict(metadata),
        pipeline=pipeline,
        instructions=data.get("instructions"),
        fulfills_exercise_uid=fulfills_exercise_uid,
        transforms_of_uid=transforms_of_uid,
        share_with_groups=share_with_groups,
        share_with_users=[],
        visibility=visibility,
    )

    # Pre-validate the assembled request so we surface audience-policy
    # failures (e.g. teacher_review with no resolvable audience for a
    # student in zero groups) before the service runs.
    validate_result = audience_resolver.validate(request)
    if validate_result.is_error:
        return Result.fail(validate_result)

    return Result.ok(request)


async def _require_teacher_for_public(
    user_uid: UserUID,
    user_service: UserService | None,
) -> Result[None]:
    """Reject ``audience: public`` unless the caller is TEACHER or higher."""
    if user_service is None:
        return Result.fail(
            Errors.forbidden(
                action="publish public UserEntry",
                reason=(
                    "'audience: public' requires TEACHER role but role cannot be "
                    "resolved (user_service unavailable)."
                ),
                required_role=UserRole.TEACHER.value,
            )
        )
    user_result = await user_service.get_user(user_uid)
    if user_result.is_error:
        return Result.fail(user_result)
    user = user_result.value
    if user is None or not user.has_permission(UserRole.TEACHER):
        return Result.fail(
            Errors.forbidden(
                action="publish public UserEntry",
                reason=(
                    "'audience: public' requires TEACHER role; this user does not "
                    "have permission to publish."
                ),
                required_role=UserRole.TEACHER.value,
            )
        )
    return Result.ok(None)


async def ingest_user_entry(
    data: dict[str, Any],
    file_path: Path,
    user_uid: UserUID,
    user_entry_service: UserEntryService,
    user_service: UserService | None = None,
    body: str | None = None,
) -> Result[dict[str, Any]]:
    """Ingest a single UserEntry through ``UserEntryService.create_entry()``.

    ``body`` is the parsed markdown body (None for YAML files); it becomes the
    entry ``content`` when no explicit ``content:`` field is present, so a
    periodic note's checkbox lines survive ingestion.

    Returns the standard ingestion result dict (uid, title, entity_type, ...)
    so callers don't need to reach into ``ShareOutcome`` to format a response.
    """
    request_result = await build_user_entry_request(
        data=data,
        file_path=file_path,
        user_uid=user_uid,
        audience_resolver=user_entry_service.audience_resolver,
        user_service=user_service,
        body=body,
    )
    if request_result.is_error:
        return Result.fail(request_result)

    create_result = await user_entry_service.create_entry(
        request=request_result.value,
        user_uid=user_uid,
    )
    if create_result.is_error:
        return Result.fail(create_result)

    entry, outcome = create_result.value
    logger.info(
        f"Ingested user_entry: {entry.uid} (pipeline={entry.pipeline.value}, "
        f"shared_groups={len(outcome.shared_groups)})"
    )

    return Result.ok(
        {
            "uid": entry.uid,
            "title": entry.title,
            "entity_type": "user_entry",
            "format": "yaml",
            "success": True,
            "nodes_created": 1,
            "nodes_updated": 0,
            "relationships_created": (
                len(outcome.shared_groups)
                + len(outcome.shared_users)
                + (1 if request_result.value.fulfills_exercise_uid else 0)
            ),
            "chunks_generated": False,
            "share_outcome": outcome.to_payload(),
        }
    )


__all__ = ["build_user_entry_request", "ingest_user_entry"]
