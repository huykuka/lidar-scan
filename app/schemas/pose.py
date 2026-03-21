"""Canonical 6-DOF sensor pose Pydantic V2 model.

Position fields (x, y, z) are in millimeters.
Angle fields (roll, pitch, yaw) are in degrees, range [-180, +180].
"""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# --- Custom annotated types ---

PoseFloat = Annotated[float, Field(allow_inf_nan=False)]
"""Finite float, no range constraint. Used for position (mm)."""

AngleDeg = Annotated[float, Field(ge=-180.0, le=180.0, allow_inf_nan=False)]
"""Finite float in degrees [-180, +180]. Used for rotation axes."""


class Pose(BaseModel):
    """Canonical 6-DOF sensor pose.

    Position (x, y, z) in millimeters.
    Rotation (roll, pitch, yaw) in degrees [-180, +180].

    The model is **frozen** (immutable) to prevent accidental mutation inside
    DAG pipelines and to ensure hashability.
    """

    model_config = ConfigDict(frozen=True)

    x: PoseFloat = 0.0      # mm — translation along X axis
    y: PoseFloat = 0.0      # mm — translation along Y axis
    z: PoseFloat = 0.0      # mm — translation along Z axis
    roll: AngleDeg = 0.0    # degrees — rotation around X axis
    pitch: AngleDeg = 0.0   # degrees — rotation around Y axis
    yaw: AngleDeg = 0.0     # degrees — rotation around Z axis

    @classmethod
    def zero(cls) -> "Pose":
        """Return a zero-pose instance (all fields = 0.0)."""
        return cls()

    def to_flat_dict(self) -> dict[str, float]:
        """Return a flat ``{x, y, z, roll, pitch, yaw}`` dict.

        Useful for backward-compatible calls such as
        ``create_transformation_matrix(**pose.to_flat_dict())``.
        """
        return self.model_dump()
