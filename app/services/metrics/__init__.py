"""Performance metrics collection and aggregation system.

This module provides the core infrastructure for collecting, storing, and serving
performance metrics for the LiDAR processing system. It implements a zero-overhead
collection pattern with session-only in-memory state.
"""

from .registry import MetricsRegistry
from .collector import IMetricsCollector, MetricsCollector
from .null_collector import NullMetricsCollector
from .instance import get_metrics_collector, set_metrics_collector

__all__ = [
    "MetricsRegistry",
    "IMetricsCollector", 
    "MetricsCollector",
    "NullMetricsCollector",
    "get_metrics_collector",
    "set_metrics_collector",
]