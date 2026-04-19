"""
Shape Pydantic models for 3D shape overlay rendering.

These models define the data contract for shapes broadcast over the 'shapes'
WebSocket topic. IDs are assigned by NodeManager before broadcast.
"""
from __future__ import annotations

import hashlib
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


class _BaseShape(BaseModel):
    id: str = ""          # filled by NodeManager before broadcast
    node_name: str = ""   # filled by NodeManager before broadcast
    type: str

    model_config = {"extra": "forbid"}


class CubeShape(_BaseShape):
    type: Literal["cube"] = "cube"
    center: List[float]          # [x, y, z] world units
    size: List[float]            # [sx, sy, sz] world units
    rotation: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])  # Euler XYZ radians
    color: str = "#00ff00"
    opacity: float = 0.4
    wireframe: bool = True
    label: Optional[str] = None


class PlaneShape(_BaseShape):
    type: Literal["plane"] = "plane"
    center: List[float]          # [x, y, z]
    normal: List[float]          # [nx, ny, nz] unit vector
    width: float = 10.0
    height: float = 10.0
    color: str = "#4488ff"
    opacity: float = 0.25


class LabelShape(_BaseShape):
    type: Literal["label"] = "label"
    position: List[float]        # [x, y, z]
    text: str
    font_size: int = 14
    color: str = "#ffffff"
    background_color: str = "#000000cc"
    scale: float = 1.0


ShapePayload = Union[CubeShape, PlaneShape, LabelShape]


class ShapeFrame(BaseModel):
    """Published to WS topic 'shapes' every frame."""
    timestamp: float
    shapes: List[ShapePayload]


def _geometry_key(shape: ShapePayload) -> str:
    """Compute a deterministic geometry key for a shape, used for stable ID hashing."""
    if isinstance(shape, CubeShape):
        parts = [str(round(v, 3)) for v in shape.center + shape.size]
        return "|".join(parts)
    elif isinstance(shape, PlaneShape):
        parts = [str(round(v, 3)) for v in shape.center + shape.normal]
        return "|".join(parts)
    elif isinstance(shape, LabelShape):
        parts = [str(round(v, 3)) for v in shape.position]
        return "|".join(parts) + "|" + shape.text
    else:
        # Fallback for unknown shape types
        return shape.model_dump_json()


def compute_shape_id(node_id: str, shape: ShapePayload) -> str:
    """
    Compute a stable 16-character hex ID for a shape.

    Strategy: sha256(node_id + "|" + shape.type + "|" + geometry_key)[:16]
    Same geometry from the same node always produces the same id (idempotent).
    """
    geometry_key = _geometry_key(shape)
    raw = f"{node_id}|{shape.type}|{geometry_key}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
