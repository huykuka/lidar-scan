# Quick Reference - Refactored Node System

## Directory Structure

```
app/services/nodes/
├── orchestrator.py       # Main NodeManager coordinator
├── managers/             # Specialized manager modules
│   ├── __init__.py
│   ├── config.py         # Configuration & initialization
│   ├── lifecycle.py      # Start/stop/remove nodes
│   ├── routing.py        # Data routing & broadcasting
│   └── throttling.py     # Rate limiting
├── base_module.py        # Abstract base for nodes
├── node_factory.py       # Factory pattern
├── schema.py             # Schema definitions
└── instance.py           # Singleton getter
```

## Manager Responsibilities

### managers/config.py (ConfigLoader)
- Load node/edge data from SQLite
- Create node instances via factory
- Initialize throttling configurations
- Register WebSocket topics
- Build downstream routing map

### managers/lifecycle.py (LifecycleManager)
- Start/enable all nodes
- Stop/disable all nodes
- Remove individual nodes
- Cleanup resources (topics, routing, state)

### managers/routing.py (DataRouter)
- Route incoming data to nodes
- Broadcast to WebSocket subscribers
- Intercept data for recording
- Forward to downstream nodes with throttling

### managers/throttling.py (ThrottleManager)
- Check if node should process
- Track last processing time
- Count throttled frames
- Provide statistics

## Usage Examples

### Import the orchestrator
```python
from app.services.nodes.instance import node_manager
```

### Import managers directly
```python
from app.services.nodes.managers import ConfigLoader
from app.services.nodes.managers import LifecycleManager
from app.services.nodes.managers import DataRouter
from app.services.nodes.managers import ThrottleManager
```

### Access from NodeManager
```python
# NodeManager automatically creates these
node_manager._config_loader      # ConfigLoader instance
node_manager._lifecycle_manager  # LifecycleManager instance
node_manager._data_router        # DataRouter instance
node_manager._throttle_manager   # ThrottleManager instance
```

## Public API (Unchanged)

All public methods remain the same:

```python
# Configuration
node_manager.load_config()
node_manager.reload_config(loop=None)

# Lifecycle
node_manager.start(loop=None)
node_manager.stop()
node_manager.remove_node(node_id)

# Data Flow
await node_manager.forward_data(source_id, payload)

# Statistics
stats = node_manager.get_throttle_stats(node_id)
```

## Benefits

✅ **Clean Organization** - No spam in main directory  
✅ **Single Responsibility** - Each manager has one job  
✅ **Easy Testing** - Mock individual managers  
✅ **Maintainability** - Changes isolated to specific files  
✅ **Extensibility** - Easy to add new managers  
✅ **Backward Compatible** - No breaking changes  

## Migration Notes

**No code changes required!** The refactoring is internal only.

Existing code using `node_manager` will continue to work without modification.
