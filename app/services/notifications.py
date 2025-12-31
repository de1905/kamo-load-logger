"""Email notification service."""

import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional

import aiosmtplib

from app.config import get_settings

logger = logging.getLogger(__name__)


class NotificationService:
    """Send email notifications for alerts."""

    def __init__(self):
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        """Check if notifications are enabled."""
        return self.settings.notifications_enabled

    async def send_email(
        self,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> bool:
        """
        Send an email notification.

        Returns True if sent successfully, False otherwise.
        """
        if not self.enabled:
            logger.debug("Notifications disabled, skipping email")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[KAMO Logger] {subject}"
            msg["From"] = self.settings.smtp_from or self.settings.smtp_user
            msg["To"] = self.settings.notification_email

            # Plain text version
            msg.attach(MIMEText(body, "plain"))

            # HTML version (optional)
            if html_body:
                msg.attach(MIMEText(html_body, "html"))

            # Send via SMTP
            await aiosmtplib.send(
                msg,
                hostname=self.settings.smtp_host,
                port=self.settings.smtp_port,
                username=self.settings.smtp_user,
                password=self.settings.smtp_password,
                start_tls=True,
            )

            logger.info(f"Email sent: {subject}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    async def send_failure_alert(self, message: str) -> bool:
        """Send an import failure alert."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        body = f"""KAMO Load Logger Alert

Time: {timestamp}
Status: Import Failure

{message}

---
This is an automated message from KAMO Load Logger.
Check the dashboard for more details.
"""

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
        .alert {{ background-color: #fee; border: 1px solid #c00; padding: 15px; border-radius: 5px; }}
        .header {{ color: #c00; margin-bottom: 10px; }}
        .timestamp {{ color: #666; font-size: 12px; }}
        .footer {{ margin-top: 20px; padding-top: 10px; border-top: 1px solid #ddd; font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <h2>KAMO Load Logger Alert</h2>
    <div class="alert">
        <div class="header"><strong>Import Failure</strong></div>
        <p>{message}</p>
        <div class="timestamp">Time: {timestamp}</div>
    </div>
    <div class="footer">
        This is an automated message from KAMO Load Logger.<br>
        Check the dashboard for more details.
    </div>
</body>
</html>
"""

        return await self.send_email("Import Failure Alert", body, html_body)

    async def send_recovery_notice(self) -> bool:
        """Send a notice that imports have recovered."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        body = f"""KAMO Load Logger Notice

Time: {timestamp}
Status: Import Recovered

Data imports have resumed successfully after previous failures.

---
This is an automated message from KAMO Load Logger.
"""

        return await self.send_email("Import Recovered", body)

    async def send_test_email(self) -> bool:
        """Send a test email to verify configuration."""
        body = """KAMO Load Logger Test

This is a test email to verify your notification settings are configured correctly.

If you received this email, notifications are working!

---
KAMO Load Logger
"""
        return await self.send_email("Test Notification", body)
