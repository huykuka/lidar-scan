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
        
        For async contexts (FastAPI routes), prefer remove_node_async().
        
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
    
    async def remove_node_async(self, node_id: str) -> None:
        """
        Async counterpart of remove_node with proper WebSocket teardown.
        
        This stops the node and cleans up all associated resources including
        WebSocket topics (with proper connection closing), routing maps, and runtime state.
        
        Args:
            node_id: The ID of the node to remove
        """
        node_instance = self.manager.nodes.pop(node_id, None)
        if not node_instance:
            return

        logger.info(f"Removing node {node_id} dynamically from running orchestrator (async)")

        self._stop_node(node_instance)
        await self._unregister_node_websocket_topic_async(node_id, node_instance)
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
        Unregister WebSocket topic for a node (sync fallback - deprecated).
        
        NOTE: This sync version cannot properly close WebSocket connections.
        Use _unregister_node_websocket_topic_async() for proper cleanup.
        
        Args:
            node_id: The node ID
            node_instance: The node instance
        """
        import asyncio
        
        # Use stored topic if available to guarantee key match with registration
        if hasattr(node_instance, "_ws_topic"):
            topic = node_instance._ws_topic
        else:
            node_name = getattr(node_instance, "name", node_id)
            safe_name = slugify_topic_prefix(node_name)
            topic = f"{safe_name}_{node_id[:8]}"
        
        logger.warning(f"Sync unregister_topic called for {topic} - WebSocket connections may not be properly closed")
        
        # Try to schedule the async version if we're in an async context
        try:
            loop = asyncio.get_running_loop()
            # Schedule the async cleanup but don't wait for it
            asyncio.create_task(manager.unregister_topic(topic))
        except RuntimeError:
            # No running event loop - can only remove from dicts (unsafe)
            logger.error(f"No event loop available to properly unregister topic {topic} - potential connection leaks")
            if topic in manager.active_connections:
                del manager.active_connections[topic]
            if topic in manager._interceptors:
                del manager._interceptors[topic]
    
    async def _unregister_node_websocket_topic_async(self, node_id: str, node_instance: Any) -> None:
        """
        Async unregister WebSocket topic for a node with proper cleanup.
        
        Reads node_instance._ws_topic first (if present) to guarantee key consistency;
        falls back to re-deriving via slugify_topic_prefix if the attribute is absent.
        
        Args:
            node_id: The node ID
            node_instance: The node instance
        """
        # Add early return guard at top: if hasattr(node_instance, "_ws_topic") and node_instance._ws_topic is None: return
        if hasattr(node_instance, "_ws_topic") and node_instance._ws_topic is None:
            return  # This prevents calling unregister_topic() on a non-existent topic for invisible nodes
            
        # Use stored topic if available to guarantee key match with registration
        if hasattr(node_instance, "_ws_topic"):
            topic = node_instance._ws_topic
        else:
            node_name = getattr(node_instance, "name", node_id)
            safe_name = slugify_topic_prefix(node_name)
            topic = f"{safe_name}_{node_id[:8]}"
        
        await manager.unregister_topic(topic)
    
    def _cleanup_node_routing(self, node_id: str):
        """
        Remove node from downstream routing maps.
        
        Args:
            node_id: The node ID to remove
        """
        # Remove as source
        if node_id in self.manager.downstream_map:
            del self.manager.downstream_map[node_id]
        
        # Remove as target from all sources (all edges are port-aware dicts)
        for source, targets in list(self.manager.downstream_map.items()):
            new_targets = [t for t in targets if t.get("target_id") != node_id]
            if len(new_targets) != len(targets):
                if new_targets:
                    self.manager.downstream_map[source] = new_targets
                else:
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
