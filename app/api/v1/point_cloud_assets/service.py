"""Point cloud assets service — upload, list, preview and delete reference clouds."""

import asyncio

from fastapi import HTTPException, UploadFile

from app.core.logging import get_logger
from app.modules.matching.store import (
    AssetError, AssetNotFound, SUPPORTED_EXTENSIONS, parse_point_cloud_bytes, reference_store,
)

logger = get_logger(__name__)

MAX_UPLOAD_BYTES = 200 * 1024 * 1024


def _not_found(asset_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")


async def upload_asset(file: UploadFile, name: str | None) -> dict:
    filename = file.filename or "upload"
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum is {MAX_UPLOAD_BYTES} bytes.")
    try:
        points = await asyncio.to_thread(parse_point_cloud_bytes, raw, filename)
        return await asyncio.to_thread(reference_store.create, name or "", filename, points, len(raw))
    except AssetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def list_assets() -> dict:
    assets = reference_store.list()
    return {"assets": assets, "count": len(assets)}


def get_asset(asset_id: str) -> dict:
    try:
        return reference_store.get(asset_id)
    except AssetNotFound:
        raise _not_found(asset_id) from None


def rename_asset(asset_id: str, name: str) -> dict:
    try:
        return reference_store.rename(asset_id, name)
    except AssetNotFound:
        raise _not_found(asset_id) from None
    except AssetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def delete_asset(asset_id: str) -> None:
    try:
        reference_store.delete(asset_id)
    except AssetNotFound:
        raise _not_found(asset_id) from None


def preview_asset(asset_id: str, max_points: int) -> dict:
    try:
        meta = reference_store.get(asset_id)
        pts = reference_store.preview(asset_id, max_points)
    except AssetNotFound:
        raise _not_found(asset_id) from None
    return {
        "id": asset_id,
        "total_points": meta["point_count"],
        "returned_points": int(len(pts)),
        "points": pts.tolist(),
    }


def supported_extensions() -> list[str]:
    return list(SUPPORTED_EXTENSIONS)
