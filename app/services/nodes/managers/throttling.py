"""
Throttling management for node data processing.

This module handles rate limiting of data flow through nodes to prevent
overwhelming downstream processors and manage system resources.
"""
import time
from typing import Any, Dict

from app.core.logging import get_logger

logger = get_logger(__name__)


class ThrottleManager:
    """Handles throttling logic for node data processing."""
    
    def __init__(self, manager_ref):
        """
        Initialize the throttle manager.
        
        Args:
            manager_ref: Reference to the NodeManager instance
        """
        self.manager = manager_ref
    
    def should_process(self, node_id: str) -> bool:
        """
        Check if a node should process based on its throttle configuration.
        
        Args:
            node_id: The node to check
            
        Returns:
            True if the node should process, False if throttled
        """
        throttle_ms = self.manager._throttle_config.get(node_id, 0.0)
        
        # No throttling configured
        if throttle_ms <= 0:
            return True
        
        if self._has_enough_time_elapsed(node_id, throttle_ms):
            self._update_last_process_time(node_id)
            return True
        else:
            self._increment_throttled_count(node_id)
            return False
    
    def _has_enough_time_elapsed(self, node_id: str, throttle_ms: float) -> bool:
        """
        Check if enough time has elapsed since last processing.
        
        Args:
            node_id: The node ID
            throttle_ms: Throttle interval in milliseconds
            
        Returns:
            True if enough time has elapsed, False otherwise
        """
        current_time = time.time()
        last_time = self.manager._last_process_time.get(node_id, 0.0)
        elapsed_ms = (current_time - last_time) * 1000.0
        return elapsed_ms >= throttle_ms
    
    def _update_last_process_time(self, node_id: str):
        """
        Update the last processing timestamp for a node.
        
        Args:
            node_id: The node ID
        """
        self.manager._last_process_time[node_id] = time.time()
    
    def _increment_throttled_count(self, node_id: str):
        """
        Increment the throttled frame counter for a node.
        
        Args:
            node_id: The node ID
        """
        self.manager._throttled_count[node_id] = self.manager._throttled_count.get(node_id, 0) + 1
    
    def get_stats(self, node_id: str) -> Dict[str, Any]:
        """
        Get throttling statistics for a node.
        
        Args:
            node_id: The node ID
            
        Returns:
            Dictionary with throttling metrics
        """
        return {
            "throttle_ms": self.manager._throttle_config.get(node_id, 0.0),
            "throttled_count": self.manager._throttled_count.get(node_id, 0),
            "last_process_time": self.manager._last_process_time.get(node_id, 0.0)
        }
