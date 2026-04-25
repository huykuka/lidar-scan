"""
Node Orchestrator - DAG Execution Engine.

This is the main orchestrator that coordinates the node-based processing pipeline.
It delegates specific responsibilities to specialized manager classes:

- ConfigLoader: Loads configurations and initializes nodes
- LifecycleManager: Handles node start/stop/remove operations
- DataRouter: Routes data through the DAG with throttling
- ThrottleManager: Manages rate limiting per node

Architecture:
    The orchestrator maintains a Directed Acyclic Graph (DAG) of processing nodes.
    Data flows from source nodes (sensors) through processing nodes (operations)
    to sink nodes (fusion, output). The system supports:
    
    - Dynamic node creation/removal
    - WebSocket broadcasting of results
    - Recording of point cloud data
    - Per-node throttling for rate limiting
    - Multiprocessing for parallel data ingestion
"""
import asyncio
import multiprocessing as mp
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.services.shared.topics import TopicRegistry
from app.services.websocket.manager import manager as websocket_manager, SYSTEM_TOPICS

from .managers import ConfigLoader, LifecycleManager, DataRouter, ThrottleManager, SelectiveReloadManager
from .config_hasher import ConfigHashStore, compute_node_config_hash
from .input_gate import NodeInputGate

logger = get_logger(__name__)


class NodeManager:
    """
    Central orchestrator for the node-based processing pipeline.
    
    The NodeManager coordinates all aspects of the processing graph:
    - Loading and initializing nodes from database configurations
    - Managing node lifecycles (start, stop, reload)
    - Routing data between nodes via edges
    - Broadcasting results to WebSocket clients
    - Recording point cloud data streams
    - Throttling data flow to prevent overload
    """
    
    def __init__(self):
        """Initialize the NodeManager and its sub-managers."""
        # Configuration data
        self.nodes_data: List[Dict[str, Any]] = []
        self.edges_data: List[Dict[str, Any]] = []
        
        # Runtime state
        self.data_queue: Any = mp.Queue(maxsize=4)  # Small buffer — batch-drain listener keeps it near-empty
        self.is_running = False
        self._loop: Any = None
        self._listener_task: Any = None
        self._topic_registry = TopicRegistry()
        self._reload_lock: asyncio.Lock = asyncio.Lock()  # Prevent concurrent reloads
        
        # Runtime tracking instances
        self.nodes: Dict[str, Any] = {}  # node_id -> node_instance
        self.node_runtime_status: Dict[str, Dict[str, Any]] = {}  # node_id -> status_dict
        self.downstream_map: Dict[str, List[Dict[str, str]]] = {}  # source_id -> [port-aware edge dicts]
        
        # Throttling state per node
        self._throttle_config: Dict[str, float] = {}  # node_id -> throttle_interval_ms
        self._last_process_time: Dict[str, float] = {}  # node_id -> last_process_timestamp
        self._throttled_count: Dict[str, int] = {}  # node_id -> count of throttled frames
        
        # Sub-managers for specific responsibilities
        self._config_loader = ConfigLoader(self)
        self._lifecycle_manager = LifecycleManager(self)
        self._data_router = DataRouter(self)
        self._throttle_manager = ThrottleManager(self)
        self._selective_reload_manager = SelectiveReloadManager(self)

        # Selective reload state
        self._config_hash_store = ConfigHashStore()
        self._input_gates: Dict[str, NodeInputGate] = {}   # downstream_id -> gate (during reload)
        self._rollback_slot: Dict[str, Any] = {}            # node_id -> old_instance (during reload)
        self._active_reload_node_id: Optional[str] = None  # set during selective_reload_node()

    # ========================================
    # Configuration Management
    # ========================================
    
    def load_config(self):
        """
        Load node and edge configurations from SQLite and initialize the DAG.
        
        This method:
        1. Loads node and edge data from the database
        2. Creates node instances in topological order
        3. Builds the downstream routing map
        4. Registers WebSocket topics for each node
        """
        try:
            self.nodes_data, self.edges_data, enabled_nodes = self._config_loader.load_from_database()
            self._config_loader.initialize_nodes(enabled_nodes, self.edges_data)
            self.downstream_map = self._config_loader.build_downstream_map(self.edges_data)

            # Populate config hash store for change detection during selective reload.
            # On full reload, clear first so stale hashes from removed nodes don't linger.
            self._config_hash_store.clear()
            for node_data in self.nodes_data:
                if node_data.get("enabled", True):
                    self._config_hash_store.update(
                        node_data["id"],
                        compute_node_config_hash(node_data),
                    )
            
            logger.info(f"Initialized {len(self.nodes)} nodes. Downstream map: {dict(self.downstream_map)}")
        except Exception as e:
            logger.error(f"Error loading graph from DB: {e}", exc_info=True)

    async def reload_config(self, loop=None) -> None:
        """
        Reload the entire configuration from database with proper WebSocket cleanup.
        
        This method:
        1. Stops all running nodes
        2. Removes all nodes and cleans up resources (including WebSocket connections)
        3. Sweeps orphaned topics that might have been left behind
        4. Waits for cleanup to complete
        5. Reloads configuration from database
        6. Restarts the system if it was running before
        
        Args:
            loop: Optional asyncio event loop to use
        """
        async with self._reload_lock:
            logger.info("Config reload started (lock acquired)")
            
            was_running = self.is_running
            
            logger.info("Starting config reload...")
            self.stop()

            # Stop all PlaybackNode tasks properly (async, to prevent zombie tasks)
            await self._lifecycle_manager.stop_all_nodes_async()
            
            # Snapshot all topics registered BEFORE cleanup
            topics_before: set[str] = set(websocket_manager.active_connections.keys())
            
            logger.info("Cleaning up all nodes...")
            await self._cleanup_all_nodes_async()
            self._topic_registry.clear()
            
            logger.info("Waiting for process cleanup and port release...")
            await asyncio.sleep(2.0)  # replaced time.sleep — must not block the event loop
            
            # Sweep ALL topics that don't belong to the current configuration
            # This includes both topics that failed cleanup AND phantom topics from previous deployments
            logger.info("Loading new config...")
            self.load_config()
            
            # Collect all valid topics that should exist based on current config
            valid_topics: set[str] = set()
            for node_instance in self.nodes.values():
                if hasattr(node_instance, '_ws_topic'):
                    valid_topics.add(node_instance._ws_topic)
            
            # Find ALL topics that shouldn't exist (phantom + orphaned)
            current_topics: set[str] = set(websocket_manager.active_connections.keys())
            invalid_topics: set[str] = current_topics - valid_topics - SYSTEM_TOPICS
            
            if invalid_topics:
                logger.warning(f"reload_config: sweeping {len(invalid_topics)} invalid topic(s): {invalid_topics}")
                for invalid_topic in invalid_topics:
                    await websocket_manager.unregister_topic(invalid_topic)
            
            if was_running:
                logger.info("Restarting system...")
                await self.start(loop or self._loop)
            
            logger.info("Config reload complete.")

    async def selective_reload_node(self, node_id: str):
        """
        Reload a single node in-place without a full DAG teardown.

        Acquires ``_reload_lock`` to prevent concurrent reloads, broadcasts
        WebSocket reload-progress events, and delegates to
        ``SelectiveReloadManager.reload_single_node()``.

        Args:
            node_id: ID of the node to reload.

        Returns:
            SelectiveReloadResult describing the outcome.

        Raises:
            ValueError: If *node_id* is not present in the running pipeline.
        """
        from app.api.v1.schemas.nodes import SelectiveReloadResult

        async with self._reload_lock:
            self._active_reload_node_id = node_id
            try:
                await self._broadcast_reload_event(node_id, "reloading", "selective")
                result = await self._selective_reload_manager.reload_single_node(node_id)
                status = "ready" if result.status == "reloaded" else "error"
                await self._broadcast_reload_event(
                    node_id, status, "selective", result.error_message
                )
                return result
            finally:
                self._active_reload_node_id = None

    async def _broadcast_reload_event(
        self,
        node_id: Optional[str],
        status: str,
        reload_mode: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Broadcast a reload progress event on the system_status WebSocket topic.

        Args:
            node_id: The node being reloaded (None for full DAG reload).
            status: One of ``"reloading"``, ``"ready"``, ``"error"``.
            reload_mode: ``"selective"`` or ``"full"``.
            error_message: Optional error details when status is ``"error"``.
        """
        try:
            from app.schemas.status import SystemStatusBroadcast, ReloadEvent

            event = ReloadEvent(
                node_id=node_id,
                status=status,  # type: ignore[arg-type]
                reload_mode=reload_mode,  # type: ignore[arg-type]
                error_message=error_message,
            )
            broadcast = SystemStatusBroadcast(nodes=[], reload_event=event)
            await websocket_manager.broadcast("system_status", broadcast.model_dump())
        except Exception as exc:
            logger.warning(
                f"[NodeManager] _broadcast_reload_event failed: {exc!r}"
            )

    def _cleanup_all_nodes(self):
        """
        Remove all nodes and their resources during reload.
        
        # DEPRECATED: Use _cleanup_all_nodes_async() for proper async WebSocket cleanup
        """
        for node_id in list(self.nodes.keys()):
            self.remove_node(node_id)
    
    async def _cleanup_all_nodes_async(self) -> None:
        """Async remove all nodes and their resources during reload."""
        for node_id in list(self.nodes.keys()):
            await self.remove_node_async(node_id)

    # ========================================
    # Lifecycle Management
    # ========================================

    async def start(self, loop=None):
        """
        Start the orchestrator and all registered nodes.
        
        This method:
        1. Initializes the asyncio event loop
        2. Creates a fresh multiprocessing queue for data
        3. Starts all node instances (sensors spawn workers, others enable)
        4. Starts the queue listener task
        
        Args:
            loop: Optional asyncio event loop to use
        """
        self._loop = loop or asyncio.get_event_loop()
        self.is_running = True
        self.data_queue = mp.Queue(maxsize=4)

        await self._lifecycle_manager.start_all_nodes()
        self._listener_task = asyncio.create_task(self._queue_listener())

    def stop(self):
        """
        Stop the orchestrator and all running nodes.
        
        This method:
        1. Sets running flag to False
        2. Cancels the queue listener task
        3. Stops all node instances (sensors terminate workers, others disable)
        """
        self.is_running = False
        
        if self._listener_task:
            self._listener_task.cancel()
        
        self._lifecycle_manager.stop_all_nodes()
        logger.info("All nodes stopped.")

    def remove_node(self, node_id: str):
        """
        Dynamically remove a node from the running pipeline.
        
        This is useful for runtime reconfiguration without full restart.
        Cleans up all resources including WebSocket topics, routing, and state.
        
        For async contexts (FastAPI routes), prefer remove_node_async().
        
        Args:
            node_id: The ID of the node to remove
        """
        self._lifecycle_manager.remove_node(node_id)
    
    async def remove_node_async(self, node_id: str):
        """
        Async dynamically remove a node from the running pipeline with proper cleanup.
        
        This is useful for runtime reconfiguration without full restart.
        Cleans up all resources including WebSocket connections, topics, routing, and state.
        
        Args:
            node_id: The ID of the node to remove
        """
        await self._lifecycle_manager.remove_node_async(node_id)

    async def set_node_visible(self, node_id: str, visible: bool) -> None:
        """
        Set node visibility state, managing WebSocket topic registration/unregistration.
        
        Args:
            node_id: The node ID to modify
            visible: True to make visible (register topic), False to hide (unregister topic)
        """
        # If node_id not in self.nodes: log at DEBUG and return (disabled nodes — DB already updated by caller)
        if node_id not in self.nodes:
            logger.debug(f"set_node_visible called for disabled node {node_id} - DB updated, no runtime action needed")
            return
        
        node_instance = self.nodes[node_id]
        
        # If not visible and node_instance._ws_topic is not None: call unregister, then set _ws_topic = None
        if not visible and hasattr(node_instance, '_ws_topic') and node_instance._ws_topic is not None:
            await self._lifecycle_manager._unregister_node_websocket_topic_async(node_id, node_instance)
            node_instance._ws_topic = None
            logger.debug(f"Node {node_id} set to invisible - topic unregistered")
            
        # If visible and node_instance._ws_topic is None: derive topic, call register_topic, set _ws_topic = topic  
        elif visible and hasattr(node_instance, '_ws_topic') and node_instance._ws_topic is None:
            from app.services.shared.topics import slugify_topic_prefix
            
            node_name = getattr(node_instance, "name", node_id)
            topic = f"{slugify_topic_prefix(node_name)}_{node_id[:8]}"
            websocket_manager.register_topic(topic)
            node_instance._ws_topic = topic
            logger.debug(f"Node {node_id} set to visible - topic '{topic}' registered")
            
        # If visible and node_instance._ws_topic is not None: no-op (already visible)
        elif visible and hasattr(node_instance, '_ws_topic') and node_instance._ws_topic is not None:
            logger.debug(f"Node {node_id} already visible - no action needed")

    # ========================================
    # Data Flow Management
    # ========================================

    async def _queue_listener(self):
        """
        Listen to the multiprocessing queue and dispatch incoming data.

        Drains up to ``_BATCH_SIZE`` items per iteration to keep up with
        high-throughput sensors.  When multiple frames from the **same**
        sensor arrive in a single batch, only the most recent one is
        dispatched — older frames are dropped because the consumer (WebSocket
        broadcast + downstream DAG) cannot keep up anyway and stale data
        adds latency without value.
        """
        _BATCH_SIZE = 32
        loop = asyncio.get_event_loop()
        while self.is_running:
            try:
                payload = await loop.run_in_executor(
                    None, self._blocking_queue_get
                )
                if payload is None:
                    continue

                # Drain any additional queued items without blocking
                latest: dict[str, Any] = {}
                node_id = payload.get("lidar_id") or payload.get("node_id")
                if node_id:
                    latest[node_id] = payload

                for _ in range(_BATCH_SIZE - 1):
                    try:
                        extra = self.data_queue.get_nowait()
                    except Exception:
                        break
                    nid = extra.get("lidar_id") or extra.get("node_id")
                    if not nid:
                        continue
                    # Events (connect/disconnect/error) are always dispatched
                    if extra.get("event_type"):
                        asyncio.create_task(
                            self._data_router.handle_incoming_data(extra)
                        )
                    else:
                        latest[nid] = extra  # keep only the newest frame

                for p in latest.values():
                    asyncio.create_task(
                        self._data_router.handle_incoming_data(p)
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Listener error: {e}", exc_info=True)
                await asyncio.sleep(0.1)

    def _blocking_queue_get(self) -> Any:
        """Block on the mp.Queue with a short timeout so cancellation is responsive."""
        try:
            return self.data_queue.get(timeout=0.05)
        except Exception:
            return None

    async def forward_data(self, source_id: str, payload: Any, active_port: Optional[str] = None):
        """
        Forward data from a source node to downstream nodes.
        
        This is the main entry point for data propagation through the DAG.
        Called by nodes after they finish processing to send results downstream.
        
        Handles:
        - WebSocket broadcasting to subscribers
        - Recording data if active
        - Forwarding to connected downstream nodes (with throttling)
        
        Args:
            source_id: The ID of the source node
            payload: The data payload to forward
            active_port: If set, only forward edges matching this source port.
                         Used by IfConditionNode for port-aware fan-out.
        """
        await self._data_router.forward_data(source_id, payload, active_port=active_port)

    # ========================================
    # Throttling Management
    # ========================================

    def get_throttle_stats(self, node_id: str) -> Dict[str, Any]:
        """
        Get throttling statistics for a node.
        
        Used by the status API to report throttling metrics to the frontend.
        
        Args:
            node_id: The node ID
            
        Returns:
            Dictionary with throttle_ms, throttled_count, and last_process_time
        """
        return self._throttle_manager.get_stats(node_id)
