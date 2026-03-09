"""Log-related schema models for application logging."""

from pydantic import BaseModel


class LogEntry(BaseModel):
    """Single application log entry."""
    timestamp: str
    level: str
    module: str
    message: str