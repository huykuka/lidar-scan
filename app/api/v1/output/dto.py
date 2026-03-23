"""
Pydantic DTOs for the Output Node webhook API endpoints.
"""
from typing import Dict, Literal, Optional

from pydantic import BaseModel, model_validator


class WebhookConfigRequest(BaseModel):
    """Request body for PATCH /nodes/{node_id}/webhook."""

    webhook_enabled: bool = False
    webhook_url: Optional[str] = None
    webhook_auth_type: Literal["none", "bearer", "basic", "api_key"] = "none"
    webhook_auth_token: Optional[str] = None
    webhook_auth_username: Optional[str] = None
    webhook_auth_password: Optional[str] = None
    webhook_auth_key_name: Optional[str] = "X-API-Key"
    webhook_auth_key_value: Optional[str] = None
    webhook_custom_headers: Optional[Dict[str, str]] = None

    @model_validator(mode="after")
    def validate_url_when_enabled(self) -> "WebhookConfigRequest":
        if self.webhook_enabled:
            url = self.webhook_url or ""
            if not url.startswith(("http://", "https://")):
                raise ValueError(
                    "webhook_url must be a valid HTTP/HTTPS URL when webhook is enabled"
                )
        return self


class WebhookConfigResponse(BaseModel):
    """Response body for GET /nodes/{node_id}/webhook."""

    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_auth_type: str = "none"
    webhook_auth_token: Optional[str] = None
    webhook_auth_username: Optional[str] = None
    webhook_auth_password: Optional[str] = None
    webhook_auth_key_name: Optional[str] = "X-API-Key"
    webhook_auth_key_value: Optional[str] = None
    webhook_custom_headers: Optional[Dict[str, str]] = None


class WebhookUpdateResponse(BaseModel):
    """Response body for PATCH /nodes/{node_id}/webhook."""

    status: str
    node_id: str
