"""Compatibility layer.

DB access has been refactored to a repository pattern under `app.repositories`.
These functions remain for older imports.
"""

from typing import Any, Dict, List

from app.repositories import FusionRepository, LidarRepository


def get_lidars() -> List[Dict[str, Any]]:
    return LidarRepository().list()


def save_lidar(config: Dict[str, Any]) -> str:
    return LidarRepository().upsert(config)


def delete_lidar(lidar_id: str) -> None:
    LidarRepository().delete(lidar_id)


def get_fusions() -> List[Dict[str, Any]]:
    return FusionRepository().list()


def save_fusion(config: Dict[str, Any]) -> str:
    return FusionRepository().upsert(config)


def delete_fusion(fusion_id: str) -> None:
    FusionRepository().delete(fusion_id)
