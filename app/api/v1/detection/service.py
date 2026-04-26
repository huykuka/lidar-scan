"""Detection endpoint handlers — pure business logic without routing."""

from fastapi import HTTPException, UploadFile

from app.modules.detection.model_store import get_model_store
from .dto import ModelDeleteResponse, ModelInfo, ModelListResponse, ModelUploadResponse

# Maximum upload size: 2 GB (large models can exceed 500 MB)
_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024


async def list_models() -> ModelListResponse:
    """Return all uploaded detection models."""
    store = get_model_store()
    entries = store.list_models()
    models = [ModelInfo(**e.to_dict(base_dir=store._dir)) for e in entries]
    return ModelListResponse(models=models, count=len(models))


async def upload_model(
    file: UploadFile,
    display_name: str | None,
    model_type: str,
    description: str | None,
) -> ModelUploadResponse:
    """
    Upload a model checkpoint file and register it in the store.

    Args:
        file: Multipart-uploaded checkpoint file (``.pth``, ``.pt``, ``.onnx``).
        display_name: Human-readable label for the UI dropdown.
        model_type: Which detection model backend this checkpoint is for.
        description: Optional longer description.

    Returns:
        ModelUploadResponse with the new model metadata.

    Raises:
        HTTPException 400: If file is missing, too large, or wrong extension.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    data = await file.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum: {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    store = get_model_store()
    try:
        entry = store.add_model(
            filename=file.filename,
            data=data,
            display_name=display_name or "",
            model_type=model_type,
            description=description or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return ModelUploadResponse(
        model=ModelInfo(**entry.to_dict(base_dir=store._dir)),
        message=f"Model '{entry.display_name}' uploaded successfully.",
    )


async def get_model(model_id: str) -> ModelInfo:
    """Return metadata for a single model."""
    store = get_model_store()
    entry = store.get_model(model_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    return ModelInfo(**entry.to_dict(base_dir=store._dir))


async def delete_model(model_id: str) -> ModelDeleteResponse:
    """Delete a model and its checkpoint file."""
    store = get_model_store()
    deleted = store.delete_model(model_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    return ModelDeleteResponse(
        deleted=True,
        message=f"Model '{model_id}' deleted successfully.",
    )
