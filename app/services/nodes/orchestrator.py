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
from .config_hasher import ConfigHashStore, compute_node_config_hash, compute_node_config_hash_no_pose
from .input_gate import NodeInputGate

logger = get_logger(__name__)

# Watchdog timeouts (seconds) guarding the reload critical section. The
# ``_reload_lock`` is held for the whole reload; without an upper bound a single
# hung await (node start(), websocket register/unregister, a sensor process that
# never releases its port, ...) would keep the lock held forever and make every
# subsequent reload return HTTP 409. These caps force a stuck reload to abort,
# release the lock, and surface an error so the app self-heals.
FULL_RELOAD_TIMEOUT_S: float = 5.0
SELECTIVE_RELOAD_TIMEOUT_S: float = 5.0


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
                    nid = node_data["id"]
                    self._config_hash_store.update(
                        nid,
                        compute_node_config_hash(node_data),
                    )
                    self._config_hash_store.update(
                        f"{nid}:no_pose",
                        compute_node_config_hash_no_pose(node_data),
                    )

            self._data_router.invalidate_shape_collector_cache()
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
            try:
                await asyncio.wait_for(
                    self._reload_config_impl(loop), timeout=FULL_RELOAD_TIMEOUT_S
                )
            except asyncio.TimeoutError:
                # A step inside the reload hung. wait_for has already cancelled
                # the inner coroutine; exiting the `async with` releases the lock
                # so future reloads are not permanently blocked with HTTP 409.
                self.is_running = False
                logger.error(
                    "Config reload exceeded %.0fs and was aborted to release the "
                    "reload lock. The pipeline may be in a partial state — trigger "
                    "another reload once the underlying issue is resolved.",
                    FULL_RELOAD_TIMEOUT_S,
                )
                raise RuntimeError(
                    f"Config reload timed out after {FULL_RELOAD_TIMEOUT_S:.0f}s"
                )

    async def _reload_config_impl(self, loop=None) -> None:
        """Body of :meth:`reload_config`, run under a watchdog timeout.

        Must only be called while ``_reload_lock`` is held.
        """
        was_running = self.is_running

        logger.info("Starting config reload...")
        # Only set flags and cancel the listener synchronously.
        # Actual node stops are handled by stop_all_nodes() below
        # to avoid blocking the event loop on sensor process.join().
        self.is_running = False
        if self._listener_task:
            self._listener_task.cancel()

        # Stop all nodes properly via async path (runs sensor stop() in
        # threads so the event loop stays responsive).
        await self._lifecycle_manager.stop_all_nodes()

        # Snapshot all topics registered BEFORE cleanup
        logger.info("Cleaning up all nodes...")
        await self._cleanup_all_nodes_async()
        self._topic_registry.clear()

        logger.info("Waiting for process cleanup and port release...")
        await asyncio.sleep(0.5)  # Process join already handled by stop_all_nodes (10 s timeout); this brief pause covers port release only.

        # Sweep ALL topics that don't belong to the current configuration
        # This includes both topics that failed cleanup AND phantom topics from previous deployments
        logger.info("Loading new config...")
        await asyncio.to_thread(self.load_config)

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

    async def hot_update_node_pose(self, node_id: str):
        """Hot-update a node's pose without stopping/restarting its worker.

        Unlike ``selective_reload_node``, this does NOT acquire the reload lock
        (pose updates are instantaneous in-memory matrix swaps) and does NOT
        stop/restart the worker process. This prevents the hang that occurs
        when the full reload cycle waits for a sensor process to join.

        Args:
            node_id: ID of the node whose pose changed.

        Returns:
            SelectiveReloadResult describing the outcome.
        """
        result = await self._selective_reload_manager.hot_update_pose(node_id)
        status = "ready" if result.status == "reloaded" else "error"
        await self._broadcast_reload_event(
            node_id, status, "selective", result.error_message
        )
        return result

    async def bootstrap_node(self, node_id: str) -> None:
        """Bootstrap a single node into the running pipeline.

        Called when a previously-disabled node is re-enabled.  The DB record
        already exists; this method creates the runtime instance, registers its
        WebSocket topic, wires it into the downstream map, and starts it.

        Args:
            node_id: ID of the node to bootstrap.

        Raises:
            ValueError: If the node is not found in the database.
        """
        from app.repositories import NodeRepository

        node_data = NodeRepository().get_by_id(node_id)
        if node_data is None:
            raise ValueError(f"Node '{node_id}' not found in database.")

        # Create the instance and register it (throttle + WS topic)
        self._config_loader._create_node(node_data, node_data.get("category", "other"), self.edges_data)

        # Refresh edges from DB and rebuild downstream map so any new connections
        # involving this node are included.
        from app.repositories import EdgeRepository
        self.edges_data = EdgeRepository().list()
        self.downstream_map = self._config_loader.build_downstream_map(self.edges_data)

        # Update config hash store
        from app.services.nodes.config_hasher import compute_node_config_hash, compute_node_config_hash_no_pose
        self._config_hash_store.update(node_id, compute_node_config_hash(node_data))
        self._config_hash_store.update(f"{node_id}:no_pose", compute_node_config_hash_no_pose(node_data))

        # Start the node if the orchestrator is running
        if self.is_running:
            node_instance = self.nodes.get(node_id)
            if node_instance is not None:
                import inspect
                if hasattr(node_instance, "start"):
                    result = node_instance.start(self.data_queue, self.node_runtime_status)
                    if inspect.isawaitable(result):
                        await result
                elif hasattr(node_instance, "enable"):
                    result = node_instance.enable()
                    if inspect.isawaitable(result):
                        await result

        self._data_router.invalidate_shape_collector_cache()
        await self._broadcast_reload_event(node_id, "ready", "selective")
        logger.info(f"[NodeManager] Node '{node_id}' bootstrapped into running pipeline.")

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
                f"[NodeManager] _broadcast_reload_event failed (status={status!r}): {exc!r}"
            )
            # For terminal events ("ready"/"error"), retry once after a short
            # delay so the frontend loading state does not get stuck permanently.
            if status in ("ready", "error"):
                import asyncio
                await asyncio.sleep(0.5)
                try:
                    await websocket_manager.broadcast("system_status", broadcast.model_dump())
                except Exception as retry_exc:
                    logger.error(
                        f"[NodeManager] _broadcast_reload_event retry also failed "
                        f"(status={status!r}): {retry_exc!r}. "
                        "Frontend loading indicator may be stuck until next reconnect."
                    )

    async def _cleanup_all_nodes_async(self) -> None:
        """Async remove all nodes and their resources during reload.

        Results are preserved (delete_results=False) because this is a transient
        reload/reconfiguration, not a permanent node removal.
        """
        for node_id in list(self.nodes.keys()):
            await self.remove_node_async(node_id, delete_results=False)

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

    async def stop(self):
        """
        Stop the orchestrator and all running nodes.

        This method:
        1. Sets running flag to False
        2. Cancels the queue listener task
        3. Stops all node instances properly via async stop
        """
        self.is_running = False

        if self._listener_task:
            self._listener_task.cancel()

        await self._lifecycle_manager.stop_all_nodes()
        logger.info("All nodes stopped.")

    async def remove_node_async(self, node_id: str, *, delete_results: bool = True):
        """
        Async dynamically remove a node from the running pipeline with proper cleanup.

        This is useful for runtime reconfiguration without full restart.
        Cleans up all resources including WebSocket connections, topics, routing, and state.

        Args:
            node_id: The ID of the node to remove
            delete_results: When True (default), permanently deletes stored results for the
                node from the database. Pass False during reload/reconfiguration to preserve
                results across restarts — only pass True when the node is being permanently
                removed by the user.
        """
        await self._lifecycle_manager.remove_node_async(node_id)
        self._data_router.invalidate_shape_collector_cache()
        # Only delete stored results on permanent removal, not during reload cleanup
        if delete_results:
            try:
                from app.api.v1.results.router import _results_service
                if _results_service is not None:
                    deleted = await _results_service.delete_results_by_node(node_id)
                    if deleted > 0:
                        logger.info(
                            "[NodeManager] Deleted %d stored result(s) for removed node '%s'",
                            deleted, node_id,
                        )
            except Exception as exc:
                logger.warning(
                    "[NodeManager] Failed to delete results for node '%s': %s", node_id, exc
                )

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
