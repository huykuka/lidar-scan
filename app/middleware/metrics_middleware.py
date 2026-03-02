"""FastAPI middleware for measuring endpoint latency.

This middleware measures the wall-clock time for API requests and records
the metrics for performance monitoring. Only /api/** routes are instrumented.
"""

import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.logging import get_logger

logger = get_logger(__name__)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware that measures HTTP endpoint latency for /api/** routes.
    
    This middleware wraps all HTTP requests and records timing metrics
    for API endpoints while skipping static content and SPA routes.
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request and measure latency for API routes.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in the chain
            
        Returns:
            HTTP response from downstream handlers
        """
        # Skip instrumentation for non-API routes
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        
        # Record start time and process request
        t0 = time.monotonic_ns()
        response = await call_next(request)
        latency_ms = (time.monotonic_ns() - t0) / 1_000_000.0
        
        # Record endpoint metrics (wrapped to prevent middleware errors)
        try:
            from app.services.metrics.instance import get_metrics_collector
            
            get_metrics_collector().record_endpoint(
                path=request.url.path,
                method=request.method,
                latency_ms=latency_ms,
                status_code=response.status_code
            )
        except Exception as e:
            logger.debug(f"Metrics middleware error for {request.method} {request.url.path}: {e}")
        
        return response