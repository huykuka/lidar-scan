"""
Abstract base class for all pluggable module nodes in the DAG orchestrator.

This module defines the contract that every node (sensor, fusion, operation) 
must implement to integrate with the NodeManager routing engine.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ModuleNode(ABC):
    """
    Abstract base class for all pluggable module nodes.
    
    Every module that registers with the DAG orchestrator must implement
    this interface. The NodeManager interacts with nodes exclusively
    through these methods.
    
    Required attributes:
        id (str): Unique identifier for this node instance
        name (str): Display name for this node
        manager (Any): Reference to the NodeManager orchestrator
        
    Note: Throttling is now handled centrally by the NodeManager, not individual nodes.
    """

    id: str
    name: str
    manager: Any  # NodeManager reference (avoids circular import)

    @abstractmethod
    async def on_input(self, payload: Dict[str, Any]) -> None:
        """
        Receive data from upstream nodes in the DAG.
        
        Called by the orchestrator when an edge routes data to this node.
        The payload typically contains:
            - points: np.ndarray of point cloud data
            - timestamp: float (Unix timestamp)
            - node_id: str (source node ID)
            
        Implementations should:
            1. Process the input data
            2. Forward results via self.manager.forward_data(self.id, new_payload)
            3. Optionally broadcast to WebSocket subscribers
            
        Args:
            payload: Dictionary containing input data from upstream nodes
        """
        ...

    @abstractmethod
    def get_status(self, runtime_status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Return a status dictionary for the status broadcaster / API.
        
        Called periodically by the status broadcaster to collect node health metrics.
        
        Must include at minimum:
            - id (str): Node ID
            - name (str): Node name
            - type (str): Node type (e.g., "sensor", "fusion", "operation")
            - running (bool): Whether the node is active
            
        Optional fields:
            - last_frame_at (float): Timestamp of last processed frame
            - frame_age_seconds (float): Seconds since last frame
            - last_error (str): Most recent error message
            - topic (str): WebSocket topic for this node's output
            - Any module-specific metrics
            
        Args:
            runtime_status: Shared runtime state dictionary managed by the orchestrator
            
        Returns:
            Dictionary containing node status information
        """
        ...

    def start(self, data_queue: Any = None, runtime_status: Optional[Dict[str, Any]] = None) -> None:
        """
        Called when the orchestrator starts.
        
        Override for hardware nodes (sensors) that need to spawn worker processes
        or initialize connections.
        
        Args:
            data_queue: Multiprocessing queue for hardware nodes to push data
            runtime_status: Shared runtime state dictionary
        """
        pass

    def stop(self) -> None:
        """
        Called when the orchestrator stops.
        
        Override for cleanup tasks like:
            - Terminating worker processes
            - Closing network connections
            - Releasing hardware resources
        """
        pass

    def enable(self) -> None:
        """
        Enable this node for processing.
        
        Alternative to start() for nodes that don't manage background processes
        but need to toggle active state (e.g., fusion nodes).
        """
        pass

    def disable(self) -> None:
        """
        Disable this node from processing.
        
        Alternative to stop() for stateful pause/resume without full teardown.
        """
        pass
