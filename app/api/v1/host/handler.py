"""Host monitoring HTTP handlers — troubleshooting endpoints."""
from fastapi import APIRouter

from .dto import HostSnapshotResponse
from .service import get_snapshot, get_cpu, get_memory

router = APIRouter(prefix="/host", tags=["Host Monitor"])


@router.get(
    "",
    response_model=HostSnapshotResponse,
    summary="Host Snapshot",
    description=(
        "Full host system snapshot for troubleshooting: CPU, memory, disk, "
        "network interfaces, and the backend process stats."
    ),
)
async def host_snapshot():
    return await get_snapshot()


@router.get(
    "/cpu",
    summary="CPU Stats",
    description="CPU utilisation, core count, frequency, and load averages.",
)
async def host_cpu():
    return await get_cpu()


@router.get(
    "/memory",
    summary="Memory Stats",
    description="RAM and swap usage.",
)
async def host_memory():
    return await get_memory()
