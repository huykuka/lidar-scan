"""
Data routing and forwarding logic.

This module handles routing data through the DAG, including WebSocket broadcasting,
recording interception, and forwarding to downstream nodes with throttling.
"""
import asyncio
import time
from typing import Any, Dict

from app.core.logging import get_logger
from app.services.websocket.manager import manager
from app.services.shared.topics import slugify_topic_prefix

logger = get_logger(__name__)


class DataRouter:
    """Handles data routing through the DAG."""
    
    def __init__(self, manager_ref):
        """
        Initialize the data router.
        
        Args:
            manager_ref: Reference to the NodeManager instance
        """
        self.manager = manager_ref
    
    async def handle_incoming_data(self, payload: Dict[str, Any]):
        """
        Route incoming data to the appropriate node handler.
        
        Args:
            payload: Data payload from queue
        """
        node_id = payload.get("lidar_id") or payload.get("node_id")
        if not node_id or node_id not in self.manager.nodes:
            logger.warning(f"Received data for unknown node: {node_id}")
            return

        node_instance = self.manager.nodes[node_id]
        
        if hasattr(node_instance, "handle_data"):
            # Legacy handle_data method (LidarSensor specific)
            await node_instance.handle_data(payload, self.manager.node_runtime_status)
        elif hasattr(node_instance, "on_input"):
            # Standard on_input method (ModuleNode interface)
            await node_instance.on_input(payload)
    
    async def forward_data(self, source_id: str, payload: Any):
        """
        Forward data to all connected downstream nodes and handle broadcasting.
        
        This is the central routing method that:
        1. Broadcasts to WebSocket clients if subscribed
        2. Records data if recording is active
        3. Forwards to downstream nodes in the DAG (with throttling)
        
        Args:
            source_id: Source node ID
            payload: Data payload to forward
        """
        source_node = self.manager.nodes.get(source_id)
        if not source_node:
            logger.warning(f"forward_data called for unknown node: {source_id}")
            return
        
        topic = self._get_node_topic(source_id, source_node)
        
        await self._broadcast_to_websocket(source_id, topic, payload)
        await self._record_node_data(source_id, payload)
        await self._forward_to_downstream_nodes(source_id, payload)
    
    def _get_node_topic(self, source_id: str, source_node: Any) -> str:
        """
        Generate topic name for a node: {slugified_node_name}_{node_id[:8]}
        
        Args:
            source_id: Node ID
            source_node: Node instance
            
        Returns:
            Topic name string
        """
        node_name = getattr(source_node, "name", source_id)
        safe_name = slugify_topic_prefix(node_name)
        return f"{safe_name}_{source_id[:8]}"
    
    async def _broadcast_to_websocket(self, source_id: str, topic: str, payload: Dict[str, Any]):
        """
        Broadcast point cloud data to WebSocket subscribers.
        
        Args:
            source_id: Source node ID
            topic: WebSocket topic name
            payload: Data payload
        """
        if "points" not in payload or not manager.has_subscribers(topic):
            return

        try:
            from app.services.shared.binary import pack_points_binary
            
            timestamp = payload.get("timestamp") or time.time()
            binary = await asyncio.to_thread(pack_points_binary, payload["points"], timestamp)
            await manager.broadcast(topic, binary)
            logger.debug(f"Broadcasted {len(payload['points'])} points from {source_id} on topic '{topic}'")
        except Exception as e:
            logger.error(f"Error broadcasting from node '{source_id}': {e}", exc_info=True)
    
    async def _record_node_data(self, source_id: str, payload: Dict[str, Any]):
        """
        Record node output data if recording is active.
        
        Bypasses WebSocket's XYZ-only format to capture complete N-dimensional arrays.
        
        Args:
            source_id: Source node ID
            payload: Data payload
        """
        if "points" not in payload:
            return

        from app.services.shared.recorder import get_recorder
        recorder = get_recorder()
        
        if not recorder.is_recording(source_id):
            return

        try:
            timestamp = payload.get("timestamp") or time.time()
            await recorder.record_node_payload(source_id, payload["points"], timestamp)
        except Exception as e:
            logger.error(f"Error intercepting recording payload for node '{source_id}': {e}", exc_info=True)
    
    async def _forward_to_downstream_nodes(self, source_id: str, payload: Dict[str, Any]):
        """
        Forward data to all downstream nodes in the DAG, applying throttling.
        
        Args:
            source_id: Source node ID
            payload: Data payload
        """
        targets = self.manager.downstream_map.get(source_id, [])
        
        for target_id in targets:
            if self._should_skip_due_to_throttling(source_id, target_id):
                continue
            
            await self._send_to_target_node(source_id, target_id, payload)
    
    def _should_skip_due_to_throttling(self, source_id: str, target_id: str) -> bool:
        """
        Check if data should be throttled for the target node.
        
        Args:
            source_id: Source node ID
            target_id: Target node ID
            
        Returns:
            True if should skip, False otherwise
        """
        # Access throttle manager directly from parent
        if not self.manager._throttle_manager.should_process(target_id):
            logger.debug(f"Throttled forwarding from {source_id} to {target_id}")
            return True
        return False
    
    async def _send_to_target_node(self, source_id: str, target_id: str, payload: Dict[str, Any]):
        """
        Send data to a specific target node.
        
        Args:
            source_id: Source node ID (for error logging)
            target_id: Target node ID
            payload: Data payload
        """
        target_node = self.manager.nodes.get(target_id)
        
        if not target_node or not hasattr(target_node, "on_input"):
            return

        try:
            # Instrumentation: Record execution start time
            t0 = time.monotonic_ns()
            
            await target_node.on_input(payload)
            
            # Instrumentation: Record execution metrics
            try:
                from app.services.metrics.instance import get_metrics_collector
                
                exec_ms = (time.monotonic_ns() - t0) / 1_000_000.0
                node_name = getattr(target_node, 'name', target_id)
                node_type = getattr(target_node, 'type', 'unknown')
                point_count = len(payload.get('points', [])) if 'points' in payload else 0
                
                get_metrics_collector().record_node_exec(
                    target_id, node_name, node_type, exec_ms, point_count
                )
            except Exception as metrics_error:
                logger.debug(f"Metrics instrumentation error for node {target_id}: {metrics_error}")
                
        except Exception as e:
            logger.error(f"Error forwarding data from {source_id} to {target_id}: {e}")
