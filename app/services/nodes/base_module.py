"""
Abstract base class for all pluggable module nodes in the DAG orchestrator.

This module defines the contract that every node (sensor, fusion, operation) 
must implement to integrate with the NodeManager routing engine.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import warnings

from app.schemas.status import NodeStatusUpdate


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
    def emit_status(self) -> NodeStatusUpdate:
        """
        Return standardised status. Called by StatusAggregator on state changes.
        
        This method must be implemented by all nodes to provide structured status
        information using the NodeStatusUpdate schema.
        
        Returns:
            NodeStatusUpdate: Standardised status containing operational_state,
                             optional application_state, and error_message.
        
        Example:
            return NodeStatusUpdate(
                node_id=self.id,
                operational_state=OperationalState.RUNNING,
                application_state=ApplicationState(
                    label="connection_status",
                    value="connected",
                    color="green"
                )
            )
        """
        ...
    
    def get_status(self, runtime_status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        DEPRECATED — use emit_status() instead.
        
        This method provides backward compatibility by converting the new
        emit_status() return value to the legacy dict format.
        
        Will be removed in a future version.
        
        Args:
            runtime_status: Shared runtime state dictionary (unused in new implementation)
            
        Returns:
            Dictionary containing node status information (legacy format)
        """
        warnings.warn(
            "get_status() is deprecated. Use emit_status() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        
        # Call the new emit_status() and convert to legacy format
        try:
            status_update = self.emit_status()
            legacy_dict = {
                "id": status_update.node_id,
                "name": self.name,
                "type": getattr(self, "node_type", "unknown"),
                "running": status_update.operational_state in ["RUNNING", "INITIALIZE"],
                "operational_state": status_update.operational_state,
                "timestamp": status_update.timestamp,
            }
            
            if status_update.application_state:
                legacy_dict["application_state"] = {
                    "label": status_update.application_state.label,
                    "value": status_update.application_state.value,
                    "color": status_update.application_state.color,
                }
            
            if status_update.error_message:
                legacy_dict["last_error"] = status_update.error_message
            
            return legacy_dict
        except NotImplementedError:
            # If emit_status() is not implemented yet, return minimal status
            return {
                "id": self.id,
                "name": self.name,
                "type": getattr(self, "node_type", "unknown"),
                "running": False,
                "last_error": "emit_status() not implemented",
            }

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
