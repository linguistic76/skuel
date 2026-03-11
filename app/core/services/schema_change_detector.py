"""
Schema Change Detection Service
==============================

Monitors Neo4j schema evolution and detects changes that could impact
query optimization. Provides adaptive responses to schema changes.
"""

__version__ = "1.0"


import asyncio
import contextlib
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from core.models.schema_change import (  # type: ignore[import-not-found]
    ChangeImpact,
    SchemaChange,
    SchemaChangeEvent,
    SchemaChangeReport,
    SchemaChangeType,
    SchemaEvolutionStats,
    SchemaFingerprint,
    SchemaMigrationHistory,
)

from core.infrastructure.database.schema import SchemaContext
from core.utils.decorators import with_error_handling
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result


class SchemaChangeDetector:
    """
    Monitors schema changes and provides adaptive query optimization.

    Features:
    - Lightweight fingerprinting for change detection
    - Detailed change analysis and impact assessment
    - Event-driven notifications for schema changes
    - Migration history tracking
    - Adaptive query optimization updates
    """

    def __init__(self, schema_service, storage_path: str | None = None) -> None:
        self.schema_service = schema_service
        self.storage_path = storage_path or "/tmp/schema_migration_history.json"
        self.logger = get_logger("SchemaChangeDetector")

        # Event handlers
        self._change_handlers: list[Callable[[SchemaChangeEvent], None]] = []

        # In-memory state
        self._current_fingerprint: SchemaFingerprint | None = None
        self._migration_history: SchemaMigrationHistory | None = None
        self._is_monitoring = False
        self._monitor_task: asyncio.Task | None = None

        # Configuration
        self.check_interval_seconds = 300  # 5 minutes
        self.enable_persistence = True

    @with_error_handling("initialize", error_type="database")
    async def initialize(self) -> Result[bool]:
        """Initialize the change detector with current schema state"""
        # Get current schema
        schema_result = await self.schema_service.get_schema_context()
        if schema_result.is_error:
            return schema_result

        current_schema = schema_result.value
        current_fingerprint = SchemaFingerprint.from_schema_context(current_schema)

        # Load or create migration history
        await self._load_migration_history(current_fingerprint)

        self._current_fingerprint = current_fingerprint
        self.logger.info(
            f"Schema change detector initialized with {len(current_schema.indexes)} indexes, {len(current_schema.node_labels)} labels"
        )

        return Result.ok(True)

    @with_error_handling("check_for_changes", error_type="database")
    async def check_for_changes(self) -> Result[SchemaChangeReport]:
        """
        Check for schema changes since last check.
        Returns a report of any changes detected.
        """
        if not self._current_fingerprint:
            await self.initialize()

        if not self._current_fingerprint:
            return Result.fail(
                Errors.system(
                    message="Schema fingerprint not initialized", operation="check_for_changes"
                )
            )

        # Get fresh schema
        schema_result = await self.schema_service.get_schema_context(force_refresh=True)
        if schema_result.is_error:
            return schema_result

        new_schema = schema_result.value
        new_fingerprint = SchemaFingerprint.from_schema_context(new_schema)

        # Compare fingerprints
        if not self._current_fingerprint.has_changed(new_fingerprint):
            # No changes detected
            return Result.ok(
                SchemaChangeReport(
                    from_fingerprint=self._current_fingerprint,
                    to_fingerprint=new_fingerprint,
                    changes=[],
                    overall_impact=ChangeImpact.LOW,
                )
            )

        # Changes detected - analyze them
        self.logger.info("Schema changes detected, analyzing...")

        change_report = await self._analyze_changes(
            self._current_fingerprint, new_fingerprint, new_schema
        )

        # Update state
        self._current_fingerprint = new_fingerprint
        if self._migration_history:
            self._migration_history.add_change_report(change_report)

            if self.enable_persistence:
                await self._save_migration_history()

        # Notify handlers
        await self._notify_change_handlers(change_report)

        self.logger.info(
            f"Detected {len(change_report.changes)} schema changes with {change_report.overall_impact.value} impact"
        )

        return Result.ok(change_report)

    async def _analyze_changes(
        self, old_fp: SchemaFingerprint, new_fp: SchemaFingerprint, new_schema: SchemaContext
    ) -> SchemaChangeReport:
        """Analyze specific changes between two schema states"""
        changes = []
        changed_areas = old_fp.get_changed_areas(new_fp)

        # Get old schema for comparison
        # Note: In a production system, you might want to cache old schema contexts
        # For now, we'll analyze based on fingerprint differences

        # Analyze count changes (quick detection)
        if old_fp.label_count != new_fp.label_count:
            change = SchemaChange(
                change_type=SchemaChangeType.LABEL_ADDED
                if new_fp.label_count > old_fp.label_count
                else SchemaChangeType.LABEL_REMOVED,
                impact=ChangeImpact.MEDIUM,
                description=f"Node label count changed from {old_fp.label_count} to {new_fp.label_count}",
                affected_entity="node_labels",
                old_value=old_fp.label_count,
                new_value=new_fp.label_count,
            )
            changes.append(change)

        if old_fp.index_count != new_fp.index_count:
            impact = (
                ChangeImpact.HIGH
                if abs(new_fp.index_count - old_fp.index_count) > 5
                else ChangeImpact.MEDIUM
            )
            change = SchemaChange(
                change_type=SchemaChangeType.INDEX_ADDED
                if new_fp.index_count > old_fp.index_count
                else SchemaChangeType.INDEX_REMOVED,
                impact=impact,
                description=f"Index count changed from {old_fp.index_count} to {new_fp.index_count}",
                affected_entity="indexes",
                old_value=old_fp.index_count,
                new_value=new_fp.index_count,
                optimization_impact="Query optimization strategies may need recalculation",
            )
            changes.append(change)

        if old_fp.constraint_count != new_fp.constraint_count:
            change = SchemaChange(
                change_type=SchemaChangeType.CONSTRAINT_ADDED
                if new_fp.constraint_count > old_fp.constraint_count
                else SchemaChangeType.CONSTRAINT_REMOVED,
                impact=ChangeImpact.MEDIUM,
                description=f"Constraint count changed from {old_fp.constraint_count} to {new_fp.constraint_count}",
                affected_entity="constraints",
                old_value=old_fp.constraint_count,
                new_value=new_fp.constraint_count,
                optimization_impact="Unique lookup optimizations may be affected",
            )
            changes.append(change)

        if old_fp.relationship_count != new_fp.relationship_count:
            change = SchemaChange(
                change_type=SchemaChangeType.RELATIONSHIP_TYPE_ADDED
                if new_fp.relationship_count > old_fp.relationship_count
                else SchemaChangeType.RELATIONSHIP_TYPE_REMOVED,
                impact=ChangeImpact.LOW,
                description=f"Relationship type count changed from {old_fp.relationship_count} to {new_fp.relationship_count}",
                affected_entity="relationship_types",
                old_value=old_fp.relationship_count,
                new_value=new_fp.relationship_count,
            )
            changes.append(change)

        # Analyze hash changes for specific areas
        if "indexes" in changed_areas:
            # Significant index changes detected
            change = SchemaChange(
                change_type=SchemaChangeType.INDEX_MODIFIED,
                impact=ChangeImpact.HIGH,
                description="Index structure has been modified",
                affected_entity="index_configuration",
                optimization_impact="All query optimization strategies should be recalculated",
            )
            changes.append(change)

        if "properties" in changed_areas:
            change = SchemaChange(
                change_type=SchemaChangeType.PROPERTY_ADDED,
                impact=ChangeImpact.MEDIUM,
                description="Property mappings have changed",
                affected_entity="property_schema",
                optimization_impact="Property-based optimizations may need updates",
            )
            changes.append(change)

        # Determine overall impact
        if not changes:
            overall_impact = ChangeImpact.LOW
        else:
            impact_levels = [change.impact for change in changes]
            if ChangeImpact.CRITICAL in impact_levels:
                overall_impact = ChangeImpact.CRITICAL
            elif ChangeImpact.HIGH in impact_levels:
                overall_impact = ChangeImpact.HIGH
            elif ChangeImpact.MEDIUM in impact_levels:
                overall_impact = ChangeImpact.MEDIUM
            else:
                overall_impact = ChangeImpact.LOW

        # Generate recommendations
        recommendations = self._generate_recommendations(changes, new_schema)

        return SchemaChangeReport(
            from_fingerprint=old_fp,
            to_fingerprint=new_fp,
            changes=changes,
            overall_impact=overall_impact,
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self, changes: list[SchemaChange], schema: SchemaContext
    ) -> list[str]:
        """Generate recommendations based on detected changes"""
        recommendations = []

        # Index-related recommendations
        index_changes = [c for c in changes if "index" in c.change_type.value.lower()]
        if index_changes:
            recommendations.append(
                "Clear query optimization cache to ensure new indexes are utilized"
            )
            recommendations.append("Re-run query plan analysis to update cost estimates")

            # Check for new fulltext indexes
            fulltext_indexes = [idx for idx in schema.indexes if idx.type == "FULLTEXT"]
            if fulltext_indexes:
                recommendations.append(
                    f"New fulltext search capabilities available: {[idx.name for idx in fulltext_indexes]}"
                )

        # Constraint-related recommendations
        constraint_changes = [c for c in changes if "constraint" in c.change_type.value.lower()]
        if constraint_changes:
            recommendations.append("Update unique lookup optimizations for new constraints")
            recommendations.append("Refresh template selection rules for constraint-based queries")

        # Property-related recommendations
        property_changes = [c for c in changes if "property" in c.change_type.value.lower()]
        if property_changes:
            recommendations.append("Update property validation rules in query builders")
            recommendations.append(
                "Consider creating indexes for frequently queried new properties"
            )

        # High-impact changes
        high_impact_changes = [
            c for c in changes if c.impact in [ChangeImpact.HIGH, ChangeImpact.CRITICAL]
        ]
        if high_impact_changes:
            recommendations.append(
                "Perform full system re-optimization due to significant schema changes"
            )
            recommendations.append("Test existing queries to ensure they still function correctly")

        return recommendations

    @with_error_handling("start_monitoring", error_type="system")
    async def start_monitoring(self, interval_seconds: int | None = None) -> Result[bool]:
        """Start continuous schema monitoring"""
        if self._is_monitoring:
            return Result.ok(True)  # Already monitoring

        if interval_seconds:
            self.check_interval_seconds = interval_seconds

        self._is_monitoring = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())

        self.logger.info(f"Started schema monitoring with {self.check_interval_seconds}s interval")
        return Result.ok(True)

    @with_error_handling("stop_monitoring", error_type="system")
    async def stop_monitoring(self) -> Result[bool]:
        """Stop continuous schema monitoring"""
        if not self._is_monitoring:
            return Result.ok(True)  # Not monitoring

        self._is_monitoring = False

        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task

        self.logger.info("Stopped schema monitoring")
        return Result.ok(True)

    async def _monitoring_loop(self) -> None:
        """Continuous monitoring loop"""
        while self._is_monitoring:
            try:
                change_result = await self.check_for_changes()

                if change_result.is_ok:
                    report = change_result.value
                    if report.changes:
                        self.logger.info(
                            f"Detected {len(report.changes)} schema changes during monitoring"
                        )
                else:
                    self.logger.warning(f"Schema change check failed: {change_result.error}")

                # Wait for next check
                await asyncio.sleep(self.check_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval_seconds)

    def add_change_handler(self, handler: Callable[[SchemaChangeEvent], None]):
        """Add a handler for schema change events"""
        self._change_handlers.append(handler)
        self.logger.debug(
            f"Added schema change handler, total handlers: {len(self._change_handlers)}"
        )

    def remove_change_handler(self, handler: Callable[[SchemaChangeEvent], None]):
        """Remove a schema change handler"""
        if handler in self._change_handlers:
            self._change_handlers.remove(handler)
            self.logger.debug(
                f"Removed schema change handler, remaining handlers: {len(self._change_handlers)}"
            )

    async def _notify_change_handlers(self, report: SchemaChangeReport) -> None:
        """Notify all registered change handlers"""
        if not self._change_handlers or not report.changes:
            return

        event = SchemaChangeEvent(
            event_id=f"schema_change_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            change_report=report,
        )

        for handler in self._change_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                self.logger.error(f"Error in change handler: {e}", exc_info=True)

    async def _load_migration_history(self, current_fp: SchemaFingerprint) -> None:
        """Load migration history from storage"""
        try:
            if not self.enable_persistence:
                self._migration_history = SchemaMigrationHistory(
                    schema_id="default",
                    initial_fingerprint=current_fp,
                    current_fingerprint=current_fp,
                )
                return

            if not Path(self.storage_path).exists():
                # Create new history
                self._migration_history = SchemaMigrationHistory(
                    schema_id="default",
                    initial_fingerprint=current_fp,
                    current_fingerprint=current_fp,
                )
            else:
                # Load existing history (async to avoid blocking)
                def load_history() -> Any:
                    with Path(self.storage_path).open("r") as f:
                        return json.load(f)

                data = await asyncio.to_thread(load_history)

                # Reconstruct fingerprints (simplified - in production you'd want full reconstruction)
                data.get("initial_fingerprint", {})
                data.get("current_fingerprint", {})

                self._migration_history = SchemaMigrationHistory(
                    schema_id=data.get("schema_id", "default"),
                    initial_fingerprint=current_fp,  # Use current for now
                    current_fingerprint=current_fp,
                    migration_count=data.get("migration_count", 0),
                )

                self.logger.info(
                    f"Loaded migration history with {self._migration_history.migration_count} migrations"
                )

        except Exception as e:
            self.logger.warning(f"Could not load migration history: {e}, creating new history")
            self._migration_history = SchemaMigrationHistory(
                schema_id="default", initial_fingerprint=current_fp, current_fingerprint=current_fp
            )

    async def _save_migration_history(self) -> None:
        """Save migration history to storage"""
        if not self.enable_persistence or not self._migration_history:
            return

        try:
            # Create a simplified version for JSON serialization
            history_data = {
                "schema_id": self._migration_history.schema_id,
                "migration_count": self._migration_history.migration_count,
                "initial_fingerprint": asdict(self._migration_history.initial_fingerprint),
                "current_fingerprint": asdict(self._migration_history.current_fingerprint),
                "last_updated": datetime.now().isoformat(),
            }

            # Write history (async to avoid blocking)
            def write_history() -> None:
                with Path(self.storage_path).open("w") as f:
                    json.dump(history_data, f, indent=2, default=str)

            await asyncio.to_thread(write_history)

            self.logger.debug("Saved migration history to storage")

        except Exception as e:
            self.logger.error(f"Failed to save migration history: {e}")

    def get_migration_history(self) -> SchemaMigrationHistory | None:
        """Get the current migration history"""
        return self._migration_history

    def get_evolution_stats(self) -> SchemaEvolutionStats | None:
        """Get statistics about schema evolution"""
        if not self._migration_history:
            return None

        return SchemaEvolutionStats.from_history(self._migration_history)

    @with_error_handling("force_schema_refresh", error_type="database")
    async def force_schema_refresh(self) -> Result[bool]:
        """Force a schema refresh and invalidate caches"""
        # Force refresh schema service cache
        schema_result = await self.schema_service.get_schema_context(force_refresh=True)
        if schema_result.is_error:
            return schema_result

        # Update fingerprint
        new_schema = schema_result.value
        self._current_fingerprint = SchemaFingerprint.from_schema_context(new_schema)

        self.logger.info("Forced schema refresh completed")
        return Result.ok(True)


# Adaptive optimization handler that responds to schema changes
class AdaptiveOptimizationHandler:
    """
    Handles schema changes by updating query optimization systems.
    """

    def __init__(self, neo4j_adapter) -> None:
        self.adapter = neo4j_adapter
        self.logger = get_logger("AdaptiveOptimizationHandler")

    async def handle_schema_change(self, event: SchemaChangeEvent):
        """Handle a schema change event"""
        try:
            report = event.change_report

            self.logger.info(f"Handling schema change event: {len(report.changes)} changes")

            # Clear caches if needed
            if report.requires_cache_invalidation:
                await self._invalidate_caches()

            # Update optimization systems
            if report.requires_reoptimization:
                await self._update_optimizations(report)

            # Handle breaking changes
            if report.has_breaking_changes:
                await self._handle_breaking_changes(report)

            event.mark_handled()

        except Exception as e:
            self.logger.error(f"Failed to handle schema change: {e}", exc_info=True)

    async def _invalidate_caches(self) -> None:
        """Invalidate relevant caches"""
        # Clear schema service cache
        schema_service = self.adapter.get_schema_service()
        await schema_service.get_schema_context(force_refresh=True)

        self.logger.info("Invalidated schema caches")

    async def _update_optimizations(self, _report: SchemaChangeReport) -> None:
        """Update query optimization systems based on changes"""
        from contextlib import suppress

        # Force refresh index-aware builder to pick up new indexes
        with suppress(AttributeError):  # Attribute may not exist
            delattr(self.adapter, "_index_aware_builder")

        # Clear enhanced template caches
        with suppress(AttributeError):  # Attribute may not exist
            delattr(self.adapter, "_enhanced_templates")

        self.logger.info("Updated optimization systems for schema changes")

    async def _handle_breaking_changes(self, report: SchemaChangeReport) -> None:
        """Handle breaking changes that might affect existing queries"""
        breaking_changes = report.get_changes_by_impact(ChangeImpact.CRITICAL)

        for change in breaking_changes:
            self.logger.warning(f"Breaking change detected: {change.description}")

        # In a production system, you might want to:
        # - Send alerts to administrators
        # - Log detailed information for debugging
        # - Update query templates that might be affected
