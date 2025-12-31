"""Application configuration from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API
    api_key: str = "change-me"

    # Database
    database_url: str = "sqlite:///data/kamo_load.db"

    # Polling
    # KAMO API updates substation data every ~3 minutes
    # Default to 5 minutes for good resolution without excessive load
    # Timestamps are standardized to even 5-minute marks (e.g., 9:00, 9:05, 9:10)
    poll_interval_minutes: int = 5

    # Logging
    log_level: str = "INFO"

    # KAMO API
    kamo_base_url: str = "https://kamofamilyload.kamopower.com/api"

    # Timezone
    tz: str = "America/Chicago"

    # SMTP (optional)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    notification_email: str = ""

    @property
    def notifications_enabled(self) -> bool:
        """Check if email notifications are configured."""
        return bool(self.smtp_host and self.smtp_user and self.notification_email)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
