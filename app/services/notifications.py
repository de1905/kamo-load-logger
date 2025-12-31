"""Email notification service."""

import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional, Tuple

import aiosmtplib

from app.config import get_settings
from app.services.settings import get_setting

logger = logging.getLogger(__name__)


class NotificationService:
    """Send email notifications for alerts."""

    def __init__(self):
        self.env_settings = get_settings()

    def _get_smtp_settings(self) -> dict:
        """Get SMTP settings from DB (with ENV fallback)."""
        return {
            "host": get_setting("smtp_host") or "",
            "port": get_setting("smtp_port") or 587,
            "user": get_setting("smtp_user") or "",
            "password": self.env_settings.smtp_password,  # Password stays in ENV only
            "from_addr": get_setting("smtp_from") or get_setting("smtp_user") or "",
            "notification_email": get_setting("notification_email") or "",
        }

    @property
    def enabled(self) -> bool:
        """Check if notifications are enabled."""
        settings = self._get_smtp_settings()
        return bool(settings["host"] and settings["user"] and settings["notification_email"])

    async def send_email(
        self,
        subject: str,
        body: str,
        html_body: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Send an email notification.

        Returns (success, error_message).
        """
        settings = self._get_smtp_settings()

        if not settings["host"]:
            return False, "SMTP host not configured"
        if not settings["user"]:
            return False, "SMTP user not configured"
        if not settings["notification_email"]:
            return False, "Notification email not configured"
        if not settings["password"]:
            return False, "SMTP password not configured (set in .env file)"

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[KAMO Logger] {subject}"
            msg["From"] = settings["from_addr"]
            msg["To"] = settings["notification_email"]

            # Plain text version
            msg.attach(MIMEText(body, "plain"))

            # HTML version (optional)
            if html_body:
                msg.attach(MIMEText(html_body, "html"))

            # Send via SMTP
            await aiosmtplib.send(
                msg,
                hostname=settings["host"],
                port=settings["port"],
                username=settings["user"],
                password=settings["password"],
                start_tls=True,
            )

            logger.info(f"Email sent: {subject}")
            return True, None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to send email: {error_msg}")
            return False, error_msg

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

        success, _ = await self.send_email("Import Failure Alert", body, html_body)
        return success

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

        success, _ = await self.send_email("Import Recovered", body)
        return success

    async def send_test_email(self) -> Tuple[bool, Optional[str]]:
        """Send a test email to verify configuration."""
        body = """KAMO Load Logger Test

This is a test email to verify your notification settings are configured correctly.

If you received this email, notifications are working!

---
KAMO Load Logger
"""
        return await self.send_email("Test Notification", body)
