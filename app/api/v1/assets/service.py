"""Assets endpoint handlers - Pure business logic without routing configuration."""

import os
from typing import List
from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

_ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.svg', '.webp'}

_MEDIA_TYPE_MAP = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.webp': 'image/webp',
}


class ThumbnailItem(BaseModel):
    """Individual thumbnail file information."""
    filename: str
    url: str
    size: int


class ThumbnailListResponse(BaseModel):
    """Response for listing thumbnail files."""
    thumbnails: List[ThumbnailItem]
    count: int
    assets_dir: str


def _resolve_module_assets_dir(module: str) -> str:
    """Return the absolute assets directory for a given module name."""
    return os.path.abspath(os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..",
        "modules", module, "assets",
    ))


async def _get_thumbnail(module: str, filename: str) -> FileResponse:
    """Serve a device thumbnail image from *module*/assets/."""
    file_ext = os.path.splitext(filename)[1].lower()

    if file_ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}",
        )

    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    assets_dir = _resolve_module_assets_dir(module)
    file_path = os.path.join(assets_dir, filename)

    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail=f"Thumbnail '{filename}' not found")

    if not file_path.startswith(assets_dir):
        raise HTTPException(status_code=400, detail="Invalid file path")

    return FileResponse(
        path=file_path,
        media_type=_MEDIA_TYPE_MAP.get(file_ext, 'application/octet-stream'),
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Content-Source": f"{module}-thumbnails",
        },
    )


async def _list_thumbnails(module: str, url_prefix: str) -> ThumbnailListResponse:
    """List available thumbnail files for a module."""
    assets_dir = _resolve_module_assets_dir(module)

    if not os.path.exists(assets_dir):
        return ThumbnailListResponse(thumbnails=[], count=0, assets_dir=assets_dir)

    thumbnails: List[ThumbnailItem] = []
    try:
        for filename in os.listdir(assets_dir):
            if os.path.splitext(filename)[1].lower() in _ALLOWED_EXTENSIONS:
                file_path = os.path.join(assets_dir, filename)
                if os.path.isfile(file_path):
                    thumbnails.append(ThumbnailItem(
                        filename=filename,
                        url=f"{url_prefix}{filename}",
                        size=os.path.getsize(file_path),
                    ))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading thumbnails directory: {str(e)}")

    return ThumbnailListResponse(
        thumbnails=sorted(thumbnails, key=lambda x: x.filename),
        count=len(thumbnails),
        assets_dir=assets_dir,
    )


# --- Public wrappers (kept for backward-compatible imports) ---

async def get_lidar_thumbnail(filename: str) -> FileResponse:
    return await _get_thumbnail("lidar", filename)


async def list_lidar_thumbnails() -> ThumbnailListResponse:
    return await _list_thumbnails("lidar", "/api/v1/assets/lidar/")


async def get_visionary_thumbnail(filename: str) -> FileResponse:
    return await _get_thumbnail("visionary", filename)


async def list_visionary_thumbnails() -> ThumbnailListResponse:
    return await _list_thumbnails("visionary", "/api/v1/assets/visionary/")