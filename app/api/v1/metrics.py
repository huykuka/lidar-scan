"""Performance metrics REST API endpoints.

This module provides HTTP endpoints for retrieving performance metrics
snapshots and health status. Implements api-spec.md §3 endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends
from app.core.config import settings
from app.services.metrics.instance import get_metrics_collector, IMetricsCollector
from app.services.metrics.models import (
    MetricsSnapshotModel,
    DagMetricsModel,
    WebSocketMetricsModel,
    PerformanceHealthModel
)

router = APIRouter(prefix="/metrics", tags=["metrics"])


def get_collector() -> IMetricsCollector:
    """FastAPI dependency for metrics collector injection."""
    return get_metrics_collector()


@router.get("/", response_model=MetricsSnapshotModel)
async def get_metrics_snapshot(collector: IMetricsCollector = Depends(get_collector)):
    """Get full metrics snapshot.
    
    Returns complete performance metrics for all subsystems.
    
    Raises:
        HTTPException: 503 if metrics collection is disabled
    """
    if not collector.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="Metrics collection is disabled. Set LIDAR_ENABLE_METRICS=true to enable."
        )
    
    return collector.snapshot()


@router.get("/dag", response_model=DagMetricsModel)
async def get_dag_metrics(collector: IMetricsCollector = Depends(get_collector)):
    """Get DAG-only metrics subset.
    
    Returns only the DAG processing metrics without WebSocket, system,
    or endpoint data. Useful for node performance monitoring.
    
    Raises:
        HTTPException: 503 if metrics collection is disabled
    """
    if not collector.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="Metrics collection is disabled. Set LIDAR_ENABLE_METRICS=true to enable."
        )
    
    snapshot = collector.snapshot()
    return snapshot.dag


@router.get("/websocket", response_model=WebSocketMetricsModel)
async def get_websocket_metrics(collector: IMetricsCollector = Depends(get_collector)):
    """Get WebSocket-only metrics subset.
    
    Returns only WebSocket performance metrics for diagnosing
    streaming performance issues.
    
    Raises:
        HTTPException: 503 if metrics collection is disabled
    """
    if not collector.is_enabled():
        raise HTTPException(
            status_code=503,
            detail="Metrics collection is disabled. Set LIDAR_ENABLE_METRICS=true to enable."
        )
    
    snapshot = collector.snapshot()
    return snapshot.websocket


@router.get("/health/performance", response_model=PerformanceHealthModel)
async def get_performance_health(collector: IMetricsCollector = Depends(get_collector)):
    """Get performance health status.
    
    Lightweight health check that always returns 200, even when metrics
    are disabled. Used for monitoring readiness and configuration status.
    """
    # This endpoint always returns 200, even when metrics are disabled
    from app.services.metrics import broadcaster, system_probe
    
    # Check if background tasks are running
    broadcaster_running = (
        collector.is_enabled() and
        hasattr(broadcaster, '_broadcast_task') and
        broadcaster._broadcast_task is not None and
        not broadcaster._broadcast_task.done()
    )
    
    system_probe_running = (
        collector.is_enabled() and
        hasattr(system_probe, '_probe_task') and
        system_probe._probe_task is not None and
        not system_probe._probe_task.done()
    )
    
    # Count active nodes from collector if enabled
    node_count = 0
    if collector.is_enabled():
        try:
            snapshot = collector.snapshot()
            node_count = snapshot.dag.total_nodes
        except Exception:
            pass
    
    return PerformanceHealthModel(
        metrics_enabled=collector.is_enabled(),
        broadcaster_running=broadcaster_running,
        system_probe_running=system_probe_running,
        node_count=node_count,
        version=settings.VERSION,
    )