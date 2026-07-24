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
- Delegates all operations to appropriate sub-services
- Maintains backward compatibility with original UserService
- Acts as single entry point for user-related operations
- Zero business logic (pure delegation)
"""

from typing import TYPE_CHECKING, Any

from core.models.enums import DualTrackDimension, UserRole
from core.models.shared.dual_track import DualTrackResult
from core.models.type_hints import EntityUID, UserUID
from core.models.user import User
from core.ports.infrastructure_protocols import (
    EventBusOperations,
    UserOperations,
)

if TYPE_CHECKING:
    from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor
    from core.ports.service_protocols import SessionInvalidationOperations
from core.models.auth.device import Device, PairingCodeIssued
from core.models.context_types import DailyWorkPlan
from core.services.user import UserContext
from core.services.user.device_service import DeviceService
from core.services.user.intelligence import UserContextIntelligenceFactory
from core.services.user.unified_user_context import RichUserContext
from core.services.user.user_activity_service import InvalidationReason, UserActivityService
from core.services.user.user_context_builder import UserContextBuilder
from core.services.user.user_core_service import UserCoreService
from core.services.user.user_progress_recorder_service import UserProgressRecorderService
from core.services.user.user_stats_aggregator import UserStatsAggregator
from core.services.user_stats_types import ProfileHubData
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


class UserService:
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
    - Zero business logic (pure delegation)
    - Maintains backward compatibility
    - Single entry point for user operations
    - Composed of 5 focused sub-services
    """

    def __init__(
        self,
        user_repo: UserOperations,
        query_executor: "UserContextQueryExecutor | None" = None,
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
            query_executor: Optional UserContextQueryExecutor for cross-domain context
                building. Built at the composition root and injected so neither this
                service nor UserContextBuilder imports the adapter (ADR-044/SKUEL022).
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

    async def get_user_context(self, user_uid: UserUID) -> Result[UserContext]:
        """
        Get UserContext for a user (public API for Askesis and other services).

        This method exposes the internal _build_user_context() functionality
        for services that need rich user context (like Askesis AI assistant).

        Args:
            user_uid: User's unique identifier

        Returns:
            Result containing UserContext with all domain activity data

        Note:
            For statistical views, use get_profile_hub_data() instead.
            For rich entity details, use get_rich_unified_context() instead.
        """
        # Get user first
        user_result = await self.get_user(user_uid)
        if user_result.is_error:
            return Result.fail(user_result)

        if not user_result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))

        user = user_result.value

        # Build and return UserContext
        return await self._build_user_context(user_uid, user)

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

    async def hard_delete_user(
        self,
        target_user_uid: UserUID,
        admin_user_uid: UserUID,
        reason: str,
    ) -> Result[int]:
        """
        Hard-delete a user and every OWNS-linked entity (GDPR erasure, ADMIN only).

        Args:
            target_user_uid: User to erase.
            admin_user_uid: Admin initiating erasure (audit trail).
            reason: Free-form reason (required for audit).

        Returns:
            Result[int]: Count of deleted nodes (user + owned entities), or error.
        """
        admin_result = await self.get_user(admin_user_uid)
        if admin_result.is_error:
            return Result.fail(admin_result)

        if not admin_result.value:
            return Result.fail(Errors.not_found(resource="Admin user", identifier=admin_user_uid))

        admin = admin_result.value

        if not admin.can_manage_users():
            logger.warning(f"Non-admin {admin_user_uid} attempted hard-delete of {target_user_uid}")
            return Result.fail(
                Errors.forbidden(
                    action="hard_delete_user",
                    reason="Hard-delete requires ADMIN role",
                    required_role=UserRole.ADMIN.value,
                )
            )

        return await self.core.hard_delete_user(
            target_user_uid,
            requester_role=admin.role,
            deleted_by=admin_user_uid,
            reason=reason,
        )

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
    # ROLE MANAGEMENT (December 2025 - Admin Only)
    # ========================================================================

    async def update_role(
        self,
        target_user_uid: UserUID,
        new_role: UserRole,
        admin_user_uid: UserUID,
    ) -> Result[User]:
        """
        Update a user's role (ADMIN only).

        Performs authorization check before delegating to UserCoreService.

        Args:
            target_user_uid: User to update
            new_role: New role to assign
            admin_user_uid: UID of admin making the change

        Returns:
            Result[User]: Updated user or error

        Business Rules:
            - Only ADMIN can change user roles
            - Admins cannot demote themselves
            - Prevents escalation beyond ADMIN
            - An actual role change revokes all of the target's live sessions
              (forced re-login — see security-hardening roadmap item 4)
        """
        # Verify admin has permission
        admin_result = await self.get_user(admin_user_uid)
        if admin_result.is_error:
            return Result.fail(admin_result)

        if not admin_result.value:
            return Result.fail(Errors.not_found(resource="Admin user", identifier=admin_user_uid))

        admin = admin_result.value

        if not admin.can_manage_users():
            logger.warning(
                f"Non-admin {admin_user_uid} attempted to change role for {target_user_uid}"
            )
            return Result.fail(
                Errors.business(rule="admin_only", message="Only admins can change user roles")
            )

        # Prevent self-demotion for admins
        if target_user_uid == admin_user_uid and new_role != UserRole.ADMIN:
            return Result.fail(
                Errors.business(rule="self_demotion", message="Admins cannot demote themselves")
            )

        # Fetch target first: a no-op role set must not revoke live sessions
        # (also keeps an ADMIN→ADMIN self-update from logging the admin out)
        target_result = await self.get_user(target_user_uid)
        if target_result.is_error:
            return Result.fail(target_result)
        if not target_result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=target_user_uid))
        if target_result.value.role == new_role:
            return await self.core.update_user_role(target_user_uid, new_role)

        # Revoke BEFORE persisting the new role. Revoke-after is not
        # retryable: the retry would see the role already updated, take the
        # no-op branch above, and never re-attempt the revocation — leaving
        # stale-privilege sessions alive for their full lifetime. Failing
        # here leaves the role untouched, so the admin's retry re-runs both
        # steps. Worst case (revocation succeeds, update below fails): the
        # target re-logs-in with the old role — annoying, never insecure.
        revocation = await self._revoke_all_sessions(target_user_uid, change="role change")
        if revocation.is_error:
            return Result.fail(revocation)

        return await self.core.update_user_role(target_user_uid, new_role)

    async def _revoke_all_sessions(self, target_user_uid: UserUID, change: str) -> Result[int]:
        """Revoke all live sessions for a privilege change (forced re-login).

        Revocation is enforced per-request by AuthContextMiddleware. Retry
        semantics are the caller's contract: update_role revokes BEFORE
        persisting (a failure leaves the role untouched, so the retry
        re-runs both steps); deactivate_user revokes after (deactivation is
        idempotent, so the retry re-attempts the revocation).
        """
        if self.session_invalidator is None:
            return Result.fail(
                Errors.system(
                    "Session invalidator not wired — pass session_invalidator to UserService",
                    operation="revoke_sessions",
                )
            )

        invalidation = await self.session_invalidator.invalidate_all_user_sessions(target_user_uid)
        if invalidation.is_error:
            logger.error(
                f"Session revocation for {change} failed for {target_user_uid}: "
                f"{invalidation.expect_error().message}"
            )
            return Result.fail(
                Errors.database(
                    operation="revoke_sessions",
                    message=f"Revoking the user's live sessions failed — retry the {change} "
                    f"so no session outlives its privileges",
                )
            )

        logger.info(
            f"Revoked {invalidation.value} live session(s) for {target_user_uid} ({change})"
        )
        return invalidation

    async def list_users(
        self,
        admin_user_uid: UserUID,
        limit: int = 100,
        offset: int = 0,
        role_filter: UserRole | None = None,
        active_only: bool = True,
    ) -> Result[list[User]]:
        """
        List users (ADMIN only).

        Args:
            admin_user_uid: UID of admin making the request
            limit: Max results
            offset: Pagination offset
            role_filter: Optional filter by role
            active_only: Only return active users (default True)

        Returns:
            Result[list[User]]: List of users or error
        """
        # Verify admin has permission
        admin_result = await self.get_user(admin_user_uid)
        if admin_result.is_error:
            return Result.fail(admin_result)

        if not admin_result.value:
            return Result.fail(Errors.not_found(resource="Admin user", identifier=admin_user_uid))

        if not admin_result.value.can_manage_users():
            logger.warning(f"Non-admin {admin_user_uid} attempted to list users")
            return Result.fail(
                Errors.business(rule="admin_only", message="Only admins can list users")
            )

        # Delegate to core service
        return await self.core.list_users(limit, offset, role_filter, active_only)

    async def deactivate_user(
        self,
        target_user_uid: UserUID,
        admin_user_uid: UserUID,
        reason: str = "",
    ) -> Result[User]:
        """
        Deactivate a user account (ADMIN only).

        Also revokes all of the target's live sessions — deactivation must
        take effect immediately, not at next login.

        Args:
            target_user_uid: User to deactivate
            admin_user_uid: Admin making the request
            reason: Reason for deactivation

        Returns:
            Result[User]: Updated user or error
        """
        # Verify admin has permission
        admin_result = await self.get_user(admin_user_uid)
        if admin_result.is_error:
            return Result.fail(admin_result)

        if not admin_result.value:
            return Result.fail(Errors.not_found(resource="Admin user", identifier=admin_user_uid))

        admin = admin_result.value

        if not admin.can_manage_users():
            logger.warning(f"Non-admin {admin_user_uid} attempted to deactivate {target_user_uid}")
            return Result.fail(
                Errors.business(rule="admin_only", message="Only admins can deactivate users")
            )

        # Prevent self-deactivation
        if target_user_uid == admin_user_uid:
            return Result.fail(
                Errors.business(
                    rule="self_deactivation", message="Admins cannot deactivate themselves"
                )
            )

        # Delegate to core service
        result = await self.core.deactivate_user(target_user_uid, reason)
        if result.is_error:
            return result

        # Session nodes cache user_is_active at creation, so deactivation
        # alone leaves live sessions valid — revoke them explicitly. Revoking
        # AFTER the persist is retry-safe here (unlike update_role) because
        # deactivating an already-inactive user is an idempotent success, so
        # a retry always reaches this revocation again.
        revocation = await self._revoke_all_sessions(target_user_uid, change="deactivation")
        if revocation.is_error:
            return Result.fail(revocation)
        return result

    async def activate_user(
        self,
        target_user_uid: UserUID,
        admin_user_uid: UserUID,
    ) -> Result[User]:
        """
        Reactivate a user account (ADMIN only).

        Args:
            target_user_uid: User to reactivate
            admin_user_uid: Admin making the request

        Returns:
            Result[User]: Updated user or error
        """
        # Verify admin has permission
        admin_result = await self.get_user(admin_user_uid)
        if admin_result.is_error:
            return Result.fail(admin_result)

        if not admin_result.value:
            return Result.fail(Errors.not_found(resource="Admin user", identifier=admin_user_uid))

        if not admin_result.value.can_manage_users():
            logger.warning(f"Non-admin {admin_user_uid} attempted to activate {target_user_uid}")
            return Result.fail(
                Errors.business(rule="admin_only", message="Only admins can activate users")
            )

        # Delegate to core service
        return await self.core.activate_user(target_user_uid)

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

    # ========================================================================
    # PROFILE HUB DATA (Delegate to UserStatsAggregator)
    # ========================================================================

    async def get_profile_hub_data(self, user_uid: UserUID) -> Result[ProfileHubData]:
        """
        Get aggregated data for user profile hub.

        Pattern 3C + UserContext Integration:
        - Builds UserContext from domain queries (single source of truth)
        - Uses ProfileHubData.from_context() to compute statistical view
        - Returns strongly-typed ProfileHubData with full context

        Args:
            user_uid: User's unique identifier

        Returns:
            Result[ProfileHubData]: Strongly-typed profile hub data with frozen dataclasses

        Raises:
            ValueError: If stats aggregator not initialized (driver required)
        """
        if not self.stats:
            from core.utils.result_simplified import Errors

            return Result.fail(
                Errors.system(
                    message="ProfileHubData requires Neo4j driver - initialize UserService with driver"
                )
            )

        return await self.stats.get_profile_hub_data(user_uid)

    # ========================================================================
    # CONTEXT BUILDING (Internal - used by stats aggregator)
    # ========================================================================

    async def _build_user_context(self, user_uid: UserUID, user: User) -> Result[UserContext]:
        """
        Build UserContext from domain queries.

        INTERNAL METHOD: Used by UserStatsAggregator.

        Args:
            user_uid: User's unique identifier
            user: User entity

        Returns:
            Result[UserContext] with complete domain awareness (~240 fields)
        """
        if not self.context_builder:
            return Result.fail(Errors.system(message="Context building requires Neo4j driver"))

        return await self.context_builder.build_user_context(user_uid, user)

    # ========================================================================
    # RICH CONTEXT (November 22, 2025 - Neo4j Optimization)
    # ========================================================================

    def peek_cached_context(self, user_uid: UserUID) -> RichUserContext | None:
        """Cache-hit-only context access — NEVER builds (no MEGA-QUERY, ever).

        For latency-sensitive surfaces (the keystroke-driven /search path)
        that want to enrich opportunistically when a rich context is already
        warm, and silently do without one when it isn't. Use
        ``get_rich_unified_context`` when you need a context unconditionally.
        """
        if self.activity is None:
            return None
        return self.activity.get_valid_context(user_uid)

    async def get_rich_unified_context(
        self, user_uid: UserUID, min_confidence: float = 0.7
    ) -> Result[RichUserContext]:
        """
        Get COMPLETE UserContext with BOTH standard AND rich fields.

        **PERFORMANCE OPTIMIZATION (February 6, 2026):**
        Now uses UserContextCache (5-minute TTL) with event-driven invalidation.
        - Cache hit (~80% of requests): Returns instantly without database query
        - Cache miss: Builds context with MEGA-QUERY and caches result
        - Auto-invalidation: Domain events (TaskCompleted, GoalAchieved, etc.) clear cache

        **ARCHITECTURE REFACTOR (November 24, 2025):**
        This now uses the TRUE MEGA-QUERY that fetches EVERYTHING in a single database query.

        **Before:** 2-3 queries (standard context + MEGA-QUERY)
        **After:** 1 query (TRUE MEGA-QUERY) with caching

        This single comprehensive query fetches:
        1. **Standard context fields** (UIDs, relationships, metadata)
           - active_task_uids, active_goal_uids, active_habit_uids
           - habit_streaks, knowledge_mastery, goal_progress
           - tasks_by_goal, overdue_task_uids, etc.

        2. **Rich context fields** (full entities + graph neighborhoods)
           - entities_rich: {"tasks": [{entity: {...}, graph_context: {...}}, ...], "goals": [...], ...}
           - knowledge_units_rich: {uid: {ku: {...}, graph_context: {prerequisites, dependents}}, ...}

        Args:
            user_uid: User's unique identifier
            min_confidence: Minimum relationship confidence (default 0.7)

        Returns:
            Result[UserContext] with ALL ~240 fields populated

        Performance:
            - Cache hit: ~1-5ms (no database query)
            - Cache miss: ~800ms-2s (MEGA-QUERY runs)
            - Expected cache hit rate: ~80% during active user sessions

        Usage:
            # Dashboard view - needs full entity data
            context_result = await user_service.get_rich_unified_context(user_uid)
            context = context_result.value

            # Access lightweight UIDs (standard context)
            task_uids = context.active_task_uids # ✅ Populated from MEGA-QUERY

            # Access rich entities with graph neighborhoods
            for task_data in context.entities_rich.get("tasks", []):  # ✅ Populated from MEGA-QUERY
                task = task_data["entity"]
                graph_context = task_data["graph_context"]

                # Use subtasks, dependencies, applied knowledge, etc.
                subtasks = graph_context["subtasks"]
                dependencies = graph_context["dependencies"]
                knowledge = graph_context["applied_knowledge"]
        """
        if not self.context_builder:
            return Result.fail(Errors.system(message="Rich context building requires Neo4j driver"))

        # ========================================================================
        # STEP 1: Check cache first (5-minute TTL with event-driven invalidation)
        # ========================================================================
        if self.activity:
            cached_context = self.activity.get_valid_context(user_uid)
            if cached_context:
                logger.debug(
                    "Rich context cache HIT", extra={"user_uid": user_uid, "cache_age_seconds": 0}
                )
                return Result.ok(cached_context)

            logger.debug(
                "Rich context cache MISS - building from database", extra={"user_uid": user_uid}
            )

        # ========================================================================
        # STEP 2: Cache miss - build from database (MEGA_QUERY)
        # ========================================================================
        # Use builder-owned user resolution to avoid duplicating lookup/error handling
        # and keep MEGA_QUERY orchestration in a single place.
        context_result = await self.context_builder.build_rich(
            user_uid, min_confidence=min_confidence
        )

        if context_result.is_error:
            return context_result

        # ========================================================================
        # STEP 3: Cache the freshly-built context
        # ========================================================================
        context = context_result.value
        if self.activity:
            self.activity.cache_context(user_uid, context)
            logger.debug(
                "Rich context cached",
                extra={"user_uid": user_uid, "cache_ttl_seconds": 300},  # 5 minutes
            )

        return Result.ok(context)

    # ========================================================================
    # INTELLIGENCE METHODS
    # ========================================================================

    async def get_daily_work_plan(
        self,
        user_uid: UserUID,
        prioritize_life_path: bool = True,
        respect_capacity: bool = True,
    ) -> Result[DailyWorkPlan]:
        """
        Get optimal daily work plan for a user.

        🎯 THE FLAGSHIP METHOD - What should I focus on TODAY?

        This synthesizes across ALL domains to create an optimal daily plan:
        - Learning: Knowledge ready to learn + aligned with goals
        - Tasks: Today's tasks + high-impact tasks + overdue tasks
        - Habits: Daily habits + at-risk habits (maintain streaks)
        - Goals: Goals nearing deadline + primary goal focus
        - Events: Today's events

        Considers:
        - User capacity (available_minutes_daily)
        - Energy level (current_energy_level)
        - Workload (current_workload_score)
        - Life path alignment (if prioritize_life_path=True)

        Args:
            user_uid: User's unique identifier
            prioritize_life_path: Weight life path alignment highly
            respect_capacity: Don't exceed available time

        Returns:
            Result[DailyWorkPlan]: Complete daily plan with rationale and priorities
        """
        # Check if intelligence factory is available
        if not self.intelligence_factory:
            return Result.fail(
                Errors.system(
                    message="Intelligence factory not available",
                    operation="get_daily_work_plan",
                )
            )

        # Build rich user context — intelligence methods consume rich-only fields.
        context_result = await self.get_rich_unified_context(user_uid)
        if context_result.is_error:
            return Result.fail(context_result)

        context = context_result.value

        # Create intelligence service from factory and get daily plan
        intelligence = self.intelligence_factory.create(context)
        return await intelligence.get_ready_to_work_on_today(
            prioritize_life_path=prioritize_life_path,
            respect_capacity=respect_capacity,
        )


# ============================================================================
# FACTORY FUNCTION (Bootstrap Compatibility)
# ============================================================================


def create_user_service(
    user_repo: UserOperations,
    query_executor: Any | None = None,
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
        query_executor: Optional UserContextQueryExecutor for cross-domain context
            building (built at the composition root; ADR-044/SKUEL022)
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
