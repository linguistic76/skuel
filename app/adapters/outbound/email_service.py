"""
Resend Email Service
=====================

Email delivery adapter using the Resend API.

This is the single email delivery path for SKUEL.
Currently supports password reset emails only.

See: /core/ports/email_protocols.py - EmailOperations protocol
"""

import resend

from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.adapters.email")


class ResendEmailService:
    """Email delivery service using Resend API.

    Implements EmailOperations protocol.

    Args:
        api_key: Resend API key (required, fail-fast)
        from_email: Sender email address (required)
    """

    def __init__(self, api_key: str, from_email: str) -> None:
        if not api_key:
            raise ValueError("RESEND_API_KEY is required")
        if not from_email:
            raise ValueError("RESEND_FROM_EMAIL is required")

        resend.api_key = api_key
        self.from_email = from_email
        logger.info("ResendEmailService initialized")

    async def send_password_reset(
        self, to_email: str, reset_link: str, display_name: str | None = None
    ) -> Result[bool]:
        """
        Send a password reset email via Resend.

        Args:
            to_email: Recipient email address
            reset_link: Full URL with reset token
            display_name: Optional name for personalization

        Returns:
            Result[bool] indicating delivery success
        """
        greeting = f"Hi {display_name}" if display_name else "Hi"

        html_body = f"""
        <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 24px;">
            <h2 style="color: #1a1a2e;">SKUEL Password Reset</h2>
            <p>{greeting},</p>
            <p>We received a request to reset your password. Click the button below to choose a new one:</p>
            <p style="text-align: center; margin: 32px 0;">
                <a href="{reset_link}"
                   style="background-color: #6366f1; color: white; padding: 12px 32px;
                          text-decoration: none; border-radius: 6px; font-weight: 600;">
                    Reset Password
                </a>
            </p>
            <p style="color: #666; font-size: 14px;">
                This link expires in 15 minutes. If you didn't request a password reset,
                you can safely ignore this email.
            </p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;" />
            <p style="color: #999; font-size: 12px;">SKUEL</p>
        </div>
        """

        try:
            resend.Emails.send(
                {
                    "from": self.from_email,
                    "to": [to_email],
                    "subject": "Reset your SKUEL password",
                    "html": html_body,
                }
            )
            logger.info(f"Password reset email sent to {to_email}")
            return Result.ok(True)
        except Exception as e:
            logger.error(f"Failed to send password reset email: {e}")
            return Result.fail(
                Errors.integration(
                    service="resend",
                    message=f"Email delivery failed: {e}",
                )
            )
