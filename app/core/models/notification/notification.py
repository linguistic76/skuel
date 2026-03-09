"""
Notification Model
==================

Frozen dataclass for in-app notifications stored as :Notification nodes in Neo4j.
Linked to users via (User)-[:HAS_NOTIFICATION]->(Notification).

Notifications are created by event handlers (e.g., when a teacher provides feedback)
and consumed by the navbar badge + /notifications page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Notification:
    """
    In-app notification for a user.

    Graph pattern: (User)-[:HAS_NOTIFICATION]->(Notification)
    """

    uid: str
    user_uid: str  # Recipient
    notification_type: str  # e.g., "feedback_received", "revision_requested"
    title: str  # Short display title
    message: str  # Longer description
    source_uid: str  # The entity UID that triggered this notification
    source_type: str  # Entity type (e.g., "submission_report", "submission")
    read: bool = False
    created_at: datetime = field(default_factory=datetime.now)
