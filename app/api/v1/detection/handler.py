"""Detection model management router — upload, list, and delete checkpoints."""

from fastapi import APIRouter, File, Form, UploadFile

from .dto import ModelDeleteResponse, ModelInfo, ModelListResponse, ModelUploadResponse
from .service import delete_model, get_model, list_models, upload_model

router = APIRouter(prefix="/detection", tags=["Detection Models"])


@router.get(
    "/models",
    response_model=ModelListResponse,
    summary="List Detection Models",
    description="List all uploaded detection model checkpoints.",
)
async def models_list_endpoint() -> ModelListResponse:
    return await list_models()


@router.post(
    "/models/upload",
    response_model=ModelUploadResponse,
    responses={
        400: {"description": "Invalid file type, empty file, or file too large"},
    },
    summary="Upload Detection Model",
    description=(
        "Upload a model checkpoint file (.pth, .pt, .onnx) for use with "
        "the 3D Object Detection node. The uploaded model appears in the "
        "checkpoint dropdown of the node configuration."
    ),
)
async def models_upload_endpoint(
    file: UploadFile = File(..., description="Model checkpoint file (.pth, .pt, .onnx)"),
    display_name: str | None = Form(None, description="Display name for the model in the UI"),
    model_type: str = Form("pointpillars", description="Model backend type (e.g. pointpillars)"),
    description: str | None = Form(None, description="Optional description"),
) -> ModelUploadResponse:
    return await upload_model(file, display_name, model_type, description)


@router.get(
    "/models/{model_id}",
    response_model=ModelInfo,
    responses={404: {"description": "Model not found"}},
    summary="Get Detection Model",
    description="Get metadata for a specific uploaded model.",
)
async def models_get_endpoint(model_id: str) -> ModelInfo:
    return await get_model(model_id)


@router.delete(
    "/models/{model_id}",
    response_model=ModelDeleteResponse,
    responses={404: {"description": "Model not found"}},
    summary="Delete Detection Model",
    description="Delete an uploaded model checkpoint and its file.",
)
async def models_delete_endpoint(model_id: str) -> ModelDeleteResponse:
    return await delete_model(model_id)
