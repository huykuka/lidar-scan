"""
Rule-based object classifier using bounding box dimensions.

Classifies detected clusters by comparing their axis-aligned bounding box
dimensions against configurable size rules. Rules are evaluated in order;
the first matching rule wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class ClassificationRule:
    """Single classification rule matching bounding box dimensions.

    All dimension constraints use the *sorted* bounding box sizes
    (smallest, medium, largest) so classification is rotation-invariant.

    Attributes:
        label: Human-readable class name (e.g. "car", "truck", "pedestrian").
        color: Hex color for the bounding box shape overlay.
        min_length: Minimum largest dimension (metres).
        max_length: Maximum largest dimension (metres).
        min_width: Minimum medium dimension (metres).
        max_width: Maximum medium dimension (metres).
        min_height: Minimum smallest dimension (metres).
        max_height: Maximum smallest dimension (metres).
        min_points: Minimum point count in cluster.
    """

    label: str
    color: str = "#00ff00"
    min_length: float = 0.0
    max_length: float = float("inf")
    min_width: float = 0.0
    max_width: float = float("inf")
    min_height: float = 0.0
    max_height: float = float("inf")
    min_points: int = 0

    def matches(self, dims: Tuple[float, float, float], point_count: int) -> bool:
        """Check if sorted dimensions (height, width, length) match this rule."""
        height, width, length = dims
        if point_count < self.min_points:
            return False
        if not (self.min_length <= length <= self.max_length):
            return False
        if not (self.min_width <= width <= self.max_width):
            return False
        if not (self.min_height <= height <= self.max_height):
            return False
        return True


@dataclass
class ClassificationResult:
    """Result of classifying a single cluster."""

    cluster_idx: int
    label: str
    confidence: float
    center: List[float]
    size: List[float]
    point_count: int
    color: str


# Default classification rules — ordered from most specific to least.
DEFAULT_RULES: List[ClassificationRule] = [
    ClassificationRule(
        label="pedestrian",
        color="#ff6600",
        min_height=1.2,
        max_height=2.2,
        min_width=0.2,
        max_width=1.0,
        min_length=0.2,
        max_length=1.0,
        min_points=20,
    ),
    ClassificationRule(
        label="car",
        color="#00aaff",
        min_height=1.0,
        max_height=2.2,
        min_width=1.4,
        max_width=2.5,
        min_length=3.0,
        max_length=6.0,
        min_points=50,
    ),
    ClassificationRule(
        label="truck",
        color="#ff0066",
        min_height=2.0,
        max_height=5.0,
        min_width=2.0,
        max_width=3.5,
        min_length=5.0,
        max_length=25.0,
        min_points=100,
    ),
    ClassificationRule(
        label="forklift",
        color="#ffcc00",
        min_height=1.5,
        max_height=3.5,
        min_width=0.8,
        max_width=2.0,
        min_length=1.5,
        max_length=4.0,
        min_points=30,
    ),
]


class ObjectClassifier:
    """Rule-based classifier for point cloud clusters.

    Args:
        rules: Ordered list of classification rules. First match wins.
        unknown_label: Label assigned when no rule matches.
        unknown_color: Color for unclassified objects.
    """

    def __init__(
        self,
        rules: Optional[List[ClassificationRule]] = None,
        unknown_label: str = "unknown",
        unknown_color: str = "#888888",
    ) -> None:
        self._rules = rules if rules is not None else DEFAULT_RULES
        self._unknown_label = unknown_label
        self._unknown_color = unknown_color

    def classify_cluster(
        self,
        points: np.ndarray,
        cluster_idx: int,
    ) -> ClassificationResult:
        """Classify a single cluster of points.

        Args:
            points: (N, 3) array of point positions for this cluster.
            cluster_idx: Index identifier for the cluster.

        Returns:
            ClassificationResult with label, dimensions, and color.
        """
        point_count = points.shape[0]
        center = points.mean(axis=0).tolist()
        bbox_min = points.min(axis=0)
        bbox_max = points.max(axis=0)
        raw_size = (bbox_max - bbox_min).tolist()

        # Sort dimensions for rotation-invariant matching
        sorted_dims = tuple(sorted(raw_size))  # (smallest, medium, largest)

        for rule in self._rules:
            if rule.matches(sorted_dims, point_count):
                return ClassificationResult(
                    cluster_idx=cluster_idx,
                    label=rule.label,
                    confidence=1.0,
                    center=center,
                    size=raw_size,
                    point_count=point_count,
                    color=rule.color,
                )

        return ClassificationResult(
            cluster_idx=cluster_idx,
            label=self._unknown_label,
            confidence=0.0,
            center=center,
            size=raw_size,
            point_count=point_count,
            color=self._unknown_color,
        )

    def classify_all(
        self,
        positions: np.ndarray,
        labels: np.ndarray,
        cluster_count: int,
    ) -> List[ClassificationResult]:
        """Classify all clusters in a labeled point cloud.

        Args:
            positions: (N, 3) point positions.
            labels: (N,) integer cluster labels (-1 = noise).
            cluster_count: Number of valid clusters (max label + 1).

        Returns:
            List of ClassificationResult for each cluster.
        """
        results: List[ClassificationResult] = []
        for i in range(cluster_count):
            mask = labels == i
            cluster_points = positions[mask]
            if cluster_points.shape[0] == 0:
                continue
            results.append(self.classify_cluster(cluster_points, i))
        return results
