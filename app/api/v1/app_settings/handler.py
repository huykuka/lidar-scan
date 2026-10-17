"""Application settings HTTP handlers (service users only)."""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.v1.auth.dependencies import roles_required
from app.services import app_settings, blob_storage

router = APIRouter(prefix="/app-settings", tags=["App Settings"])


class UpdateSettingsRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict, description="Setting key -> new value")
    reset: list[str] = Field(default_factory=list, description="Keys to revert to their default")


@router.get("", summary="Get Settings", description="All settings grouped by category. Secrets are never returned.")
@roles_required("service")
async def get_settings():
    return await asyncio.to_thread(app_settings.get_all)


@router.put("", summary="Update Settings", description="Validate and persist settings; takes effect immediately.")
@roles_required("service")
async def update_settings(body: UpdateSettingsRequest):
    try:
        return await asyncio.to_thread(app_settings.update, body.values, body.reset)
    except app_settings.SettingsValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors)


@router.post("/storage/test", summary="Test Storage Connection",
             description="Check the saved storage credentials against the provider.")
@roles_required("service")
async def test_storage():
    status = await blob_storage.get_status(force=True)
    return {
        "configured": status.configured,
        "authenticated": status.authenticated,
        "backend": status.backend,
        "bucket": status.bucket,
        "reason": status.reason,
    }
