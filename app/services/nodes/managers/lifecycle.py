"""
Node lifecycle management.

This module handles starting, stopping, enabling, disabling, and removing nodes
from the orchestration system.
"""
from typing import Any

from app.core.logging import get_logger
from app.services.websocket.manager import manager
from app.services.shared.topics import slugify_topic_prefix

logger = get_logger(__name__)


class LifecycleManager:
    """Handles node lifecycle operations."""
    
    def __init__(self, manager_ref):
        """
        Initialize the lifecycle manager.
        
        Args:
            manager_ref: Reference to the NodeManager instance
        """
        self.manager = manager_ref
    
    def start_all_nodes(self):
        """Start or enable all node instances."""
        for node_id, node_instance in self.manager.nodes.items():
            if hasattr(node_instance, "start"):
                node_instance.start(self.manager.data_queue, self.manager.node_runtime_status)
            elif hasattr(node_instance, "enable"):
                node_instance.enable()
    
    def stop_all_nodes(self):
        """Stop or disable all node instances."""
        for node_instance in self.manager.nodes.values():
            if hasattr(node_instance, "stop"):
                node_instance.stop()
            elif hasattr(node_instance, "disable"):
                node_instance.disable()
    
    def remove_node(self, node_id: str):
        """
        Dynamically remove a node from the running pipeline.
        
        This stops the node and cleans up all associated resources including
        WebSocket topics, routing maps, and runtime state.
        
        Args:
            node_id: The ID of the node to remove
        """
        node_instance = self.manager.nodes.pop(node_id, None)
        if not node_instance:
            return

        logger.info(f"Removing node {node_id} dynamically from running orchestrator")

        self._stop_node(node_instance)
        self._unregister_node_websocket_topic(node_id, node_instance)
        self._cleanup_node_routing(node_id)
        self._cleanup_node_state(node_id)
    
    def _stop_node(self, node_instance: Any):
        """
        Stop a single node instance.
        
        Args:
            node_instance: The node to stop
        """
        if hasattr(node_instance, "stop"):
            node_instance.stop()
    
    def _unregister_node_websocket_topic(self, node_id: str, node_instance: Any):
        """
        Unregister WebSocket topic for a node.
        
        Args:
            node_id: The node ID
            node_instance: The node instance
        """
        node_name = getattr(node_instance, "name", node_id)
        safe_name = slugify_topic_prefix(node_name)
        topic = f"{safe_name}_{node_id[:8]}"
        manager.unregister_topic(topic)
    
    def _cleanup_node_routing(self, node_id: str):
        """
        Remove node from downstream routing maps.
        
        Args:
            node_id: The node ID to remove
        """
        # Remove as source
        if node_id in self.manager.downstream_map:
            del self.manager.downstream_map[node_id]
        
        # Remove as target from all sources
        for source, targets in list(self.manager.downstream_map.items()):
            if node_id in targets:
                targets.remove(node_id)
                if not targets:
                    del self.manager.downstream_map[source]
    
    def _cleanup_node_state(self, node_id: str):
        """
        Clean up runtime state for a node.
        
        Args:
            node_id: The node ID to clean up
        """
        if node_id in self.manager.node_runtime_status:
            del self.manager.node_runtime_status[node_id]
        
        # Cleanup throttle state
        self.manager._throttle_config.pop(node_id, None)
        self.manager._last_process_time.pop(node_id, None)
        self.manager._throttled_count.pop(node_id, None)
