"""
Output Node webhook API service layer.

Business logic for reading and updating webhook configuration of Output Nodes.
"""
from typing import Any, Dict

from fastapi import HTTPException

from app.core.logging import get_logger
from app.repositories import NodeRepository
from app.services.nodes.instance import node_manager
from .dto import WebhookConfigRequest, WebhookConfigResponse, WebhookUpdateResponse

logger = get_logger(__name__)

# Webhook-related config keys (used for reading defaults)
_WEBHOOK_KEYS = [
    "webhook_enabled",
    "webhook_url",
    "webhook_auth_type",
    "webhook_auth_token",
    "webhook_auth_username",
    "webhook_auth_password",
    "webhook_auth_key_name",
    "webhook_auth_key_value",
    "webhook_custom_headers",
]

_WEBHOOK_DEFAULTS: Dict[str, Any] = {
    "webhook_enabled": False,
    "webhook_url": "",
    "webhook_auth_type": "none",
    "webhook_auth_token": None,
    "webhook_auth_username": None,
    "webhook_auth_password": None,
    "webhook_auth_key_name": "X-API-Key",
    "webhook_auth_key_value": None,
    "webhook_custom_headers": None,
}


def _get_output_node_or_raise(node_id: str) -> Dict[str, Any]:
    """
    Fetch node from DB; raise 404 if missing, 400 if wrong type.

    Returns the node dict.
    """
    repo = NodeRepository()
    node = repo.get_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
    if node.get("type") != "output_node":
        raise HTTPException(
            status_code=400,
            detail=f"Node {node_id} is not an output_node",
        )
    return node


async def get_webhook_config(node_id: str) -> WebhookConfigResponse:
    """
    Return current webhook configuration for an Output Node.

    Reads from the node's config_json blob, applying defaults for any
    missing keys (e.g., a freshly created node with no webhook settings).
    """
    node = _get_output_node_or_raise(node_id)
    config: Dict[str, Any] = node.get("config") or {}

    data: Dict[str, Any] = {}
    for key in _WEBHOOK_KEYS:
        value = config.get(key)
        data[key] = value if value is not None else _WEBHOOK_DEFAULTS[key]

    # Normalize webhook_url: never return None
    data["webhook_url"] = data.get("webhook_url") or ""

    return WebhookConfigResponse(**data)


async def update_webhook_config(
    node_id: str, req: WebhookConfigRequest
) -> WebhookUpdateResponse:
    """
    Persist updated webhook configuration and hot-reload the running node instance.

    Merges webhook fields into the existing config_json (preserves non-webhook
    fields such as pose). Updates the in-memory OutputNode instance if running.
    """
    node = _get_output_node_or_raise(node_id)

    # Merge webhook fields into existing config
    existing_config: Dict[str, Any] = dict(node.get("config") or {})
    webhook_fields = req.model_dump()
    existing_config.update(webhook_fields)

    # Persist to DB
    repo = NodeRepository()
    try:
        repo.update_node_config(node_id, existing_config)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Hot-reload running instance (if DAG is active)
    node_instance = node_manager.nodes.get(node_id)
    if node_instance is not None and hasattr(node_instance, "_rebuild_webhook"):
        node_instance._rebuild_webhook(existing_config)
        logger.info(f"OutputNode {node_id}: webhook config hot-reloaded")
    else:
        logger.debug(
            f"OutputNode {node_id}: node not running; webhook config persisted to DB only"
        )

    return WebhookUpdateResponse(status="ok", node_id=node_id)
