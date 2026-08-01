"""
User Service Facade - Coordination Layer
=========================================

Facade coordinating all user-related sub-services.

This service is part of the refactored UserService architecture:
- UserCoreService: CRUD + Auth
- UserProgressRecorderService: Learning progress recording
- UserActivityService: Activity tracking
- UserContextBuilder: Context building
- UserStatsAggregator: Stats aggregation
- UserService: Facade coordinating all sub-services (THIS FILE)

Architecture:
- Thin delegation methods live here; the two logic-bearing clusters are
  mixins (July 2026 decomposition):
  - _AdminLifecycleMixin: admin-gated account lifecycle (role changes,
    listing, deactivation/reactivation, GDPR hard-delete)
  - _ContextPlanningMixin: context building, rich-context cache
    orchestration, profile hub, daily work plan
- Acts as single entry point for user-related operations
"""

from typing import TYPE_CHECKING, Any

from core.models.enums import DualTrackDimension
from core.models.shared.dual_track import DualTrackResult
from core.models.type_hints import EntityUID, UserUID
from core.models.user import User
from core.ports.infrastructure_protocols import (
    EventBusOperations,
    UserOperations,
)

if TYPE_CHECKING:
    from core.ports.service_protocols import SessionInvalidationOperations
    from core.ports.user_context_protocols import UserContextQueryOperations
from core.models.auth.device import Device, PairingCodeIssued
from core.services.user._admin_lifecycle_mixin import _AdminLifecycleMixin
from core.services.user._context_planning_mixin import _ContextPlanningMixin
from core.services.user.device_service import DeviceService
from core.services.user.intelligence import UserContextIntelligenceFactory
from core.services.user.user_activity_service import InvalidationReason, UserActivityService
from core.services.user.user_context_builder import UserContextBuilder
from core.services.user.user_core_service import UserCoreService
from core.services.user.user_progress_recorder_service import UserProgressRecorderService
from core.services.user.user_stats_aggregator import UserStatsAggregator
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class UserService(_AdminLifecycleMixin, _ContextPlanningMixin):
    """
    Facade coordinating all user-related sub-services.

    This service provides a unified interface for user operations while delegating
    to specialized sub-services:
    - UserCoreService: CRUD + Authentication
    - UserProgressRecorderService: Learning progress recording
    - UserActivityService: Activity tracking
    - UserContextBuilder: Context building
    - UserStatsAggregator: Stats aggregation

    Architecture:
    - Thin delegation on the facade; logic-bearing clusters in
      _AdminLifecycleMixin + _ContextPlanningMixin
    - Single entry point for user operations
    - Composed of 5 focused sub-services
    """

    def __init__(
        self,
        user_repo: UserOperations,
        query_executor: "UserContextQueryOperations | None" = None,
        event_bus: EventBusOperations | None = None,
        intelligence_factory: UserContextIntelligenceFactory | None = None,
        metrics_cache=None,
        device_service: DeviceService | None = None,
        session_invalidator: "SessionInvalidationOperations | None" = None,
    ) -> None:
        """
        Initialize facade with all sub-services.

        Args:
            user_repo: Repository implementation for user persistence (protocol-based)
            query_executor: Optional MEGA / CONSOLIDATED query execution for
                cross-domain context building. Built at the composition root and
                injected so neither this service nor UserContextBuilder imports
                the adapter (ADR-044 / SKUEL022 / SKUEL023).
            event_bus: Event bus for publishing domain events (protocol-based)
            intelligence_factory: Factory for creating UserContextIntelligence instances
                                  (wired with all 9 domain relationship services)
            metrics_cache: MetricsCache for performance tracking (optional)
            device_service: Vault-agent device enrollment/revocation (ADR-075).
                Built at the composition root (needs the driver-backed
                DeviceBackend); None only in tests that never touch devices.
            session_invalidator: Server-side session revocation on privilege
                change (role update, deactivation) — forces re-login so no live
                cookie outlives its privileges. Built at the composition root
                (driver-backed SessionBackend); None only in tests that never
                change privileges.

        Raises:
            ValueError: If user_repo is None
        """
        if not user_repo:
            raise ValueError("User repository is required")

        # Initialize all sub-services
        self.core = UserCoreService(user_repo, event_bus=event_bus)
        self.progress = UserProgressRecorderService(user_repo)
        self.activity = UserActivityService(
            user_repo, event_bus=event_bus, metrics_cache=metrics_cache
        )

        # Context builder requires the injected query executor.
        #
        # This is THE single app-wide UserContextBuilder (One Path Forward, July
        # 2026): it must be constructed here because it needs user_service=self
        # for user resolution — a true circular dependency, so it can't be built
        # first and injected. services_bootstrap/compose.py reuses this instance
        # for every consumer (UserContextService, report generators, orchestrators)
        # and _intelligence_hub post-wires zpd_service + ps_engagement_service
        # onto it — never construct a second builder in production.
        self.context_builder: UserContextBuilder | None
        if query_executor is not None:
            self.context_builder = UserContextBuilder(query_executor, user_service=self)
        else:
            self.context_builder = None
            logger.warning(
                "UserService initialized without query_executor - context operations unavailable"
            )

        # Stats aggregator requires context_builder + cross_domain_backend
        # cross_domain_backend is wired post-construction via wire_cross_domain_backend()
        self.stats: UserStatsAggregator | None = None

        # Vault-agent devices (ADR-075) — auth infrastructure behind this facade
        self.devices: DeviceService | None = device_service

        # Session revocation on privilege change — auth infrastructure behind
        # this facade, like devices above
        self.session_invalidator: "SessionInvalidationOperations | None" = session_invalidator

        # Intelligence factory (wired with 13 domain relationship services)
        # Note: Factory is wired post-construction via services_bootstrap.py
        # This is intentional - the factory requires all 13 domain services
        self.intelligence_factory = intelligence_factory

        # Keep repo reference for backward compatibility
        self.repo = user_repo

    def wire_cross_domain_backend(self, cross_domain_backend: Any) -> None:
        """
        Post-construction wiring for cross-domain backend.

        Called from services_bootstrap after CrossDomainBackend is created
        (CrossDomainBackend is created after UserService in the bootstrap sequence).
        """
        if self.context_builder:
            self.stats = UserStatsAggregator(self.core, self.context_builder, cross_domain_backend)
        else:
            logger.warning("Cannot wire stats — context_builder not available")

    # ========================================================================
    # CRUD OPERATIONS (Delegate to UserCoreService)
    # ========================================================================

    async def create_user(
        self,
        username: str,
        email: str | None = None,
        display_name: str | None = None,
        **kwargs: Any,
    ) -> Result[User]:
        """Create a new user with default preferences."""
        return await self.core.create_user(username, email, display_name, **kwargs)

    async def ensure_system_user(self) -> Result[User]:
        """Ensure system user exists for infrastructure operations."""
        return await self.core.ensure_system_user()

    async def get_user(self, user_uid: UserUID) -> Result[User | None]:
        """Get user by UID."""
        return await self.core.get_user(user_uid)

    async def get_user_by_username(self, username: str) -> Result[User | None]:
        """Get user by username."""
        return await self.core.get_user_by_username(username)

    async def update_user(self, user: User) -> Result[User]:
        """Update user information."""
        return await self.core.update_user(user)

    async def update_preferences(
        self, user_uid: UserUID, preferences_update: dict[str, Any]
    ) -> Result[User]:
        """Update user preferences (convenience method).

        Invalidates the cached UserContext immediately on success, then
        REBUILDS it — preference fields (available_minutes_daily → workload
        capacity, preferred_time, learning_level) feed the context, and
        cache-hit-only consumers (SearchRouter._peek_capacity_warnings) never
        build on their own, so invalidation alone would leave search blind to
        the new preferences until another surface warmed the cache (Codex
        #605). The rebuild costs one rich build per Settings save — the same
        price the navbar personal-header pays on every page load. Fail-soft:
        a rebuild failure logs and the save still succeeds (the cache is
        simply cold, as before).
        """
        result = await self.core.update_preferences(user_uid, preferences_update)
        if result.is_ok:
            await self.activity.invalidate_context(
                user_uid, reason=InvalidationReason.PREFERENCES_UPDATED, immediate=True
            )
            rebuild = await self.get_rich_unified_context(user_uid)
            if rebuild.is_error:
                logger.warning(
                    "Context rebuild after preference save failed — cache stays cold",
                    extra={"user_uid": user_uid, "error": str(rebuild.error)},
                )
        return result

    async def append_dual_track_checkin(  # skuel-lint: disable=SKUEL005 -- facade delegation to the safe-by-design store_callback (ADR-030)
        self,
        user_uid: UserUID,
        result: DualTrackResult[Any],
        *,
        dimension: DualTrackDimension,
    ) -> None:
        """Persist a user-level dual-track check-in to the User node (ADR-030).

        Safe-by-design store_callback for the user-level dimensions (Productivity /
        Engagement / Decision Quality). See ``UserCoreService.append_dual_track_checkin``.
        """
        await self.core.append_dual_track_checkin(user_uid, result, dimension=dimension)

    async def append_knowledge_checkin(  # skuel-lint: disable=SKUEL005 -- facade delegation to the safe-by-design store_callback (ADR-030)
        self,
        ku_uid: str,
        result: DualTrackResult[Any],
        *,
        user_uid: UserUID,
    ) -> None:
        """Persist a Knowledge dual-track (mastery) check-in to the User node (ADR-030).

        Safe-by-design store_callback for the per-Ku Knowledge dimension — keyed by
        ``ku_uid`` in the User node's ``knowledge_checkins`` log (a Ku is SHARED, so its
        mastery check-ins live per-user). See ``UserCoreService.append_knowledge_checkin``.
        """
        await self.core.append_knowledge_checkin(ku_uid, result, user_uid=user_uid)

    async def delete_user(
        self,
        user_uid: UserUID,
        reason: str = "",
        deleted_by: UserUID | None = None,
    ) -> Result[bool]:
        """Soft-delete a user: mark status=DELETED, scrub PII, preserve OWNS graph."""
        return await self.core.delete_user(user_uid, reason=reason, deleted_by=deleted_by)

    # ========================================================================
    # AUTHENTICATION (Delegate to UserCoreService)
    # ========================================================================

    async def authenticate(self, username: str, password: str) -> Result[User]:
        """Authenticate user with username and password."""
        return await self.core.authenticate(username, password)

    # ========================================================================
    # VAULT-AGENT DEVICES (Delegate to DeviceService — ADR-075)
    # Devices are auth infrastructure (graph-native, like sessions), so their
    # operations live behind UserService per ADR-075 Decision 2.
    # ========================================================================

    def _require_devices(self) -> Result[DeviceService]:
        """Fail-fast guard: device operations need the wired DeviceService."""
        if self.devices is None:
            return Result.fail(
                Errors.system(
                    "Device service not wired — pass device_service to UserService",
                    operation="devices",
                )
            )
        return Result.ok(self.devices)

    async def create_device_pairing_code(self, user_uid: UserUID) -> Result[PairingCodeIssued]:
        """Mint a one-time device pairing code (10-min TTL, stored hashed)."""
        devices = self._require_devices()
        if devices.is_error:
            return Result.fail(devices)
        return await devices.value.create_pairing_code(user_uid)

    async def enroll_device(
        self, pairing_code: str, pubkey: str, device_name: str
    ) -> Result[Device]:
        """Enroll a vault-agent device — the pairing code is the credential."""
        devices = self._require_devices()
        if devices.is_error:
            return Result.fail(devices)
        return await devices.value.enroll_device(pairing_code, pubkey, device_name)

    async def list_devices(self, user_uid: UserUID) -> Result[list[Device]]:
        """A user's enrolled devices (revoked rows included — audit surface)."""
        devices = self._require_devices()
        if devices.is_error:
            return Result.fail(devices)
        return await devices.value.list_devices(user_uid)

    async def revoke_device(self, user_uid: UserUID, device_uid: str) -> Result[bool]:
        """Stamp ``revoked_at`` on an owned device (False = not found/owned)."""
        devices = self._require_devices()
        if devices.is_error:
            return Result.fail(devices)
        return await devices.value.revoke_device(user_uid, device_uid)

    async def get_device_by_pubkey(self, pubkey: str) -> Result[Device | None]:
        """Resolve an UNREVOKED device by public key (WS handshake path)."""
        devices = self._require_devices()
        if devices.is_error:
            return Result.fail(devices)
        return await devices.value.get_device_by_pubkey(pubkey)

    async def touch_device(self, device_uid: str) -> Result[None]:
        """Stamp ``last_seen_at`` after a successful agent handshake."""
        devices = self._require_devices()
        if devices.is_error:
            return Result.fail(devices)
        return await devices.value.touch_device(device_uid)

    # ========================================================================
    # LEARNING PROGRESS (Delegate to UserProgressRecorderService)
    # ========================================================================

    async def record_knowledge_mastery(
        self,
        user_uid: UserUID,
        knowledge_uid: str,
        mastery_score: float,
        practice_count: int = 1,
        confidence_level: float = 0.8,
        update_progress: bool = True,
    ) -> Result[bool]:
        """Record knowledge mastery using graph relationships."""
        return await self.progress.record_knowledge_mastery(
            user_uid,
            knowledge_uid,
            mastery_score,
            practice_count,
            confidence_level,
            update_progress,
        )

    async def get_user_mastery(self, user_uid: UserUID, concept_uid: str) -> Result[float]:
        """Get user's mastery level for a knowledge concept (0.0-1.0)."""
        return await self.progress.repo.get_user_mastery(user_uid, concept_uid)

    async def record_knowledge_progress(
        self,
        user_uid: UserUID,
        knowledge_uid: str,
        progress: float,
        time_invested_minutes: int = 0,
        difficulty_rating: float | None = None,
    ) -> Result[bool]:
        """Record progress on a knowledge unit."""
        return await self.progress.record_knowledge_progress(
            user_uid, knowledge_uid, progress, time_invested_minutes, difficulty_rating
        )

    async def enroll_in_learning_path(
        self,
        user_uid: UserUID,
        learning_path_uid: str,
        target_completion: str | None = None,
        weekly_time_commitment: int = 300,
        motivation_note: str = "",
    ) -> Result[bool]:
        """Enroll user in a learning path using graph relationships."""
        return await self.progress.enroll_in_learning_path(
            user_uid, learning_path_uid, target_completion, weekly_time_commitment, motivation_note
        )

    async def complete_learning_path(
        self,
        user_uid: UserUID,
        learning_path_uid: str,
        completion_score: float = 1.0,
        feedback_rating: int | None = None,
    ) -> Result[bool]:
        """Mark a learning path as completed."""
        return await self.progress.complete_learning_path(
            user_uid, learning_path_uid, completion_score, feedback_rating
        )

    async def express_interest_in_knowledge(
        self,
        user_uid: UserUID,
        knowledge_uid: str,
        interest_score: float = 0.8,
        interest_source: str = "discovery",
        priority: str = "medium",
        notes: str = "",
    ) -> Result[bool]:
        """Express interest in a knowledge unit."""
        return await self.progress.express_interest_in_knowledge(
            user_uid, knowledge_uid, interest_score, interest_source, priority, notes
        )

    async def bookmark_knowledge(
        self,
        user_uid: UserUID,
        knowledge_uid: str,
        bookmark_reason: str = "reference",
        tags: list | None = None,
        reminder_date: str | None = None,
    ) -> Result[bool]:
        """Bookmark a knowledge unit for later."""
        return await self.progress.bookmark_knowledge(
            user_uid, knowledge_uid, bookmark_reason, tags, reminder_date
        )

    # ========================================================================
    # ACTIVITY TRACKING (Delegate to UserActivityService)
    # ========================================================================

    async def update_user_activity(
        self, user_uid: UserUID, activity_type: str, entity_uid: EntityUID, action: str = "viewed"
    ) -> Result[bool]:
        """Update user's activity state."""
        return await self.activity.update_user_activity(user_uid, activity_type, entity_uid, action)

    async def add_conversation_message(
        self, user_uid: UserUID, role: str, content: str, metadata: dict | None = None
    ) -> Result[bool]:
        """Add message to user's conversation history."""
        return await self.activity.add_conversation_message(user_uid, role, content, metadata)

    async def invalidate_context(  # skuel-lint: disable=SKUEL005 -- facade delegation to the fire-and-forget cache invalidation
        self, user_uid: UserUID, reason: str = "manual", affected_contexts: list[str] | None = None
    ) -> None:
        """Invalidate cached user context when domain events occur."""
        await self.activity.invalidate_context(user_uid, reason, affected_contexts)

    async def get_active_learners(
        self, since_hours: int = 24, limit: int = 100
    ) -> Result[list[User]]:
        """Get users who have been active recently."""
        return await self.activity.get_active_learners(since_hours, limit)


# ============================================================================
# FACTORY FUNCTION (Bootstrap Compatibility)
# ============================================================================


def create_user_service(
    user_repo: UserOperations,
    query_executor: "UserContextQueryOperations | None" = None,
    event_bus: Any | None = None,
    intelligence_factory: UserContextIntelligenceFactory | None = None,
    metrics_cache=None,
    device_service: DeviceService | None = None,
    session_invalidator: "SessionInvalidationOperations | None" = None,
) -> UserService:
    """
    Factory function to create a UserService instance.

    Args:
        user_repo: User repository implementation
        query_executor: Optional MEGA / CONSOLIDATED query execution for cross-domain
            context building (built at the composition root; ADR-044 / SKUEL022).
            Typed against the port rather than ``Any`` so the composition root's
            injection is actually checked — an ``Any`` here launders every
            downstream annotation (SoC arc PR 4's lesson).
        event_bus: Event bus for publishing domain events (optional)
        intelligence_factory: Factory for creating UserContextIntelligence instances
                              (wired with all 9 domain relationship services)
        metrics_cache: MetricsCache for performance tracking (optional)
        device_service: Vault-agent device enrollment/revocation (ADR-075)
        session_invalidator: Session revocation on privilege change (SessionBackend)

    Returns:
        UserService: Configured user service instance (facade pattern)
    """
    return UserService(
        user_repo,
        query_executor,
        event_bus,
        intelligence_factory,
        metrics_cache,
        device_service=device_service,
        session_invalidator=session_invalidator,
    )
