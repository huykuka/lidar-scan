"""Discovery router.

    POST /discovery/scan  — start (202) or join running (200) scan   [admin]
    GET  /discovery/scan  — last cached scan job or null             [any authenticated user]
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from app.api.v1.auth.dependencies import get_current_user, roles_required
from .dto import ScanJob, ScanRequest
from .service import get_last_job, start_scan

router = APIRouter(prefix="/discovery", tags=["Discovery"])


@router.post(
    "/scan",
    response_model=ScanJob,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {"description": "A scan is already running; returns it"},
        422: {"description": "invalid_cidr | too_many_hosts | no_subnet"},
    },
    summary="Start LiDAR Device Scan",
    description="Starts a background scan for SICK devices (TCP 2111, CoLa A DeviceIdent). "
                "Non-empty cidrs replace auto-detected subnets. Singleton: returns running job if active.",
)
@roles_required("admin")
async def discovery_scan_start_endpoint(response: Response, req: ScanRequest | None = None) -> ScanJob:
    job, created = await start_scan(req.cidrs if req else None)
    if not created:
        response.status_code = status.HTTP_200_OK
    return job


@router.get(
    "/scan",
    response_model=ScanJob | None,
    summary="Get Last Scan Job",
    description="Returns the last (or running) scan job, or null when none.",
    dependencies=[Depends(get_current_user)],
)
async def discovery_scan_get_endpoint() -> ScanJob | None:
    return get_last_job()
