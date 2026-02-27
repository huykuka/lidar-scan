"""
Configuration loading and node initialization logic.

This module handles loading node/edge configurations from the database,
creating node instances via the factory, and building the DAG routing map.
"""
from typing import Any, Dict, List

from app.core.logging import get_logger
from app.repositories import NodeRepository, EdgeRepository
from app.services.websocket.manager import manager
from app.services.shared.topics import slugify_topic_prefix

from ..node_factory import NodeFactory

logger = get_logger(__name__)


class ConfigLoader:
    """Handles configuration loading and node initialization."""
    
    def __init__(self, manager_ref):
        """
        Initialize the config loader.
        
        Args:
            manager_ref: Reference to the NodeManager instance
        """
        self.manager = manager_ref
    
    def load_from_database(self) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Load node and edge configurations from SQLite.
        
        Returns:
            Tuple of (nodes_data, edges_data, enabled_nodes)
        """
        node_repo = NodeRepository()
        edge_repo = EdgeRepository()
        
        nodes_data = node_repo.list()
        edges_data = edge_repo.list()
        
        enabled_nodes = [n for n in nodes_data if n.get("enabled", True)]
        logger.info(f"Loaded {len(enabled_nodes)} enabled nodes and {len(edges_data)} edges from DB")
        
        return nodes_data, edges_data, enabled_nodes
    
    def initialize_nodes(self, enabled_nodes: List[Dict[str, Any]], edges_data: List[Dict[str, Any]]):
        """
        Initialize nodes in topological order: sensors -> operations -> fusions.
        
        Args:
            enabled_nodes: List of enabled node configurations
            edges_data: List of edge configurations
        """
        # Group nodes by category for proper initialization order
        sensors = [n for n in enabled_nodes if n.get("category") == "sensor"]
        operations = [n for n in enabled_nodes if n.get("category") == "operation"]
        fusions = [n for n in enabled_nodes if n.get("category") == "fusion"]
        other = [n for n in enabled_nodes if n.get("category") not in ("sensor", "operation", "fusion")]

        for group_name, group in [("sensor", sensors), ("operation", operations), ("fusion", fusions), ("other", other)]:
            for node in group:
                self._create_node(node, group_name, edges_data)
    
    def _create_node(self, node: Dict[str, Any], group_name: str, edges_data: List[Dict[str, Any]]):
        """
        Create a single node instance and register it.
        
        Args:
            node: Node configuration dictionary
            group_name: Category name for logging
            edges_data: List of edge configurations
        """
        try:
            node_instance = NodeFactory.create(node, self.manager, edges_data)
            self.manager.nodes[node["id"]] = node_instance
            
            self._initialize_node_throttling(node)
            self._register_node_websocket_topic(node, node_instance)
            
            logger.debug(f"Created {group_name} node: {node['id']}")
        except Exception as e:
            logger.error(f"Failed to create {group_name} node {node['id']}: {e}", exc_info=True)
    
    def _initialize_node_throttling(self, node: Dict[str, Any]):
        """
        Extract and store throttle configuration for a node.
        
        Args:
            node: Node configuration dictionary
        """
        config = node.get("config", {})
        throttle_ms = config.get("throttle_ms", 0)
        
        try:
            self.manager._throttle_config[node["id"]] = float(throttle_ms)
        except (ValueError, TypeError):
            self.manager._throttle_config[node["id"]] = 0.0
            
        self.manager._last_process_time[node["id"]] = 0.0
        self.manager._throttled_count[node["id"]] = 0
    
    def _register_node_websocket_topic(self, node: Dict[str, Any], node_instance: Any):
        """
        Register WebSocket topic for a node.
        
        Args:
            node: Node configuration dictionary
            node_instance: Created node instance
        """
        node_name = getattr(node_instance, "name", node["id"])
        safe_name = slugify_topic_prefix(node_name)
        topic = f"{safe_name}_{node['id'][:8]}"
        manager.register_topic(topic)
    
    def build_downstream_map(self, edges_data: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        Build downstream routing map from edge configurations.
        
        Args:
            edges_data: List of edge configurations
            
        Returns:
            Dictionary mapping source_node_id -> [target_node_ids]
        """
        downstream_map = {}
        
        for edge in edges_data:
            source = edge.get("source_node")
            target = edge.get("target_node")
            if source and target:
                if source not in downstream_map:
                    downstream_map[source] = []
                downstream_map[source].append(target)
        
        return downstream_map
