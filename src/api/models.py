import base64
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# Supported image media types matching original Dify flow
SUPPORTED_IMAGE_TYPES = Literal[
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
]

# Max 10MB per image (base64 adds ~33% overhead, so check decoded size)
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
MAX_IMAGES_PER_REQUEST = 5
_SUPPORTED_IMAGE_TYPE_SET = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
}


def _normalize_media_type(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized == "image/jpg":
        normalized = "image/jpeg"
    if normalized in _SUPPORTED_IMAGE_TYPE_SET:
        return normalized
    return None


def _coerce_files_to_images(files: object) -> list[dict]:
    """Convert Agent Framework-style files payload into ImageInput data."""
    if not isinstance(files, list):
        return []

    images: list[dict] = []
    for item in files:
        if not isinstance(item, dict):
            continue

        file_type = str(item.get("type", "")).lower()
        url = item.get("url")
        if not isinstance(url, str):
            continue

        # Prefer data URIs: data:image/jpeg;base64,...
        if url.startswith("data:"):
            try:
                header, b64_data = url.split(",", 1)
            except ValueError:
                continue
            if ";base64" not in header:
                continue
            media_type = _normalize_media_type(header[5:].split(";", 1)[0])
            if not media_type:
                continue
            images.append(
                {
                    "data": b64_data,
                    "media_type": media_type,
                    "filename": item.get("name") or item.get("filename"),
                }
            )
            continue

        # Fallback for plain base64 content in url field.
        if item.get("transfer_method") == "base64":
            media_type = _normalize_media_type(
                item.get("media_type") or item.get("mime_type") or ("image/jpeg" if file_type == "image" else None)
            )
            if not media_type:
                continue
            images.append(
                {
                    "data": url,
                    "media_type": media_type,
                    "filename": item.get("name") or item.get("filename"),
                }
            )

    return images


class ImageInput(BaseModel):
    """Model for image input in chat requests."""

    data: str = Field(..., description="Base64-encoded image data")
    media_type: SUPPORTED_IMAGE_TYPES = Field(..., description="MIME type of the image")
    filename: str | None = Field(None, description="Optional filename for reference")

    @field_validator("data")
    @classmethod
    def validate_image_size(cls, v: str) -> str:
        """Validate that decoded image data does not exceed 10MB."""
        try:
            decoded = base64.b64decode(v)
        except Exception:
            raise ValueError("Invalid base64-encoded image data")
        if len(decoded) > MAX_IMAGE_SIZE_BYTES:
            raise ValueError(f"Image exceeds maximum size of {MAX_IMAGE_SIZE_BYTES // (1024*1024)}MB")
        return v


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(..., description="User message to the SRE agent")
    thread_id: str | None = Field(None, description="Conversation thread ID for continuity")
    user_id: str | None = Field(None, description="User identifier for tracking")
    images: list[ImageInput] | None = Field(
        None, description="Optional list of images (max 5, each max 10MB)"
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_payload(cls, data):
        """Allow legacy/alternate payload shapes (Agent Framework client)."""
        if not isinstance(data, dict):
            return data

        # Support legacy key names.
        if "message" not in data and "query" in data:
            data["message"] = data["query"]
        if "thread_id" not in data and "conversation_id" in data:
            data["thread_id"] = data["conversation_id"]
        if "user_id" not in data and "user" in data:
            data["user_id"] = data["user"]

        # Support Agent Framework-style "files" image payloads.
        if "images" not in data and "files" in data:
            images = _coerce_files_to_images(data.get("files"))
            if images:
                data["images"] = images

        return data

    @field_validator("images")
    @classmethod
    def validate_image_count(cls, v: list[ImageInput] | None) -> list[ImageInput] | None:
        if v is not None and len(v) > MAX_IMAGES_PER_REQUEST:
            raise ValueError(f"Maximum {MAX_IMAGES_PER_REQUEST} images per request")
        return v


class PendingApproval(BaseModel):
    """Model for pending approval requests."""

    id: str = Field(..., description="Unique approval request ID")
    function_name: str = Field(..., description="Name of the function requiring approval")
    arguments: dict = Field(..., description="Arguments for the function")
    description: str = Field(..., description="Human-readable description of the operation")


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    message: str = Field(..., description="Agent response message")
    thread_id: str = Field(..., description="Conversation thread ID")
    pending_approvals: list[PendingApproval] | None = Field(
        None, description="List of operations pending user approval"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ApprovalRequest(BaseModel):
    """Request model for approval endpoint."""

    thread_id: str = Field(..., description="Conversation thread ID")
    approval_id: str = Field(..., description="Approval request ID to respond to")
    approved: bool = Field(..., description="Whether to approve the operation")
    reason: str | None = Field(None, description="Optional reason for approval/rejection")
    user_id: str | None = Field(None, description="User identifier for tracking")


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""

    status: Literal["healthy", "unhealthy"] = Field(..., description="Service health status")
    version: str = Field(..., description="Application version")
    agents_loaded: bool = Field(..., description="Whether agents are initialized")


class UpdateModelRequest(BaseModel):
    """Request model for active model update endpoint."""

    model_name: str = Field(..., description="Azure OpenAI deployment name to activate")


class ModelConfigResponse(BaseModel):
    """Response model for active model configuration."""

    active_model: str = Field(..., description="Currently active deployment")
    default_model: str = Field(..., description="Default deployment from .env")
    available_models: list[str] = Field(
        ...,
        description="Runtime-selectable model deployments",
    )


class AlertWebhookRequest(BaseModel):
    """Incoming alert webhook payload (best-effort normalized fields)."""

    rule_name: str | None = Field(None, description="Alert rule name")
    alert_id: str | None = Field(None, description="Unique alert identifier")
    severity: str | None = Field(None, description="Alert severity")
    context_message: str | None = Field(None, description="Alert message/context")
    app_name: str | None = Field(None, description="Application name")
    namespace: str | None = Field(None, description="Kubernetes namespace")
    pod_name: str | None = Field(None, description="Kubernetes pod name")
    container_name: str | None = Field(None, description="Kubernetes container name")
    node_name: str | None = Field(None, description="Kubernetes node name")
    value: str | None = Field(None, description="Alert value/threshold")
    link: str | None = Field(None, description="Alert link")
    date: str | None = Field(None, description="Alert timestamp")

    model_config = {
        "extra": "allow",
    }


class AlertWebhookResponse(BaseModel):
    """Response model for alert webhook processing."""

    status: str = Field(..., description="Processing status")
    analysis: str = Field(..., description="SRE-Agent analysis result")
