"""
Abstract base and data types for pluggable 3D object detection models.

Every concrete model (PointPillars, CenterPoint, …) must subclass
:class:`DetectionModel` and register itself via the :func:`register_model`
decorator so it becomes selectable in the node configuration UI.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type

import numpy as np


# ---------------------------------------------------------------------------
# Detection result
# ---------------------------------------------------------------------------

@dataclass
class Detection3D:
    """A single detected object in 3D space."""

    center: List[float]       # [x, y, z] in world coordinates
    size: List[float]         # [length, width, height]
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])  # Euler XYZ radians
    label: str = "unknown"
    score: float = 0.0        # confidence in [0, 1]
    points_in_box: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "center": self.center,
            "size": self.size,
            "rotation": self.rotation,
            "label": self.label,
            "score": round(self.score, 4),
            "points_in_box": self.points_in_box,
        }


# ---------------------------------------------------------------------------
# Abstract model interface
# ---------------------------------------------------------------------------

class DetectionModel(ABC):
    """Abstract interface that every detection backend must implement."""

    @abstractmethod
    def load(self, checkpoint_path: str, device: str = "cpu") -> None:
        """Load model weights from *checkpoint_path* onto *device* (``cpu`` or ``cuda``)."""
        ...

    @abstractmethod
    def detect(self, points: np.ndarray, **kwargs: Any) -> List[Detection3D]:
        """
        Run inference on a raw point cloud.

        Args:
            points: ``(N, C)`` numpy array.  At minimum columns 0-2 are
                    ``(x, y, z)``.  Column 3 (intensity) is used when available.
            **kwargs: Model-specific overrides (``confidence_threshold``, etc.).

        Returns:
            List of :class:`Detection3D` instances.
        """
        ...

    @property
    @abstractmethod
    def supported_classes(self) -> List[str]:
        """Return the class names this model can detect."""
        ...

    @property
    def is_loaded(self) -> bool:
        """Return ``True`` once :meth:`load` has been called successfully."""
        return False


# ---------------------------------------------------------------------------
# Model registry — maps UI-visible model names to builder callables
# ---------------------------------------------------------------------------

@dataclass
class _ModelEntry:
    name: str
    display_name: str
    builder: Callable[..., DetectionModel]
    description: str = ""

MODEL_REGISTRY: Dict[str, _ModelEntry] = {}


def register_model(
    name: str,
    *,
    display_name: str = "",
    description: str = "",
) -> Callable[[Type[DetectionModel]], Type[DetectionModel]]:
    """Decorator to register a :class:`DetectionModel` subclass."""

    def _decorator(cls: Type[DetectionModel]) -> Type[DetectionModel]:
        MODEL_REGISTRY[name] = _ModelEntry(
            name=name,
            display_name=display_name or name,
            builder=cls,
            description=description,
        )
        return cls

    return _decorator


def get_available_models() -> List[Dict[str, str]]:
    """Return list of ``{label, value}`` dicts for the UI select dropdown."""
    return [
        {"label": entry.display_name, "value": entry.name}
        for entry in MODEL_REGISTRY.values()
    ]
