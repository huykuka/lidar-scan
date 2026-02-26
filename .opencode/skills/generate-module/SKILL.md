# Module Generation Skill

## Overview

This skill helps you generate new pluggable modules for the LiDAR point cloud processing system. Modules are self-contained components that can process sensor data, fuse multiple streams, or perform algorithmic transformations.

## Architecture Principles

### 1. Self-Contained Modules

All modules live under `app/services/modules/` and follow this structure:

```
app/services/modules/
└── <module_name>/
    ├── __init__.py           # Public API exports
    ├── registry.py           # NodeDefinition schemas & factory builders
    ├── <node_class>.py       # Node implementation extending ModuleNode
    └── (supporting files)    # Algorithm implementations, helpers, etc.
```

### 2. The ModuleNode Interface

All nodes must extend the `ModuleNode` abstract base class defined in `app/services/nodes/base_module.py`:

```python
from app.services.nodes.base_module import ModuleNode

class MyCustomNode(ModuleNode):
    """Required attributes: id, name, manager"""
    
    async def on_input(self, payload: Dict[str, Any]):
        """
        Process input data from upstream nodes.
        
        Typical flow:
        1. Extract points from payload: payload.get("points")
        2. Process the data (off main thread via asyncio.to_thread)
        3. Forward results: await self.manager.forward_data(self.id, new_payload)
        4. Optionally broadcast to WebSocket subscribers
        """
        pass
    
    def get_status(self, runtime_status: Dict[str, Any]) -> Dict[str, Any]:
        """Return node health/metrics for the status API"""
        return {
            "id": self.id,
            "name": self.name,
            "type": "my_custom",
            "running": True,
            # ... additional metrics
        }
    
    # Optional lifecycle hooks:
    def start(self, data_queue=None, runtime_status=None): pass
    def stop(self): pass
    def enable(self): pass
    def disable(self): pass
```

### 3. The Registry Pattern

Each module provides a `registry.py` that:

1. **Defines NodeDefinition schemas** - JSON metadata describing the node's UI, inputs, outputs, and properties
2. **Registers factory builders** - Functions decorated with `@NodeFactory.register()` that instantiate nodes

Example structure:

```python
from app.services.nodes.schema import NodeDefinition, PortDefinition, PropertyDefinition
from app.services.nodes.node_factory import NodeFactory

# 1. Define the schema
MY_NODE_SCHEMA = NodeDefinition(
    type="my_custom",
    category="Processing",
    name="My Custom Node",
    description="Does something cool",
    icon="🔧",
    inputs=[
        PortDefinition(
            id="input",
            name="Input Points",
            accepts=["points"]
        )
    ],
    outputs=[
        PortDefinition(
            id="output",
            name="Output Points",
            produces="points"
        )
    ],
    properties=[
        PropertyDefinition(
            id="threshold",
            name="Threshold",
            type="number",
            default=1.0,
            min=0.0,
            max=10.0
        )
    ]
)

# 2. Register the schema in the global registry
from app.services.nodes.schema import node_schema_registry
node_schema_registry.register(MY_NODE_SCHEMA)

# 3. Register the factory builder
@NodeFactory.register("my_custom")
def build_my_custom_node(node_data, manager, edges):
    """
    Factory function to instantiate the node.
    
    Args:
        node_data: Dict containing id, config, etc.
        manager: Reference to NodeManager (orchestrator)
        edges: List of edge connections for this node
    
    Returns:
        Instance of MyCustomNode
    """
    from .my_node import MyCustomNode
    
    return MyCustomNode(
        manager=manager,
        node_id=node_data["id"],
        config=node_data.get("config", {})
    )
```

### 4. Auto-Discovery

Modules are automatically discovered at startup via `app/services/modules/__init__.py`:

```python
def discover_modules():
    """Dynamically import all module registries"""
    import importlib
    import pkgutil
    
    # Find all packages in modules/
    for module_info in pkgutil.iter_modules([modules_path]):
        if module_info.ispkg:
            # Import the registry.py to trigger side-effect registration
            importlib.import_module(f"app.modules.{module_info.name}.registry")
```

This means **adding a new module requires zero changes to the orchestrator** - just create the folder structure and restart.

## Module Types

There are three primary module archetypes:

### Type 1: Sensor Nodes (Hardware Sources)

**Purpose**: Interface with physical hardware or simulation data sources.

**Characteristics**:
- Spawn multiprocessing workers to handle UDP packets or file I/O
- Push data into a shared queue consumed by the orchestrator
- Don't receive input from upstream nodes (they ARE the source)
- Handle lifecycle: `start()` spawns workers, `stop()` terminates them

**Example**: `modules/lidar/sensor.py`

**Key Implementation Notes**:
- Use `multiprocessing.Process` for worker isolation
- Communicate via `multiprocessing.Queue`
- Track runtime status in a shared dict
- The `on_input()` method can be empty (sensors are source nodes)

### Type 2: Fusion Nodes (Stream Aggregators)

**Purpose**: Combine multiple upstream data streams into a single output.

**Characteristics**:
- Receive input from multiple sensor nodes
- Maintain internal buffers of latest frames per source
- Wait until all expected sources have contributed before processing
- Use `enable()`/`disable()` instead of `start()`/`stop()`

**Example**: `modules/fusion/service.py`

**Key Implementation Notes**:
- Store `_latest_frames` dict keyed by source ID
- Check if all expected sources are ready before processing
- Use `asyncio.to_thread()` for heavy operations (e.g., `np.concatenate`)
- Forward merged payload via `self.manager.forward_data()`

### Type 3: Operation Nodes (Algorithmic Processors)

**Purpose**: Apply transformations, filtering, or analysis to point cloud data.

**Characteristics**:
- Receive single input stream
- Apply Open3D or NumPy algorithms
- Produce single output stream
- Highly composable (chain multiple operations)

**Example**: `modules/pipeline/operations/crop.py`

**Key Implementation Notes**:
- Use the `PipelineOperation` abstract base for algorithm logic
- Wrap operations in `OperationNode` for DAG integration
- Run heavy computation off main thread via `asyncio.to_thread()`
- Support dynamic property configuration from the UI

## Generation Workflow

When generating a new module, follow these steps:

### Step 1: Determine Module Type

Ask the user:
- **Sensor**: Are you interfacing with hardware or reading files?
- **Fusion**: Are you combining multiple data streams?
- **Operation**: Are you transforming/analyzing point cloud data?

### Step 2: Gather Module Information

Collect:
- **Module name**: Short, lowercase, snake_case (e.g., `radar`, `thermal_fusion`)
- **Description**: One-line summary of purpose
- **Node class name**: PascalCase (e.g., `RadarSensor`, `ThermalFusion`)
- **Properties**: User-configurable parameters (name, type, default, min/max)

### Step 3: Generate File Structure

Create:

```
app/services/modules/<module_name>/
├── __init__.py
├── registry.py
├── <node_class>.py
└── (supporting files as needed)
```

### Step 4: Implement Core Files

#### `__init__.py`
```python
"""<Module description>"""
from .<node_class> import <NodeClassName>

__all__ = ["<NodeClassName>"]
```

#### `registry.py`

Follow the pattern from existing modules:

1. Import schema types and registries
2. Define `NodeDefinition` with complete metadata
3. Call `node_schema_registry.register()`
4. Define factory builder with `@NodeFactory.register()`

#### `<node_class>.py`

1. Import `ModuleNode` base class
2. Implement required methods (`on_input`, `get_status`)
3. Add lifecycle hooks if needed (`start`, `stop`, `enable`, `disable`)
4. Use proper typing with `Dict[str, Any]` for payloads

### Step 5: Implement Processing Logic

For **Operation** nodes:
- Create a `PipelineOperation` subclass in a separate file
- Implement the `process(points, **params)` method
- Import and use in the node's `on_input()` method

For **Sensor** nodes:
- Create a worker process function
- Implement UDP/file reading logic
- Push frames to the data queue

For **Fusion** nodes:
- Implement buffering logic in `_on_frame()`
- Handle source tracking and readiness checks
- Merge data using NumPy/Open3D

### Step 6: Add WebSocket Broadcasting (Optional)

If the node should stream data to the UI:

```python
from app.services.websocket.manager import manager
from app.services.shared.binary import pack_points_binary

# In on_input():
topic = f"{self.name}_output"
if manager.has_subscribers(topic):
    binary_data = await asyncio.to_thread(
        pack_points_binary, 
        processed_points, 
        timestamp
    )
    await manager.broadcast(topic, binary_data)
```

### Step 7: Add Recorder Support (Optional)

If frames should be recordable:

```python
# In on_input():
topic = f"{self.name}_output"
if self.manager.has_subscribers(topic):  # Recorder is a subscriber
    # Broadcasting will automatically be captured by RecordingService
    await manager.broadcast(topic, binary_data)
```

### Step 8: Test the Module

1. **Import test**: Verify `from app.modules.<module_name> import <NodeClass>` works
2. **Discovery test**: Check that `discover_modules()` loads the registry
3. **Factory test**: Confirm the node type appears in `NodeFactory._registry`
4. **Integration test**: Add a node via API and verify it appears in the DAG

## Common Patterns & Best Practices

### 1. Off-Thread Computation

Always run heavy operations off the main event loop:

```python
import asyncio

async def on_input(self, payload):
    points = payload["points"]
    
    # Run Open3D/NumPy processing in thread pool
    result = await asyncio.to_thread(
        self._heavy_processing,
        points
    )
    
    # Back on main thread - can await async calls
    await self.manager.forward_data(self.id, {"points": result})

def _heavy_processing(self, points):
    """Synchronous processing (runs in thread pool)"""
    import open3d as o3d
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points[:, :3])
    # ... do work
    return np.asarray(pcd.points)
```

### 2. Error Handling

Wrap processing in try/except and update status:

```python
async def on_input(self, payload):
    try:
        # ... processing
        self.last_error = None
    except Exception as e:
        logger.error(f"[{self.id}] Processing failed: {e}", exc_info=True)
        self.last_error = str(e)
```

### 3. Status Reporting

Include actionable metrics in `get_status()`:

```python
def get_status(self, runtime_status):
    return {
        "id": self.id,
        "name": self.name,
        "type": "my_type",
        "running": self._enabled,
        "last_frame_at": self.last_frame_time,
        "frame_age_seconds": time.time() - self.last_frame_time if self.last_frame_time else None,
        "last_error": self.last_error,
        "frames_processed": self.frame_count,
        # Custom metrics:
        "buffer_size": len(self._buffer),
        "topic": self.output_topic,
    }
```

### 4. Topic Naming

Use consistent topic naming:

```python
from app.services.shared.topics import TopicRegistry, slugify_topic_prefix

# In __init__:
self.topic = TopicRegistry.generate_unique(
    slugify_topic_prefix(self.name),
    self.id
)

# Register for API discovery:
manager.register_topic(self.topic)
```

### 5. Payload Structure

Standard payload format:

```python
payload = {
    "node_id": self.id,           # Source node ID
    "points": np.ndarray,         # (N, 3+) float32 array
    "timestamp": float,           # Unix timestamp
    "count": int,                 # Number of points
    # Optional metadata:
    "lidar_id": str,              # Original sensor ID
    "event_type": str,            # "connected", "error", etc.
    "message": str,               # Human-readable status
}
```

## Property Configuration

Properties defined in the schema are passed to the node via `config`:

```python
# In registry.py:
properties=[
    PropertyDefinition(
        id="threshold",
        name="Threshold Value",
        type="number",
        default=2.0,
        min=0.0,
        max=10.0,
        step=0.1,
        description="Filtering threshold"
    ),
    PropertyDefinition(
        id="method",
        name="Processing Method",
        type="select",
        default="fast",
        options=[
            {"label": "Fast", "value": "fast"},
            {"label": "Accurate", "value": "accurate"}
        ]
    )
]

# In node __init__:
def __init__(self, manager, node_id, config):
    self.manager = manager
    self.id = node_id
    self.threshold = config.get("threshold", 2.0)
    self.method = config.get("method", "fast")
```

## Common Pitfalls

1. **Forgetting to call `discover_modules()`** - Modules won't be registered
2. **Not using `asyncio.to_thread()`** - Blocks the event loop, freezes WebSockets
3. **Hardcoding file paths** - Use `Path(__file__).parent` for relative imports
4. **Mutable default arguments** - Use `config.get("key", None)` not `config.get("key", [])`
5. **Not checking for subscribers before broadcasting** - Wastes CPU encoding binary data
6. **Circular imports** - Keep `ModuleNode` in a separate `nodes/` folder
7. **Accessing private attributes in tests** - Use public properties or methods

## Example: Complete Minimal Module

Here's a complete working example of a simple passthrough module:

**`app/services/modules/passthrough/__init__.py`**:
```python
"""Simple passthrough module for testing."""
from .node import PassthroughNode

__all__ = ["PassthroughNode"]
```

**`app/services/modules/passthrough/registry.py`**:
```python
from app.services.nodes.schema import NodeDefinition, PortDefinition, PropertyDefinition, node_schema_registry
from app.services.nodes.node_factory import NodeFactory

PASSTHROUGH_SCHEMA = NodeDefinition(
    type="passthrough",
    category="Utility",
    name="Passthrough",
    description="Forwards input data unchanged",
    icon="➡️",
    inputs=[PortDefinition(id="input", name="Input", accepts=["points"])],
    outputs=[PortDefinition(id="output", name="Output", produces="points")],
    properties=[
        PropertyDefinition(
            id="delay_ms",
            name="Delay (ms)",
            type="number",
            default=0,
            min=0,
            max=1000
        )
    ]
)

node_schema_registry.register(PASSTHROUGH_SCHEMA)

@NodeFactory.register("passthrough")
def build_passthrough(node_data, manager, edges):
    from .node import PassthroughNode
    return PassthroughNode(
        manager=manager,
        node_id=node_data["id"],
        config=node_data.get("config", {})
    )
```

**`app/services/modules/passthrough/node.py`**:
```python
import asyncio
import time
from typing import Dict, Any
from app.services.nodes.base_module import ModuleNode
from app.core.logging_config import get_logger

logger = get_logger(__name__)

class PassthroughNode(ModuleNode):
    """Forwards input data with optional delay."""
    
    def __init__(self, manager, node_id: str, config: Dict[str, Any]):
        self.manager = manager
        self.id = node_id
        self.name = f"Passthrough ({node_id[:8]})"
        self.delay_ms = config.get("delay_ms", 0)
        self.frame_count = 0
        self.last_frame_at = None
    
    async def on_input(self, payload: Dict[str, Any]):
        """Forward input to output with optional delay."""
        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000.0)
        
        self.frame_count += 1
        self.last_frame_at = time.time()
        
        # Forward unchanged
        await self.manager.forward_data(self.id, payload)
    
    def get_status(self, runtime_status: Dict[str, Any]) -> Dict[str, Any]:
        """Return node status."""
        return {
            "id": self.id,
            "name": self.name,
            "type": "passthrough",
            "running": True,
            "frames_processed": self.frame_count,
            "last_frame_at": self.last_frame_at,
            "delay_ms": self.delay_ms
        }
```

## Testing Your Module

Create a test file at `tests/services/<module_name>/test_<node_class>.py`:

```python
import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock

from app.modules.<module_name>.<node_class> import <NodeClassName>

@pytest.fixture
def mock_manager():
    manager = MagicMock()
    manager.forward_data = AsyncMock()
    return manager

@pytest.mark.asyncio
async def test_basic_processing(mock_manager):
    node = <NodeClassName>(
        manager=mock_manager,
        node_id="test-node",
        config={"param": 1.0}
    )
    
    payload = {
        "node_id": "upstream",
        "points": np.array([[1, 2, 3], [4, 5, 6]], dtype=np.float32),
        "timestamp": 123.0
    }
    
    await node.on_input(payload)
    
    # Verify forward_data was called
    mock_manager.forward_data.assert_called_once()
    args = mock_manager.forward_data.call_args[0]
    assert args[0] == "test-node"
    assert "points" in args[1]
```

## Summary Checklist

When generating a module, ensure:

- [ ] Module folder created in `app/services/modules/<name>/`
- [ ] `__init__.py` exports the node class
- [ ] `registry.py` defines schema and factory builder
- [ ] Node class extends `ModuleNode`
- [ ] `on_input()` implemented with proper payload handling
- [ ] `get_status()` returns comprehensive metrics
- [ ] Heavy operations use `asyncio.to_thread()`
- [ ] Error handling with try/except and status updates
- [ ] WebSocket broadcasting checks for subscribers
- [ ] Properties extracted from `config` dict
- [ ] Type hints used throughout
- [ ] Logger imported and used for debugging
- [ ] Test file created with basic coverage
- [ ] Module imports successfully: `from app.modules.<name> import <Node>`
- [ ] Discovery works: `discover_modules()` registers the node type
- [ ] Factory creates instances: `NodeFactory.create()` works

---

**Ready to generate a module?** Use the `/generate-module <name> <description>` command!
