"""Compatibility layer.

DB access has been refactored to a repository pattern under `app.repositories`.
These functions remain for older imports.
"""

from typing import Any, Dict, List

from app.repositories import NodeRepository


def get_lidars() -> List[Dict[str, Any]]:
    return [n for n in NodeRepository().list() if n.get("type") == "sensor"]


def save_lidar(config: Dict[str, Any]) -> str:
    config["type"] = "sensor"
    config["category"] = "Input"
    return NodeRepository().upsert(config)


def delete_lidar(lidar_id: str) -> None:
    NodeRepository().delete(lidar_id)


def get_fusions() -> List[Dict[str, Any]]:
    return [n for n in NodeRepository().list() if n.get("type") == "fusion"]


def save_fusion(config: Dict[str, Any]) -> str:
    config["type"] = "fusion"
    config["category"] = "Input"
    return NodeRepository().upsert(config)


def delete_fusion(fusion_id: str) -> None:
    NodeRepository().delete(fusion_id)
