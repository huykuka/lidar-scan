"""
Static assets API endpoints for self-contained LiDAR module.

Serves device thumbnails directly from the LiDAR module assets directory,
maintaining a clean self-contained modular architecture.
"""
import os
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/assets", tags=["Assets"])


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


@router.get("/lidar/{filename}", responses={
    200: {"description": "Thumbnail image", "content": {"image/png": {}}},
    400: {"description": "Invalid filename or unsupported file type"},
    404: {"description": "Thumbnail not found"}
})
async def get_lidar_thumbnail(filename: str):
    """
    Serve LiDAR device thumbnail images.
    
    Args:
        filename: The thumbnail filename (e.g., "multiscan.png", "tim5xx.png")
    
    Returns:
        FileResponse with the requested image
        
    Raises:
        HTTPException(404): If the thumbnail file is not found
    """
    # Security: Only allow specific file extensions
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.svg', '.webp'}
    file_ext = os.path.splitext(filename)[1].lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Security: Prevent directory traversal
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(
            status_code=400,
            detail="Invalid filename"
        )
    
    # Construct the file path
    # Assets are stored in app/modules/lidar/assets/
    assets_dir = os.path.join(
        os.path.dirname(__file__),  # app/api/v1/
        "..", "..",                 # app/
        "modules", "lidar", "assets"
    )
    assets_dir = os.path.abspath(assets_dir)
    file_path = os.path.join(assets_dir, filename)
    
    # Verify the file exists
    if not os.path.isfile(file_path):
        raise HTTPException(
            status_code=404,
            detail=f"Thumbnail '{filename}' not found"
        )
    
    # Security: Ensure the resolved path is still within the assets directory
    if not file_path.startswith(assets_dir):
        raise HTTPException(
            status_code=400,
            detail="Invalid file path"
        )
    
    # Determine media type
    media_type_map = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg', 
        '.jpeg': 'image/jpeg',
        '.svg': 'image/svg+xml',
        '.webp': 'image/webp'
    }
    media_type = media_type_map.get(file_ext, 'application/octet-stream')
    
    return FileResponse(
        path=file_path,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            "X-Content-Source": "lidar-thumbnails"
        }
    )


@router.get("/lidar/", response_model=ThumbnailListResponse, responses={
    500: {"description": "Error reading assets directory"}
})
async def list_lidar_thumbnails():
    """
    List available LiDAR thumbnail files.
    
    Returns:
        List of available thumbnail filenames
    """
    assets_dir = os.path.join(
        os.path.dirname(__file__),
        "..", "..", 
        "modules", "lidar", "assets"
    )
    assets_dir = os.path.abspath(assets_dir)
    
    if not os.path.exists(assets_dir):
        return ThumbnailListResponse(
            thumbnails=[],
            count=0,
            assets_dir=assets_dir
        )
    
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.svg', '.webp'}
    thumbnails = []
    
    try:
        for filename in os.listdir(assets_dir):
            if os.path.splitext(filename)[1].lower() in allowed_extensions:
                file_path = os.path.join(assets_dir, filename)
                if os.path.isfile(file_path):
                    thumbnails.append(ThumbnailItem(
                        filename=filename,
                        url=f"/api/v1/assets/lidar/{filename}",
                        size=os.path.getsize(file_path)
                    ))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reading thumbnails directory: {str(e)}"
        )
    
    return ThumbnailListResponse(
        thumbnails=sorted(thumbnails, key=lambda x: x.filename),
        count=len(thumbnails),
        assets_dir=assets_dir
    )