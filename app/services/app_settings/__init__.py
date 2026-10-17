"""Runtime application settings persisted in the database.

Values from the ``app_settings`` table are applied onto ``app.core.config.settings`` so existing
code that reads ``settings.X`` keeps working and sees edits immediately.
"""

import json
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import AppSettingModel
from app.db.session import SessionLocal

from . import crypto
from .registry import BY_KEY, CATEGORIES, SETTINGS, coerce

__all__ = ["load_overrides", "get_all", "update", "SettingsValidationError"]

logger = get_logger(__name__)

# Env/default values captured before any override is applied, so a reset can restore them.
_DEFAULTS: dict[str, Any] = {d.key: getattr(settings, d.key) for d in SETTINGS}


class SettingsValidationError(Exception):
    def __init__(self, errors: dict[str, str]):
        super().__init__("Invalid settings")
        self.errors = errors


def _backends() -> list[str]:
    from app.services.blob_storage.registry import available_backends

    return available_backends()


def _apply(key: str, value: Any) -> None:
    setattr(settings, key, value)
    if key.startswith("UPLOAD_"):
        from app.services import blob_storage

        blob_storage.invalidate_status_cache()
    elif key == "APP_LOG_LEVEL":
        from app.core.logging import set_log_level

        set_log_level(value)


# Keys renamed to <CATEGORY>_<NAME>; rows saved under the old name are moved on startup.
LEGACY_KEYS: dict[str, str] = {
    "STORAGE_BACKEND": "UPLOAD_BACKEND",
    "STORAGE_AUTO_UPLOAD": "UPLOAD_AUTO",
    "STORAGE_MAX_CONCURRENT_UPLOADS": "UPLOAD_MAX_CONCURRENT",
    "STORAGE_UPLOAD_TIMEOUT_MINUTES": "UPLOAD_TIMEOUT_MINUTES",
    "S3_ENDPOINT_URL": "UPLOAD_S3_ENDPOINT_URL",
    "S3_ACCESS_KEY_ID": "UPLOAD_S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY": "UPLOAD_S3_SECRET_ACCESS_KEY",
    "S3_BUCKET": "UPLOAD_S3_BUCKET",
    "S3_REGION": "UPLOAD_S3_REGION",
    "S3_KEY_PREFIX": "UPLOAD_S3_KEY_PREFIX",
    "RECORDINGS_RETENTION_DAYS": "RETENTION_RECORDINGS_DAYS",
}


def _migrate_legacy_keys(db) -> None:
    for old, new in LEGACY_KEYS.items():
        row = db.get(AppSettingModel, old)
        if row is None:
            continue
        if db.get(AppSettingModel, new) is None:
            db.add(AppSettingModel(key=new, value_json=row.value_json, updated_at=row.updated_at))
        db.delete(row)
    db.commit()


def load_overrides() -> None:
    """Apply persisted overrides at startup. Bad rows are skipped, never fatal."""
    db = SessionLocal()
    try:
        _migrate_legacy_keys(db)
        for row in db.query(AppSettingModel).all():
            defn = BY_KEY.get(row.key)
            if defn is None:
                continue
            try:
                value = json.loads(row.value_json)
                # Values saved before a setting became a secret are plain text; they are
                # re-encrypted the next time that setting is saved.
                if defn.type == "secret" and isinstance(value, str) and value.startswith(crypto.PREFIX):
                    value = crypto.decrypt(value)
                _apply(row.key, value)
            except Exception as exc:
                logger.warning("Ignoring invalid stored setting %s: %s", row.key, exc)
    finally:
        db.close()


def _overridden_keys() -> dict[str, str]:
    db = SessionLocal()
    try:
        return {r.key: r.updated_at for r in db.query(AppSettingModel).all()}
    finally:
        db.close()


def get_all() -> dict:
    """Categories with their settings and current values. Secrets are never included."""
    overridden = _overridden_keys()
    backends = _backends()
    categories = []
    for cat in CATEGORIES:
        items = []
        for d in (s for s in SETTINGS if s.category == cat.id):
            current = getattr(settings, d.key)
            item = {
                "key": d.key,
                "label": d.label,
                "type": d.type,
                "description": d.description,
                "placeholder": d.placeholder,
                "unit": d.unit,
                "min": d.min,
                "max": d.max,
                "depends_on": d.depends_on,
                "options": (list(d.options) or backends) if d.type == "select" else None,
                "value": None if d.type == "secret" else current,
                "is_set": bool(current) if d.type == "secret" else None,
                "default": None if d.type == "secret" else _DEFAULTS[d.key],
                "modified": d.key in overridden,
            }
            items.append(item)
        categories.append({"id": cat.id, "label": cat.label, "icon": cat.icon,
                           "description": cat.description, "settings": items})
    return {"categories": categories, "encryption_available": crypto.is_available(),
            "encryption_error": crypto.unavailable_reason()}


def update(values: dict[str, Any], reset: list[str] | None = None) -> dict:
    """Validate and persist ``values``; ``reset`` reverts keys to their env default.

    For secrets, a missing key keeps the stored value and an empty string clears it.
    """
    reset = reset or []
    errors: dict[str, str] = {}
    backends = _backends()
    clean: dict[str, Any] = {}

    for key, raw in values.items():
        defn = BY_KEY.get(key)
        if defn is None:
            errors[key] = "Unknown setting"
            continue
        try:
            clean[key] = coerce(defn, raw, backends)
        except ValueError as exc:
            errors[key] = str(exc)
    secret_keys = [k for k in clean if BY_KEY[k].type == "secret" and clean[k]]
    if secret_keys and not crypto.is_available():
        for key in secret_keys:
            errors[key] = f"Cannot store secrets: {crypto.unavailable_reason()}"
    for key in reset:
        if key not in BY_KEY:
            errors[key] = "Unknown setting"
    if errors:
        raise SettingsValidationError(errors)

    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        for key, value in clean.items():
            stored = crypto.encrypt(value) if BY_KEY[key].type == "secret" and value else value
            row = db.get(AppSettingModel, key)
            if row is None:
                db.add(AppSettingModel(key=key, value_json=json.dumps(stored), updated_at=now))
            else:
                row.value_json = json.dumps(stored)
                row.updated_at = now
        for key in reset:
            row = db.get(AppSettingModel, key)
            if row is not None:
                db.delete(row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    for key, value in clean.items():
        _apply(key, value)
    for key in reset:
        _apply(key, _DEFAULTS[key])
    return get_all()
