from typing import Callable, Dict, Any, List

class NodeFactory:
    """Registry for dynamically creating Node instances based on their type."""
    _registry: Dict[str, Callable] = {}

    @classmethod
    def register(cls, node_type: str):
        """Decorator to register a node builder function."""
        def decorator(builder_func: Callable):
            cls._registry[node_type] = builder_func
            return builder_func
        return decorator

    @classmethod
    def create(cls, node_data: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
        """Instantiates a node using the registered builder."""
        node_type = node_data.get("type")
        if not node_type:
            raise ValueError(f"Node data missing 'type': {node_data.get('id', 'unknown')}")
            
        if node_type not in cls._registry:
            raise ValueError(f"Unknown node type: {node_type}")
            
        return cls._registry[node_type](node_data, service_context, edges)

# Note: node_registry is imported by instance.py at startup.
# This function is kept for backward compatibility but is no longer needed.
def _register_builtins():
    pass

_register_builtins()
