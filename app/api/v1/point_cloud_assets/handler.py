"""Point cloud assets router — manage reference clouds used by the matching node."""

from typing import Optional

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from . import service
from .dto import PointCloudAsset, PointCloudAssetList, PointCloudPreview, RenameRequest

router = APIRouter(prefix="/point-cloud-assets", tags=["Point Cloud Assets"])


@router.post(
    "",
    response_model=PointCloudAsset,
    status_code=status.HTTP_201_CREATED,
    responses={400: {"description": "Unsupported or invalid point cloud file"},
               413: {"description": "Uploaded file exceeds size limit"}},
    summary="Upload Point Cloud Asset",
    description="Upload a .pcd/.ply/.xyz/.xyzn/.xyzrgb/.pts/.npy file (multipart/form-data) as a reusable reference cloud.",
)
async def upload_point_cloud_asset(file: UploadFile = File(...), name: Optional[str] = Form(None)):
    return await service.upload_asset(file, name)


@router.get("", response_model=PointCloudAssetList, summary="List Point Cloud Assets")
async def list_point_cloud_assets():
    return service.list_assets()


@router.get("/{asset_id}", response_model=PointCloudAsset, summary="Get Point Cloud Asset")
async def get_point_cloud_asset(asset_id: str):
    return service.get_asset(asset_id)


@router.patch("/{asset_id}", response_model=PointCloudAsset, summary="Rename Point Cloud Asset")
async def rename_point_cloud_asset(asset_id: str, body: RenameRequest):
    return service.rename_asset(asset_id, body.name)


@router.get("/{asset_id}/preview", response_model=PointCloudPreview, summary="Preview Point Cloud Asset")
async def preview_point_cloud_asset(asset_id: str, max_points: int = Query(20000, ge=100, le=200000)):
    return service.preview_asset(asset_id, max_points)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Point Cloud Asset")
async def delete_point_cloud_asset(asset_id: str):
    service.delete_asset(asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
