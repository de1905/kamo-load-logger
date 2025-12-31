"""Settings service for managing configurable options.

Settings can be stored in the database and override ENV defaults.
Sensitive settings (API_KEY, SMTP_PASSWORD) remain ENV-only.
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.database import Setting, get_session_local
from app.config import get_settings as get_env_settings

logger = logging.getLogger(__name__)


@dataclass
class SettingDefinition:
    """Definition of a configurable setting."""
    key: str
    description: str
    default: Any
    setting_type: str  # 'int', 'str', 'bool'
    editable: bool = True  # Can be edited from UI


# Settings that can be configured from the UI
CONFIGURABLE_SETTINGS: List[SettingDefinition] = [
    SettingDefinition(
        key="poll_interval_minutes",
        description="How often to poll KAMO API (minutes)",
        default=5,
        setting_type="int",
    ),
    SettingDefinition(
        key="log_level",
        description="Logging verbosity (DEBUG, INFO, WARNING, ERROR)",
        default="INFO",
        setting_type="str",
    ),
    SettingDefinition(
        key="smtp_host",
        description="SMTP server for email notifications",
        default="",
        setting_type="str",
    ),
    SettingDefinition(
        key="smtp_port",
        description="SMTP server port",
        default=587,
        setting_type="int",
    ),
    SettingDefinition(
        key="smtp_user",
        description="SMTP username/email",
        default="",
        setting_type="str",
    ),
    SettingDefinition(
        key="smtp_from",
        description="From address for notification emails",
        default="",
        setting_type="str",
    ),
    SettingDefinition(
        key="notification_email",
        description="Email address for failure notifications",
        default="",
        setting_type="str",
    ),
]

# Map of setting keys to their definitions
SETTINGS_MAP = {s.key: s for s in CONFIGURABLE_SETTINGS}


class SettingsService:
    """Service for reading and writing application settings."""

    def __init__(self, db: Optional[Session] = None):
        self._db = db
        self._env_settings = get_env_settings()

    def _get_db(self) -> Session:
        """Get database session."""
        if self._db:
            return self._db
        SessionLocal = get_session_local()
        return SessionLocal()

    def _close_db(self, db: Session):
        """Close database session if we created it."""
        if not self._db:
            db.close()

    def get(self, key: str) -> Any:
        """
        Get a setting value.

        Priority: Database > Environment > Default
        """
        db = self._get_db()
        try:
            # Check database first
            setting = db.query(Setting).filter(Setting.key == key).first()
            if setting and setting.value is not None:
                return self._cast_value(key, setting.value)

            # Fall back to environment
            env_value = getattr(self._env_settings, key, None)
            if env_value is not None:
                return env_value

            # Fall back to default
            if key in SETTINGS_MAP:
                return SETTINGS_MAP[key].default

            return None
        finally:
            self._close_db(db)

    def _cast_value(self, key: str, value: str) -> Any:
        """Cast string value to appropriate type."""
        if key not in SETTINGS_MAP:
            return value

        setting_type = SETTINGS_MAP[key].setting_type
        if setting_type == "int":
            return int(value)
        elif setting_type == "bool":
            return value.lower() in ("true", "1", "yes")
        return value

    def set(self, key: str, value: Any) -> bool:
        """
        Set a setting value in the database.

        Returns True if successful.
        """
        if key not in SETTINGS_MAP:
            logger.warning(f"Attempted to set unknown setting: {key}")
            return False

        if not SETTINGS_MAP[key].editable:
            logger.warning(f"Attempted to set non-editable setting: {key}")
            return False

        db = self._get_db()
        try:
            setting = db.query(Setting).filter(Setting.key == key).first()
            str_value = str(value) if value is not None else None

            if setting:
                setting.value = str_value
            else:
                setting = Setting(
                    key=key,
                    value=str_value,
                    description=SETTINGS_MAP[key].description,
                )
                db.add(setting)

            db.commit()
            logger.info(f"Setting updated: {key} = {value}")
            return True
        except Exception as e:
            logger.error(f"Failed to set setting {key}: {e}")
            db.rollback()
            return False
        finally:
            self._close_db(db)

    def get_all(self) -> Dict[str, Any]:
        """Get all configurable settings with their current values."""
        result = {}
        for setting_def in CONFIGURABLE_SETTINGS:
            result[setting_def.key] = {
                "value": self.get(setting_def.key),
                "description": setting_def.description,
                "type": setting_def.setting_type,
                "default": setting_def.default,
            }
        return result

    def set_multiple(self, settings: Dict[str, Any]) -> Dict[str, bool]:
        """Set multiple settings at once. Returns success status for each."""
        results = {}
        for key, value in settings.items():
            results[key] = self.set(key, value)
        return results

    def reset(self, key: str) -> bool:
        """Reset a setting to its default (remove from database)."""
        db = self._get_db()
        try:
            setting = db.query(Setting).filter(Setting.key == key).first()
            if setting:
                db.delete(setting)
                db.commit()
                logger.info(f"Setting reset to default: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to reset setting {key}: {e}")
            db.rollback()
            return False
        finally:
            self._close_db(db)


# Global instance for convenience
_settings_service: Optional[SettingsService] = None


def get_settings_service(db: Optional[Session] = None) -> SettingsService:
    """Get settings service instance."""
    global _settings_service
    if db:
        return SettingsService(db)
    if _settings_service is None:
        _settings_service = SettingsService()
    return _settings_service


def get_setting(key: str) -> Any:
    """Convenience function to get a setting value."""
    return get_settings_service().get(key)
