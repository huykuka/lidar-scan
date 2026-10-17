"""Declarative list of the settings editable from the UI.

Each definition maps a key to an attribute of ``app.core.config.settings``. The env value is the
default; a row in the ``app_settings`` table overrides it. To expose a new setting, add it to
``Settings`` in ``app/core/config.py`` and declare it here.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

SettingType = Literal["bool", "int", "string", "select", "secret"]


@dataclass(frozen=True)
class SettingDef:
    key: str
    category: str
    label: str
    type: SettingType
    description: str = ""
    placeholder: str = ""
    unit: str | None = None
    min: int | None = None
    max: int | None = None
    #: only shown/used when ``depends_on`` (a bool setting key) is true
    depends_on: str | None = None
    options: tuple[str, ...] = field(default_factory=tuple)

    @property
    def attr(self) -> str:
        return self.key


@dataclass(frozen=True)
class CategoryDef:
    id: str
    label: str
    icon: str
    description: str


CATEGORIES: tuple[CategoryDef, ...] = (
    CategoryDef("storage", "Storage", "cloud", "Where recordings are stored outside this machine and when they are uploaded."),
    CategoryDef("retention", "Data Retention", "auto_delete", "How long recordings are kept on this machine."),
)

SETTINGS: tuple[SettingDef, ...] = (
    SettingDef("STORAGE_BACKEND", "storage", "Storage provider", "select",
               "Strategy used to store uploaded recordings."),
    SettingDef("S3_ENDPOINT_URL", "storage", "Endpoint URL", "string",
               "Leave empty for AWS S3. Set for MinIO or other S3-compatible services.",
               placeholder="http://localhost:9000"),
    SettingDef("S3_BUCKET", "storage", "Bucket", "string", placeholder="lidar-recordings"),
    SettingDef("S3_REGION", "storage", "Region", "string", placeholder="us-east-1"),
    SettingDef("S3_KEY_PREFIX", "storage", "Folder prefix", "string",
               "Objects are named <prefix>/<recording name>_<date>.mcap.", placeholder="recordings"),
    SettingDef("S3_ACCESS_KEY_ID", "storage", "Access key ID", "secret",
               "Stored encrypted. Never returned by the API."),
    SettingDef("S3_SECRET_ACCESS_KEY", "storage", "Secret access key", "secret",
               "Stored in the application database. Never returned by the API."),
    SettingDef("STORAGE_AUTO_UPLOAD", "storage", "Upload new recordings automatically", "bool",
               "Requires valid storage credentials. Each recording is uploaded as soon as it is saved."),
    SettingDef("RECORDINGS_RETENTION_DAYS", "retention", "Delete recordings older than", "int",
               "0 keeps recordings forever. The check runs hourly.", unit="days", min=0, max=3650),
    SettingDef("RETENTION_ONLY_UPLOADED", "retention", "Only delete uploaded recordings", "bool",
               "Safety net: recordings that were never uploaded are kept.",
               depends_on="RECORDINGS_RETENTION_DAYS"),
)

BY_KEY: dict[str, SettingDef] = {s.key: s for s in SETTINGS}


def coerce(defn: SettingDef, raw: Any, backends: list[str]) -> Any:
    """Validate/convert an incoming value. Raises ValueError with a user-facing message."""
    if defn.type == "bool":
        if not isinstance(raw, bool):
            raise ValueError("must be true or false")
        return raw
    if defn.type == "int":
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ValueError("must be a whole number")
        if defn.min is not None and raw < defn.min:
            raise ValueError(f"must be at least {defn.min}")
        if defn.max is not None and raw > defn.max:
            raise ValueError(f"must be at most {defn.max}")
        return raw
    if not isinstance(raw, str):
        raise ValueError("must be text")
    value = raw.strip()
    if defn.type == "select":
        if value.lower() not in backends:
            raise ValueError(f"must be one of: {', '.join(backends)}")
        return value.lower()
    return value
