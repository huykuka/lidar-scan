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

from .managers import ConfigLoader, LifecycleManager, DataRouter, ThrottleManager

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
        self.data_queue: Any = mp.Queue(maxsize=500)  # Multiprocessing queue for sensor data
        self.is_running = False
        self._loop: Any = None
        self._listener_task: Any = None
        self._topic_registry = TopicRegistry()
        
        # Runtime tracking instances
        self.nodes: Dict[str, Any] = {}  # node_id -> node_instance
        self.node_runtime_status: Dict[str, Dict[str, Any]] = {}  # node_id -> status_dict
        self.downstream_map: Dict[str, List[str]] = {}  # source_id -> [target_ids]
        
        # Throttling state per node
        self._throttle_config: Dict[str, float] = {}  # node_id -> throttle_interval_ms
        self._last_process_time: Dict[str, float] = {}  # node_id -> last_process_timestamp
        self._throttled_count: Dict[str, int] = {}  # node_id -> count of throttled frames
        
        # Sub-managers for specific responsibilities
        self._config_loader = ConfigLoader(self)
        self._lifecycle_manager = LifecycleManager(self)
        self._data_router = DataRouter(self)
        self._throttle_manager = ThrottleManager(self)

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
            
            logger.info(f"Initialized {len(self.nodes)} nodes. Downstream map: {dict(self.downstream_map)}")
        except Exception as e:
            logger.error(f"Error loading graph from DB: {e}", exc_info=True)

    def reload_config(self, loop=None):
        """
        Reload the entire configuration from database.
        
        This method:
        1. Stops all running nodes
        2. Removes all nodes and cleans up resources
        3. Waits for cleanup to complete
        4. Reloads configuration from database
        5. Restarts the system if it was running before
        
        Args:
            loop: Optional asyncio event loop to use
        """
        import time
        
        was_running = self.is_running
        
        logger.info("Starting config reload...")
        self.stop()
        
        logger.info("Cleaning up all nodes...")
        self._cleanup_all_nodes()
        self._topic_registry.clear()
        
        # Give processes time to fully terminate and release UDP ports
        # UDP sockets can remain in kernel for a short period after process exit
        logger.info("Waiting for process cleanup and port release...")
        time.sleep(2.0)
        
        logger.info("Loading new config...")
        self.load_config()
        
        if was_running:
            logger.info("Restarting system...")
            self.start(loop or self._loop)
        
        logger.info("Config reload complete.")

    def _cleanup_all_nodes(self):
        """Remove all nodes and their resources during reload."""
        for node_id in list(self.nodes.keys()):
            self.remove_node(node_id)

    # ========================================
    # Lifecycle Management
    # ========================================

    def start(self, loop=None):
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
        self.data_queue = mp.Queue(maxsize=500)

        self._lifecycle_manager.start_all_nodes()
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
        
        Args:
            node_id: The ID of the node to remove
        """
        self._lifecycle_manager.remove_node(node_id)

    # ========================================
    # Data Flow Management
    # ========================================

    async def _queue_listener(self):
        """
        Listen to the multiprocessing queue and dispatch incoming data.
        
        This task runs continuously while the system is running, pulling
        data from sensor worker processes and routing it to the appropriate
        node handlers.
        """
        loop = asyncio.get_event_loop()
        while self.is_running:
            try:
                if not self.data_queue.empty():
                    payload = await loop.run_in_executor(None, self.data_queue.get)
                    # Process frame concurrently without waiting (fire-and-forget)
                    asyncio.create_task(self._data_router.handle_incoming_data(payload))
                else:
                    await asyncio.sleep(0.005)  # 5ms sleep to prevent busy-waiting
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Listener error: {e}", exc_info=True)
                await asyncio.sleep(0.1)

    async def forward_data(self, source_id: str, payload: Any):
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
        """
        await self._data_router.forward_data(source_id, payload)

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
