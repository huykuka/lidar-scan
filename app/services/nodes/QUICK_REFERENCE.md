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
- **Register WebSocket topics** with `_ws_topic` attribute storage on nodes
- Build downstream routing map

### managers/lifecycle.py (LifecycleManager)
- Start/enable all nodes
- Stop/disable all nodes
- Remove individual nodes
- **Async node removal** (`remove_node_async()`) for proper WebSocket cleanup
- Cleanup resources (topics, routing, state)
- **WebSocket topic cleanup** - automatically closes connections during removal

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
await node_manager.reload_config()  # Now async! (concurrency-safe with lock)

# Lifecycle
node_manager.start(loop=None)
node_manager.stop()
node_manager.remove_node(node_id)           # Sync version (deprecated)
await node_manager.remove_node_async(node_id)  # Preferred for FastAPI routes

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

## WebSocket Topic Cleanup

### Node `_ws_topic` Attribute Convention

When nodes are registered, they automatically receive a `_ws_topic` attribute that stores the exact WebSocket topic key used for registration. This enables reliable cleanup:

```python
# During node registration (automatic)
node._ws_topic = topic_key  # e.g., "lidar_sensor_abc123"

# During node removal (automatic cleanup)
if hasattr(node, '_ws_topic'):
    await websocket_manager.unregister_topic(node._ws_topic)
```

### Async Methods for WebSocket Safety

- **`reload_config()`** is now async - handles concurrent calls with a lock
- **`remove_node_async()`** is the preferred method for FastAPI route handlers
- Both methods properly close WebSocket connections and cancel pending futures
- Orphaned topic sweep in reload automatically cleans up stale topics

### Migration Notes

**No code changes required!** The refactoring is internal only.

Existing code using `node_manager` will continue to work without modification.
