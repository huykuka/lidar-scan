"""PCD Injection router — multipart upload endpoint for injecting PCD files."""

from fastapi import APIRouter, File, UploadFile

from .dto import PcdInjectionResponse
from .service import inject_pcd

router = APIRouter(prefix="/pcd-injection", tags=["PCD Injection"])


@router.post(
    "/{node_id}/upload",
    response_model=PcdInjectionResponse,
    responses={
        400: {"description": "Invalid PCD file or node is not a PCD Injection node"},
        404: {"description": "Node not found in running DAG"},
        413: {"description": "Uploaded file exceeds size limit"},
    },
    summary="Inject PCD File",
    description=(
        "Upload a PCD file via multipart/form-data and inject the parsed "
        "point cloud into the DAG through a PCD Injection node. "
        "The node must already exist in the running pipeline."
    ),
)
async def pcd_injection_upload(node_id: str, file: UploadFile = File(...)):
    return await inject_pcd(node_id, file)
