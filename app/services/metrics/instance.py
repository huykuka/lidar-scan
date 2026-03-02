"""Module-level singleton accessor for metrics collector.

This module provides a global singleton pattern for accessing the active
metrics collector, mirroring the pattern used by app/services/nodes/instance.py.
"""

from .collector import IMetricsCollector
from .null_collector import NullMetricsCollector

# Module-level singleton instance - starts as null collector
_collector: IMetricsCollector = NullMetricsCollector()


def get_metrics_collector() -> IMetricsCollector:
    """Get the currently active metrics collector.
    
    Returns:
        The active metrics collector instance (real or null)
    """
    return _collector


def set_metrics_collector(collector: IMetricsCollector) -> None:
    """Replace the active metrics collector.
    
    This is called at application startup to inject either a real
    MetricsCollector or NullMetricsCollector based on configuration.
    
    Args:
        collector: The metrics collector instance to use
    """
    global _collector
    _collector = collector