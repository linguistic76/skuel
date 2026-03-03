"""
Email Service Protocols
========================

Protocol for email delivery operations.

See: /docs/patterns/protocol_architecture.md
"""

from typing import Protocol, runtime_checkable

from core.utils.result_simplified import Result


@runtime_checkable
class EmailOperations(Protocol):
    """Protocol for email delivery services.

    Implementations: ResendEmailService (adapters/outbound/email_service.py)
    """

    async def send_password_reset(
        self, to_email: str, reset_link: str, display_name: str | None = None
    ) -> Result[bool]:
        """
        Send a password reset email.

        Args:
            to_email: Recipient email address
            reset_link: Full URL for the password reset page with token
            display_name: Optional display name for personalization

        Returns:
            Result[bool] indicating success or failure
        """
        ...
