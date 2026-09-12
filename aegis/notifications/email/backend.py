"""
Aegis — Email Delivery Backends (AC-4.6)

Provides:
- EmailBackend base protocol
- FakeEmailBackend: in-memory mock for CI and offline development (no credentials required)
- SMTPEmailBackend: production SMTP delivery using settings
- Factory function get_email_backend()
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Protocol

from core.config.settings import get_settings
from core.logging.logger import setup_logging

logger = setup_logging()


class EmailBackend(Protocol):
    """Protocol defining the email sending interface."""

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> bool:
        """Send an email to a single recipient."""
        ...


class FakeEmailBackend:
    """
    In-memory mock email backend for testing and development.
    Requires zero external network or credentials (AC-4.6).
    """

    def __init__(self) -> None:
        self.sent_emails: list[dict[str, Any]] = []

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> bool:
        """Records the email in memory and logs."""
        record = {
            "to": to_email,
            "subject": subject,
            "html_body": html_body,
            "text_body": text_body,
        }
        self.sent_emails.append(record)
        logger.info(
            "FakeEmailBackend: Captured email to %s (subject: %s)",
            to_email,
            subject,
        )
        return True

    def clear(self) -> None:
        """Clear recorded emails."""
        self.sent_emails.clear()

    @property
    def count(self) -> int:
        return len(self.sent_emails)


class SMTPEmailBackend:
    """Production SMTP email delivery backend."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> bool:
        """Sends an email via SMTP server configured in settings."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.settings.smtp_from_email
        msg["To"] = to_email

        part1 = MIMEText(text_body, "plain", "utf-8")
        part2 = MIMEText(html_body, "html", "utf-8")
        msg.attach(part1)
        msg.attach(part2)

        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=10) as server:
                if self.settings.smtp_use_tls:
                    server.starttls()
                if self.settings.smtp_user and self.settings.smtp_password:
                    server.login(self.settings.smtp_user, self.settings.smtp_password)
                server.sendmail(self.settings.smtp_from_email, [to_email], msg.as_string())
            logger.info("SMTPEmailBackend: Sent email to %s (subject: %s)", to_email, subject)
            return True
        except Exception as exc:
            logger.error("SMTPEmailBackend: Failed to send email to %s: %s", to_email, exc)
            return False


# Global singleton instance of the fake email backend for easy inspection in tests
_fake_backend_instance = FakeEmailBackend()


def get_email_backend() -> EmailBackend:
    """Factory returning configured email backend."""
    settings = get_settings()
    if settings.use_fake_email_backend or settings.environment == "testing":
        return _fake_backend_instance
    return SMTPEmailBackend()
