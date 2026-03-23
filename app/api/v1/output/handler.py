"""
Output Node API router — webhook configuration endpoints.
"""
from fastapi import APIRouter

from .dto import WebhookConfigResponse, WebhookUpdateResponse, WebhookConfigRequest
from .service import get_webhook_config, update_webhook_config

router = APIRouter(tags=["Output Node"])


@router.get(
    "/nodes/{node_id}/webhook",
    response_model=WebhookConfigResponse,
    responses={
        404: {"description": "Node not found"},
        400: {"description": "Node is not an output_node"},
    },
    summary="Get Webhook Configuration",
    description="Returns the current webhook configuration for an Output Node.",
)
async def get_webhook_config_endpoint(node_id: str) -> WebhookConfigResponse:
    return await get_webhook_config(node_id)


@router.patch(
    "/nodes/{node_id}/webhook",
    response_model=WebhookUpdateResponse,
    responses={
        404: {"description": "Node not found"},
        400: {"description": "Node is not an output_node or validation failed"},
        422: {"description": "Invalid webhook configuration"},
    },
    summary="Update Webhook Configuration",
    description=(
        "Updates webhook configuration for an Output Node. "
        "Persists to DB and hot-reloads the running node instance without a full DAG reload."
    ),
)
async def update_webhook_config_endpoint(
    node_id: str, req: WebhookConfigRequest
) -> WebhookUpdateResponse:
    return await update_webhook_config(node_id, req)
