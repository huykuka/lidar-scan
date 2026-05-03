"""PCD Injection service — business logic for parsing and injecting PCD uploads."""

from typing import Any

import numpy as np
import open3d as o3d
from fastapi import HTTPException, UploadFile

from app.core.logging import get_logger
from app.modules.pcd_injection.node import PcdInjectionNode
from app.services.nodes.instance import node_manager

logger = get_logger(__name__)

# Maximum upload size: 50 MB (generous for large point clouds)
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _get_injection_node(node_id: str) -> PcdInjectionNode:
    """Resolve a running PcdInjectionNode instance or raise HTTP 404/400."""
    node: Any = node_manager.nodes.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found in running DAG")
    if not isinstance(node, PcdInjectionNode):
        raise HTTPException(
            status_code=400,
            detail=f"Node '{node_id}' is not a PCD Injection node (type: {type(node).__name__})",
        )
    return node


async def parse_pcd_upload(file: UploadFile) -> np.ndarray:
    """Read an uploaded PCD file and return an (N, 3) float64 array.

    Supports ASCII and binary PCD formats via Open3D.

    Args:
        file: The uploaded PCD file from a multipart request.

    Returns:
        Numpy array of shape (N, 3) with XYZ coordinates.

    Raises:
        HTTPException: On file-size violations, parse errors, or empty clouds.
    """
    if file.content_type and file.content_type not in (
        "application/octet-stream",
        "application/x-pcd",
        "text/plain",
    ):
        logger.warning("Unexpected content-type for PCD upload: %s", file.content_type)

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(raw)} bytes). Maximum is {MAX_UPLOAD_BYTES} bytes.",
        )
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    import tempfile, os, asyncio
    tmp_path: str = ""
    try:
        # Open3D requires a file path — write to a temporary file
        fd, tmp_path = tempfile.mkstemp(suffix=".pcd")
        os.write(fd, raw)
        os.close(fd)

        pcd: o3d.geometry.PointCloud = await asyncio.to_thread(o3d.io.read_point_cloud, tmp_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse PCD file: {exc}") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    points = np.asarray(pcd.points)
    if points.size == 0:
        raise HTTPException(status_code=400, detail="PCD file contains no points")

    return points


async def inject_pcd(node_id: str, file: UploadFile) -> dict:
    """Full pipeline: validate node, parse PCD, inject into DAG.

    Returns:
        Dict matching PcdInjectionResponse schema.
    """
    node = _get_injection_node(node_id)
    points = await parse_pcd_upload(file)
    count = await node.inject_points(points)

    return {
        "node_id": node_id,
        "points_injected": count,
        "message": "ok",
    }
