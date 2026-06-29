from .orchestrator import NodeManager
# Auto-discover and load all core module registries at startup
from app.modules import discover_modules
# Auto-load any plugins already present in app/plugins/
from app.plugins import discover_plugins

discover_modules()
discover_plugins()

node_manager = NodeManager()
