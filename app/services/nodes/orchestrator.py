import asyncio
import multiprocessing as mp
from typing import Any, Dict, List, Optional, cast


from app.services.websocket.manager import manager
from app.services.shared.topics import TopicRegistry
from app.core.logging import get_logger
from app.repositories import NodeRepository, EdgeRepository

from .node_factory import NodeFactory

logger = get_logger(__name__)

class NodeManager:
    def __init__(self):
        self.nodes_data: List[Dict[str, Any]] = []
        self.edges_data: List[Dict[str, Any]] = []
        self.data_queue: Any = mp.Queue(maxsize=100)
        self.is_running = False
        self._loop: Any = None
        self._listener_task: Any = None
        self._topic_registry = TopicRegistry()
        
        # Runtime tracking instances
        self.nodes: Dict[str, Any] = {}
        self.node_runtime_status: Dict[str, Dict[str, Any]] = {}
        self.downstream_map: Dict[str, List[str]] = {}

    def load_config(self):
        """Loads node and edge configurations from SQLite and registers them."""
        node_repo = NodeRepository()
        edge_repo = EdgeRepository()
        try:
            self.nodes_data = node_repo.list()
            self.edges_data = edge_repo.list()

            enabled_nodes = [n for n in self.nodes_data if n.get("enabled", True)]
            logger.info(f"Loaded {len(enabled_nodes)} enabled nodes and {len(self.edges_data)} edges from DB")

            # Initialize in topological order: sensors first, then operations, then fusions
            # (categories stored as 'sensor', 'operation', 'fusion')
            sensors    = [n for n in enabled_nodes if n.get("category") == "sensor"]
            operations = [n for n in enabled_nodes if n.get("category") == "operation"]
            fusions    = [n for n in enabled_nodes if n.get("category") == "fusion"]
            other      = [n for n in enabled_nodes if n.get("category") not in ("sensor", "operation", "fusion")]

            for group_name, group in [("sensor", sensors), ("operation", operations), ("fusion", fusions), ("other", other)]:
                for node in group:
                    try:
                        node_instance = NodeFactory.create(node, self, self.edges_data)
                        self.nodes[node["id"]] = node_instance
                        
                        # Register WebSocket topic for this node
                        node_name = getattr(node_instance, "name", node["id"])
                        topic = f"{node_name}_{node['id'][:8]}"
                        manager.register_topic(topic)
                        
                        logger.debug(f"Created {group_name} node: {node['id']} with topic: {topic}")
                    except Exception as e:
                        logger.error(f"Failed to create {group_name} node {node['id']}: {e}", exc_info=True)

            # Build downstream map for explicit routing
            self.downstream_map.clear()
            for edge in self.edges_data:
                source = edge.get("source_node")
                target = edge.get("target_node")
                if source and target:
                    if source not in self.downstream_map:
                        self.downstream_map[source] = []
                    self.downstream_map[source].append(target)

            logger.info(f"Initialized {len(self.nodes)} nodes. Downstream map: {dict(self.downstream_map)}")

        except Exception as e:
            logger.error(f"Error loading graph from DB: {e}", exc_info=True)

    def reload_config(self, loop=None):
        """Stops all services, reloads config, and restarts."""
        was_running = self.is_running

        self.stop()
        
        for node_id in list(self.nodes.keys()):
            self.remove_node(node_id)
            
        self._topic_registry.clear()
        # manager.reset_active_connections() # Do not wipe system websockets

        self.load_config()

        if was_running:
            self.start(loop or self._loop)



    def start(self, loop=None):
        self._loop = loop or asyncio.get_event_loop()
        self.is_running = True
        self.data_queue = mp.Queue(maxsize=100)

        for node_id, node_instance in self.nodes.items():
            if hasattr(node_instance, "start"):
                node_instance.start(self.data_queue, self.node_runtime_status)
            elif hasattr(node_instance, "enable"):
                node_instance.enable()
                
        self._listener_task = asyncio.create_task(self._queue_listener())

    def stop(self):
        self.is_running = False
        if self._listener_task:
            self._listener_task.cancel()
        
        for node_instance in self.nodes.values():
            if hasattr(node_instance, "stop"):
                node_instance.stop()
            elif hasattr(node_instance, "disable"):
                node_instance.disable()
                
        logger.info("All nodes stopped.")

    def remove_node(self, node_id: str):
        """Dynamically removes a node from the running pipeline, stopping it and cleaning up resources."""
        node_instance = self.nodes.pop(node_id, None)
        if not node_instance:
            return

        logger.info(f"Removing node {node_id} dynamically from running orchestrator")

        if hasattr(node_instance, "stop"):
            node_instance.stop()

        # Unregister WebSocket topic for this node
        node_name = getattr(node_instance, "name", node_id)
        topic = f"{node_name}_{node_id[:8]}"
        manager.unregister_topic(topic)

        # Cleanup topological maps
        if node_id in self.downstream_map:
            del self.downstream_map[node_id]
            
        for source, targets in list(self.downstream_map.items()):
            if node_id in targets:
                targets.remove(node_id)
                if not targets:
                    del self.downstream_map[source]
                    
        if node_id in self.node_runtime_status:
            del self.node_runtime_status[node_id]

    async def _queue_listener(self):
        loop = asyncio.get_event_loop()
        while self.is_running:
            try:
                if not self.data_queue.empty():
                    payload = await loop.run_in_executor(None, self.data_queue.get)
                    await self._handle_incoming_data(payload)
                else:
                    await asyncio.sleep(0.005)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Listener error: {e}", exc_info=True)
                await asyncio.sleep(0.1)

    async def _handle_incoming_data(self, payload: Dict[str, Any]):
        node_id = payload.get("lidar_id") or payload.get("node_id")
        if node_id and node_id in self.nodes:
            node_instance = self.nodes[node_id]
            if hasattr(node_instance, "handle_data"):
                # Legacy handle_data method (LidarSensor specific)
                await node_instance.handle_data(payload, self.node_runtime_status)
            elif hasattr(node_instance, "on_input"):
                # Standard on_input method (ModuleNode interface)
                await node_instance.on_input(payload)
        else:
            logger.warning(f"Received data for unknown node: {node_id}")

    async def forward_data(self, source_id: str, payload: Any):
        """
        Forwards data to all connected downstream nodes and handles WebSocket broadcasting.
        
        This is the central routing method that:
        1. Records data if recording is active
        2. Broadcasts to WebSocket clients if subscribed
        3. Forwards to downstream nodes in the DAG
        """
        source_node = self.nodes.get(source_id)
        if not source_node:
            logger.warning(f"forward_data called for unknown node: {source_id}")
            return
        
        # Generate topic name: {node_name}_{node_id[:8]}
        node_name = getattr(source_node, "name", source_id)
        topic = f"{node_name}_{source_id[:8]}"
        
        # 1. WebSocket Broadcasting (if anyone is listening)
        if "points" in payload and manager.has_subscribers(topic):
            try:
                from app.services.shared.binary import pack_points_binary
                import asyncio
                
                timestamp = payload.get("timestamp") or __import__('time').time()
                binary = await asyncio.to_thread(pack_points_binary, payload["points"], timestamp)
                await manager.broadcast(topic, binary)
                logger.debug(f"Broadcasted {len(payload['points'])} points from {source_id} on topic '{topic}'")
            except Exception as e:
                logger.error(f"Error broadcasting from node '{source_id}': {e}", exc_info=True)
        
        # 2. Native N-Dimensional Recording Interception
        # Bypasses the WebSockets strictly limited 3xFloat format (XYZ only)
        from app.services.shared.recorder import get_recorder
        recorder = get_recorder()
        if recorder.is_recording(source_id) and "points" in payload:
            try:
                # Capture complete Array out-of-band exactly as it completed calculation
                timestamp = payload.get("timestamp") or __import__('time').time()
                await recorder.record_node_payload(source_id, payload["points"], timestamp)
            except Exception as e:
                logger.error(f"Error intercepting recording payload for node '{source_id}': {e}", exc_info=True)
                
        # 3. Forward to downstream graph targets
        targets = self.downstream_map.get(source_id, [])
        for target_id in targets:
            target_node = self.nodes.get(target_id)
            if target_node and hasattr(target_node, "on_input"):
                try:
                    await target_node.on_input(payload)
                except Exception as e:
                    logger.error(f"Error forwarding data from {source_id} to {target_id}: {e}")


