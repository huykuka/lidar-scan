from .orchestrator import NodeManager
# Auto-discover and load all module registries at startup
from app.modules import discover_modules

discover_modules()

node_manager = NodeManager()
