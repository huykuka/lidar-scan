"""Configuration-related schema models for import/export operations."""

from typing import List
from pydantic import BaseModel


class ImportSummary(BaseModel):
    """Summary counts for configuration import."""
    nodes: int
    edges: int


class ImportResponse(BaseModel):
    """Response for configuration import operations."""
    success: bool
    mode: str
    imported: ImportSummary
    node_ids: List[str]
    reloaded: bool


class ConfigValidationSummary(BaseModel):
    """Summary counts for configuration validation."""
    nodes: int
    edges: int


class ValidationResponse(BaseModel):
    """Response for configuration validation operations."""
    valid: bool
    errors: List[str]
    warnings: List[str]
    summary: ConfigValidationSummary