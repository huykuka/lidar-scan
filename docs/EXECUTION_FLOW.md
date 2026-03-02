# Execution Flow: Module Auto-Discovery & Registration

This document explains the complete execution timeline of the LiDAR standalone application's module auto-discovery system, from Python import to runtime data processing.

---

## Overview

The application uses a **side-effect import pattern** to auto-register modules without requiring orchestrator changes. Understanding the execution timeline is critical for:

- Adding new modules
- Debugging registration issues
- Understanding when code executes during startup
- Tracing data flow through the DAG

---

## Three-Phase Execution Model

The system operates in three distinct phases:

1. **Phase 1: Import Time** - Side-effect registration (decorators execute)
2. **Phase 2: Startup Time** - Node instantiation (builders execute)
3. **Phase 3: Runtime** - Data processing (instance methods execute)

---

## Phase 1: Python Import Time (Side-Effect Registration)

This happens **before** any application code runs, during Python module loading.

### Call Stack

```
1. Python interpreter loads app/app.py
   │
   ├─ Line 18: from app.services.nodes.instance import node_manager
   │  │
   │  └─ instance.py loads
   │     │
   │     ├─ Line 3: from app.modules import discover_modules
   │     │
   │     ├─ Line 5: discover_modules()  ← TRIGGERS AUTO-DISCOVERY
   │     │  │
   │     │  └─ modules/__init__.py discover_modules() executes:
   │     │     │
   │     │     ├─ Scans modules/ directory for sub-packages
   │     │     ├─ Finds: lidar/, fusion/, pipeline/
   │     │     │
   │     │     ├─ For each module:
   │     │     │  └─ importlib.import_module(f".{module_name}.registry", ...)
   │     │     │
   │     │     └─ Python loads modules/fusion/registry.py
   │     │        │
   │     │        ├─ Line 17: node_schema_registry.register(NodeDefinition(...))
   │     │        │           ↑ EXECUTES IMMEDIATELY
   │     │        │
   │     │        └─ Line 37-38: @NodeFactory.register("fusion")
   │     │                       def build_fusion(...):
   │     │                       ↑ DECORATOR EXECUTES IMMEDIATELY
   │     │                       
   │     │                       What happens:
   │     │                       - Python sees @NodeFactory.register("fusion")
   │     │                       - Calls NodeFactory.register("fusion")
   │     │                       - Returns decorator function
   │     │                       - Decorator adds build_fusion to NodeFactory._registry["fusion"]
   │     │                       - build_fusion is NOT called yet, just registered
   │     │
   │     └─ Line 7: node_manager = NodeManager()  ← Creates empty orchestrator
```

### Code References

**Discovery trigger**: `app/services/nodes/instance.py:5`
```python
discover_modules()  # Executes at import time
```

**Auto-discovery logic**: `app/services/modules/__init__.py:18-44`
```python
def discover_modules():
    """Auto-discover and import all module registry files."""
    package_dir = os.path.dirname(__file__)
    
    for info in pkgutil.iter_modules([package_dir]):
        if not info.ispkg:
            continue
            
        module_name = info.name
        try:
            # Import triggers side-effect registrations
            importlib.import_module(f".{module_name}.registry", package=__name__)
            logger.info(f"Loaded module registry: {module_name}")
        except ModuleNotFoundError:
            logger.debug(f"Module '{module_name}' has no registry.py -- skipped")
        except Exception as e:
            logger.error(f"Failed to load module '{module_name}' registry: {e}", exc_info=True)
```

**Decorator definition**: `app/services/nodes/node_factory.py:8-13`
```python
@classmethod
def register(cls, node_type: str):
    """Decorator to register a node builder function."""
    def decorator(builder_func: Callable):
        cls._registry[node_type] = builder_func  # Side-effect registration
        return builder_func
    return decorator
```

**Decorator usage**: `app/services/modules/fusion/registry.py:37-58`
```python
@NodeFactory.register("fusion")  # ← Decorator executes at import time
def build_fusion(node: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    """Build a FusionService instance from persisted node configuration."""
    from app.modules.lidar.sensor import LidarSensor
    from .service import FusionService
    
    config = node.get("config", {})
    
    # Find upstream sensor nodes
    incoming_edges = [e for e in edges if e["target_node"] == node["id"]]
    sensor_ids = []
    for e in incoming_edges:
        source_id = e["source_node"]
        source_node = service_context.nodes.get(source_id)
        if isinstance(source_node, LidarSensor):
            sensor_ids.append(source_id)
    
    return FusionService(
        service_context,
        topic=config.get("topic", f"fused_{node['id'][:8]}"),
        sensor_ids=sensor_ids,
        fusion_id=node["id"]
    )
```

### Result After Phase 1

- ✅ All schemas registered in `node_schema_registry`
- ✅ All builders registered in `NodeFactory._registry`:
  ```python
  {
    "sensor": <function build_sensor>,
    "fusion": <function build_fusion>,
    "crop": <function build_crop>,
    "downsample": <function build_downsample>,
    # ... 12 total node types
  }
  ```
- ✅ No nodes instantiated yet (the orchestrator is empty)
- ✅ `node_manager` singleton exists but has no nodes

---

## Phase 2: Application Startup (Node Instantiation)

This happens when FastAPI starts via the lifespan context manager.

### Call Stack

```
10. app.py lifespan() executes
    │
    ├─ Line 48: node_manager.load_config()  ← READS DATABASE
    │  │
    │  └─ orchestrator.py load_config() method:
    │     │
    │     ├─ Reads nodes table from SQLite
    │     ├─ Reads edges table from SQLite
    │     │
    │     ├─ Gets list like:
    │     │  [
    │     │    {"id": "abc123", "type": "sensor", "config": {...}},
    │     │    {"id": "def456", "type": "fusion", "config": {...}},
    │     │    {"id": "ghi789", "type": "crop", "config": {...}}
    │     │  ]
    │     │
    │     ├─ For each node in database:
    │     │  │
    │     │  └─ Calls: NodeFactory.create(node_data, self, edges)
    │     │     │
    │     │     └─ node_factory.py create() method (line 16-25):
    │     │        │
    │     │        ├─ Extracts node_type from node_data (e.g., "fusion")
    │     │        ├─ Looks up builder: cls._registry["fusion"]  ← Gets build_fusion
    │     │        │
    │     │        └─ Calls: build_fusion(node_data, service_context, edges)
    │     │                  ↑ BUILDER FUNCTION RUNS HERE!
    │     │                  
    │     │                  What happens:
    │     │                  - Extracts config from node_data
    │     │                  - Filters edges to find incoming connections
    │     │                  - Finds source nodes from service_context.nodes
    │     │                  - Creates FusionService instance
    │     │                  - Returns the instance to orchestrator
    │     │
    │     └─ Stores instance: self.nodes[node_id] = fusion_instance
    │
    └─ Line 49: node_manager.start(asyncio.get_running_loop())
```

### Code References

**Startup trigger**: `app/app.py:48`
```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    # Startup
    engine = init_engine()
    ensure_schema(engine)
    
    recorder = get_recorder()
    manager.recorder = recorder
    
    node_manager.load_config()  # ← Triggers Phase 2
    node_manager.start(asyncio.get_running_loop())
    
    start_status_broadcaster()
    
    yield
    
    # Shutdown
    stop_status_broadcaster()
    await recorder.stop_all_recordings()
    node_manager.stop()
```

**Factory instantiation**: `app/services/nodes/node_factory.py:16-25`
```python
@classmethod
def create(cls, node_data: Dict[str, Any], service_context: Any, edges: List[Dict[str, Any]]) -> Any:
    """Instantiates a node using the registered builder."""
    node_type = node_data.get("type")
    if not node_type:
        raise ValueError(f"Node data missing 'type': {node_data.get('id', 'unknown')}")
        
    if node_type not in cls._registry:
        raise ValueError(f"Unknown node type: {node_type}")
        
    return cls._registry[node_type](node_data, service_context, edges)  # ← Calls builder
```

### Result After Phase 2

- ✅ All nodes instantiated and stored in `node_manager.nodes`
- ✅ DAG edges mapped for data routing
- ✅ Nodes ready to process data
- ✅ Workers spawned for sensor nodes (multiprocessing)

---

## Phase 3: Runtime (Data Processing)

This happens continuously while the system runs.

### Call Stack

```
16. LidarSensor worker receives UDP packet
    │
    ├─ sensor.py worker process decodes packet
    │
    ├─ Puts data on multiprocessing.Queue
    │
    ├─ sensor.py main process reads queue
    │
    └─ Calls: await self.manager.forward_data(self.id, {"points": array})
       │
       └─ orchestrator.py forward_data() method:
          │
          ├─ Looks up edges for this node
          │
          ├─ Finds target nodes (e.g., fusion node)
          │
          └─ Calls: await fusion_instance.on_input({"points": array})
             │
             └─ fusion/service.py on_input() executes:
                │
                ├─ Buffers incoming points in _latest_frames
                │
                ├─ Checks if all sensors ready
                │
                ├─ Merges point clouds via np.concatenate()
                │
                └─ Calls: await self.manager.forward_data(self.id, {"points": merged})
                   │
                   └─ orchestrator.py forwards to next nodes (e.g., crop operations)
                      │
                      └─ Loop continues...
```

### Code References

**Data forwarding**: `app/services/nodes/orchestrator.py` (forward_data method)
```python
async def forward_data(self, source_node_id: str, payload: Dict[str, Any]):
    """Route data from source node to all connected target nodes."""
    targets = self._edge_map.get(source_node_id, [])
    
    for target_id in targets:
        target_node = self.nodes.get(target_id)
        if target_node and hasattr(target_node, 'on_input'):
            await target_node.on_input(payload)
```

**Fusion processing**: `app/services/modules/fusion/service.py`
```python
async def on_input(self, payload: Dict[str, Any]):
    """Receive point cloud data from upstream sensor nodes."""
    source_id = payload.get("source_id")
    points = payload.get("points")
    
    if source_id and points is not None:
        self._latest_frames[source_id] = points
        
        # Check if we have data from all expected sensors
        if len(self._latest_frames) == len(self.sensor_ids):
            await self._merge_and_forward()
```

### Result During Phase 3

- ✅ Continuous data flow through DAG
- ✅ Real-time point cloud processing
- ✅ WebSocket streaming to frontend
- ✅ Recording to disk (if enabled)

---

## Visual Timeline

```
TIME →

┌──────────────────────────────────────────────────────────────────┐
│ PHASE 1: IMPORT TIME (Side-Effect Registration)                 │
├──────────────────────────────────────────────────────────────────┤
│ • instance.py imported                                           │
│ • discover_modules() called                                      │
│ • fusion/registry.py imported                                    │
│   ├─ node_schema_registry.register() ← RUNS                     │
│   └─ @NodeFactory.register("fusion") ← RUNS (decorator only!)   │
│ • NodeManager() created (empty)                                  │
│                                                                  │
│ RESULT: Builders registered, no nodes created                   │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ PHASE 2: STARTUP TIME (Node Instantiation)                      │
├──────────────────────────────────────────────────────────────────┤
│ • app.py lifespan starts                                         │
│ • node_manager.load_config()                                     │
│   ├─ Read nodes from database                                   │
│   ├─ Read edges from database                                   │
│   ├─ For each node:                                             │
│   │  └─ NodeFactory.create()                                    │
│   │     └─ Calls build_fusion() ← BUILDER RUNS HERE!            │
│   │        └─ Returns FusionService instance                    │
│   └─ Store instances in node_manager.nodes                      │
│ • node_manager.start()                                           │
│                                                                  │
│ RESULT: All nodes instantiated, DAG ready                       │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ PHASE 3: RUNTIME (Continuous Data Processing)                   │
├──────────────────────────────────────────────────────────────────┤
│ • UDP packets arrive                                             │
│ • sensor.forward_data()                                          │
│ • orchestrator routes to edges                                   │
│ • fusion_instance.on_input() ← INSTANCE METHOD RUNS              │
│ • fusion.forward_data()                                          │
│ • Loop continues...                                              │
│                                                                  │
│ RESULT: Real-time point cloud processing                        │
└──────────────────────────────────────────────────────────────────┘
```

---

## Key Insights

### 1. Decorator Runs at Import Time

The `@NodeFactory.register("fusion")` decorator executes when Python loads `modules/fusion/registry.py`, **NOT** when you call `build_fusion()`.

**Why this matters:**
- Module registration happens before any application code runs
- You can't conditionally register modules based on runtime config
- Registration errors will crash the application at import time

### 2. Builder Runs at Config Load

The `build_fusion()` function executes during `node_manager.load_config()` for each fusion node in the database.

**Why this matters:**
- Builders have access to the full DAG (all nodes and edges)
- You can inspect upstream/downstream connections during instantiation
- Builder errors prevent specific nodes from loading (not the whole app)

### 3. Instance Methods Run at Runtime

The `fusion_instance.on_input()` method executes continuously as data flows through the DAG.

**Why this matters:**
- Performance-critical code (use `asyncio.to_thread()` for heavy ops)
- Errors here affect runtime stability
- Must handle backpressure and rate limiting

### 4. Side-Effect Imports Are Intentional

The pattern exploits Python's import mechanism to auto-register modules without explicit orchestrator changes.

**Why this matters:**
- Adding a new module requires zero orchestrator changes
- Just create the folder and restart
- The `/generate-module` command can scaffold complete modules

### 5. Lazy Imports Prevent Circular Dependencies

Builders import their node classes inside the function (not at module level).

**Example from fusion/registry.py:40-41:**
```python
def build_fusion(...):
    from app.modules.lidar.sensor import LidarSensor  # lazy import
    from .service import FusionService  # lazy import
```

**Why this matters:**
- Avoids import-time circular dependencies
- Orchestrator can import registries without importing node implementations
- Node classes only load when actually needed

---

## Common Debugging Scenarios

### Module Not Registered

**Symptom:** `ValueError: Unknown node type: fusion`

**Cause:** Decorator never executed (import failed)

**Fix:**
1. Check `discover_modules()` logs for errors
2. Verify `modules/fusion/registry.py` exists
3. Check for syntax errors in registry.py
4. Ensure decorator syntax is correct: `@NodeFactory.register("fusion")`

### Builder Fails

**Symptom:** Node doesn't load, error during `load_config()`

**Cause:** Exception in `build_fusion()`

**Fix:**
1. Check logs for stack trace
2. Verify database has correct node type
3. Check builder logic (edge filtering, config parsing)
4. Use debugger at `node_factory.py:25`

### Instance Method Fails

**Symptom:** Runtime errors, data not flowing

**Cause:** Exception in `on_input()`

**Fix:**
1. Check runtime logs
2. Verify payload format
3. Check for None values
4. Add error handling in `on_input()`

---

## File Reference

### Core Orchestration
- `app/services/nodes/instance.py` - Singleton + discovery trigger
- `app/services/nodes/orchestrator.py` - NodeManager DAG executor
- `app/services/nodes/node_factory.py` - Factory registry + decorator
- `app/services/nodes/base_module.py` - ModuleNode interface

### Auto-Discovery
- `app/services/modules/__init__.py` - `discover_modules()` implementation

### Module Registries
- `app/services/modules/lidar/registry.py` - Sensor registration
- `app/services/modules/fusion/registry.py` - Fusion registration
- `app/services/modules/pipeline/registry.py` - 9 operation registrations

### Application Entry
- `app/app.py` - FastAPI lifespan + startup trigger

---

## Further Reading

- **Module Architecture**: See `AGENTS.md` section "Module Architecture"
- **Adding Modules**: See `.opencode/skills/generate-module/SKILL.md`
- **Generate Command**: See `.opencode/commands/generate-module.md`

---

*Last Updated: 2026-02-26*
