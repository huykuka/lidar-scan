"""Assets router configuration and endpoint metadata."""

from fastapi import APIRouter
from .service import (
    get_lidar_thumbnail, list_lidar_thumbnails,
    get_visionary_thumbnail, list_visionary_thumbnails,
    ThumbnailListResponse,
)


# Router configuration
router = APIRouter(prefix="/assets", tags=["Assets"])

# --- LiDAR endpoints ---

@router.get(
    "/lidar/{filename}",
    responses={
        200: {"description": "Thumbnail image", "content": {"image/png": {}}},
        400: {"description": "Invalid filename or unsupported file type"},
        404: {"description": "Thumbnail not found"}
    },
    summary="Get LiDAR Thumbnail",
    description="Serve LiDAR device thumbnail images by filename.",
)
async def lidar_thumbnail_endpoint(filename: str):
    return await get_lidar_thumbnail(filename)


@router.get(
    "/lidar/",
    response_model=ThumbnailListResponse,
    responses={500: {"description": "Error reading assets directory"}},
    summary="List LiDAR Thumbnails",
    description="List all available LiDAR thumbnail files in the assets directory.",
)
async def lidar_thumbnails_list_endpoint():
    return await list_lidar_thumbnails()


# --- Visionary endpoints ---

@router.get(
    "/visionary/{filename}",
    responses={
        200: {"description": "Thumbnail image", "content": {"image/png": {}}},
        400: {"description": "Invalid filename or unsupported file type"},
        404: {"description": "Thumbnail not found"}
    },
    summary="Get Visionary Thumbnail",
    description="Serve Visionary camera thumbnail images by filename.",
)
async def visionary_thumbnail_endpoint(filename: str):
    return await get_visionary_thumbnail(filename)


@router.get(
    "/visionary/",
    response_model=ThumbnailListResponse,
    responses={500: {"description": "Error reading assets directory"}},
    summary="List Visionary Thumbnails",
    description="List all available Visionary thumbnail files in the assets directory.",
)
async def visionary_thumbnails_list_endpoint():
    return await list_visionary_thumbnails()