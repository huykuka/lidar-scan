"""Configuration router configuration and endpoint metadata."""

from fastapi import APIRouter
from app.api.v1.schemas.config import ImportResponse, ValidationResponse
from .handlers import export_configuration, import_configuration, validate_configuration, ConfigurationImport


# Router configuration
router = APIRouter(tags=["Configuration"])

# Endpoint configurations
@router.get(
    "/config/export",
    responses={200: {"description": "Downloadable JSON file", "content": {"application/json": {}}}},
    summary="Export Configuration",
    description="Export all node and edge configurations as JSON file.",
)
def config_export_endpoint():
    return export_configuration()


@router.post(
    "/config/import",
    response_model=ImportResponse,
    responses={400: {"description": "Invalid configuration"}},
    summary="Import Configuration", 
    description="Import node and edge configurations from JSON.",
)
async def config_import_endpoint(config: ConfigurationImport):
    return await import_configuration(config)


@router.post(
    "/config/validate",
    response_model=ValidationResponse,
    summary="Validate Configuration",
    description="Validate a node configuration without importing it.",
)
def config_validate_endpoint(config: ConfigurationImport):
    return validate_configuration(config)