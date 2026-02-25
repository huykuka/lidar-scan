from .orchestrator import NodeManager
# Import node_registry so all schema definitions are registered at startup
from . import node_registry  # noqa: F401

node_manager = NodeManager()
