# LiDAR Standalone - Development Guide

## Project Structure

```text
lidar-standalone/
├── app/                    # Backend (Python FastAPI)
│   ├── api/v1/             # REST API endpoints (all under /api/v1 prefix)
│   │   ├── system.py       # System start/stop controls & status
│   │   ├── websocket.py    # WebSocket streaming handling
│   │   ├── nodes.py        # Node CRUD & reload operations
│   │   ├── edges.py        # Edge (connection) management
│   │   ├── recordings.py   # Recording start/stop/list/export
│   │   ├── logs.py         # System log access
│   │   └── config.py       # Configuration import/export
│   ├── modules/            # Pluggable node implementations
│   │   ├── lidar/
│   │   │   ├── workers/      # Multiprocessing workers (real.py, pcd.py)
│   │   │   │   └── api/      # SICK Scan C API bindings
│   │   │   ├── core/         # Transformations & sensor utilities
│   │   │   ├── io/           # PCD file operations
│   │   │   ├── sensor.py     # LidarSensor node class (extends ModuleNode)
│   │   │   └── registry.py   # Sensor schema definition & factory builder
│   │   ├── fusion/
│   │   │   ├── service.py    # FusionService node for merging point clouds
│   │   │   └── registry.py   # Fusion node registration
│   │   └── pipeline/         # Open3D Point Cloud Processing
│   │       ├── factory.py    # Central OperationFactory for instantiating logic
│   │       ├── base.py       # PipelineOperation abstract base class
│   │       ├── operation_node.py # Generic wrapper executing PipelineOperations
│   │       ├── registry.py   # Pipeline node registration
│   │       └── operations/   # Individual processing algorithms
│   │           ├── crop.py, downsample.py, outliers.py
│   │           ├── segmentation.py, clustering.py
│   │           ├── filter.py, boundary.py, debug.py
│   ├── services/
│   │   ├── nodes/          # Directed Acyclic Graph (DAG) Execution Engine
│   │   │   ├── orchestrator.py   # NodeManager: DAG executor, edge routing, data flow
│   │   │   ├── node_factory.py   # Factory instantiator and registry
│   │   │   ├── schema.py         # Type definitions for ports, properties, and nodes
│   │   │   ├── instance.py       # Singleton NodeManager instance
│   │   │   └── base_module.py    # BaseModule abstract class for all nodes
│   │   ├── shared/         # Shared utilities across modules
│   │   │   ├── binary.py   # Binary protocol helpers (WebSocket streaming)
│   │   │   ├── recorder.py # Global recording service singleton
│   │   │   ├── recording.py # Point cloud recording format (ZIP/PCD archives)
│   │   │   ├── thumbnail.py # Thumbnail generation for recordings
│   │   │   └── topics.py   # Topic hashing & management
│   │   ├── websocket/
│   │   │   └── manager.py  # WebSocket connection manager & multiplexer
│   │   └── status_broadcaster.py  # Real-time node status WebSocket broadcaster
│   ├── repositories/       # SQLite persistence layer
│   │   ├── nodes_orm.py    # Node & edge database operations
│   │   └── recordings_orm.py # Recording metadata storage
│   ├── db/                 # Database configuration
│   │   ├── models.py       # SQLAlchemy ORM models
│   │   ├── session.py      # Database session management
│   │   └── migrate.py      # Database migrations
│   ├── core/               # Core configuration
│   │   ├── config.py       # Application settings
│   │   └── logging_config.py # Logging setup
│   ├── config/             # Runtime data directory
│   │   ├── data.db         # SQLite database (gitignored, auto-created)
│   │   └── logs/           # Application logs
│   └── static/             # Built Angular frontend (served at /)
├── web/                    # Modern Angular frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── core/       # API Services, Signal Store architectures, Models, WS Handlers
│   │   │   │   ├── services/
│   │   │   │   │   ├── api/      # HTTP API client services
│   │   │   │   │   └── stores/   # Signal-based state management
│   │   │   │   ├── models/       # TypeScript interfaces & types
│   │   │   │   ├── interceptors/ # HTTP interceptors
│   │   │   │   ├── errors/       # Error handling
│   │   │   │   └── animations/   # Reusable animations
│   │   │   ├── features/   # Feature modules
│   │   │   │   ├── settings/
│   │   │   │   │   └── components/
│   │   │   │   │       ├── flow-canvas/   # Node-RED style drag-and-drop workspace
│   │   │   │   │       ├── dynamic-node-editor/ # Auto-generating config forms
│   │   │   │   │       ├── node-card/     # Individual node UI cards
│   │   │   │   │       ├── toolbox-header/ # Node palette toolbar
│   │   │   │   │       └── config-import-dialog/ # Import/export dialogs
│   │   │   │   ├── workspaces/ # 3D Three.js visualizer for live point clouds
│   │   │   │   │   └── components/
│   │   │   │   ├── recordings/ # Recording management UI
│   │   │   │   │   └── components/
│   │   │   │   ├── logs/       # Log viewer UI
│   │   │   │   │   └── components/
│   │   │   │   └── start/      # Start/home page
│   │   │   ├── layout/     # UI Shell routing
│   │   │   │   ├── components/
│   │   │   │   │   ├── header/
│   │   │   │   │   ├── footer/
│   │   │   │   │   └── side-nav/
│   │   │   │   └── main-layout/
│   │   │   ├── plugins/    # Extensible plugin system
│   │   │   └── app.*       # Root component
│   │   └── environments/   # Environment configuration
│   ├── package.json
│   ├── angular.json
│   └── tailwind.config.js
├── tests/                  # Unit tests (pytest)
├── scripts/                # Launch scripts (e.g. run_sim.sh)
└── AGENTS.md               # This architecture documentation
```

## Backend Stack & Architecture

- **FastAPI**: Core Python web framework for REST and WebSockets.
- **Open3D**: Point cloud manipulation, mathematics, clustering, and transformations.
- **AsyncIO & Multiprocessing**: High-performance isolated workers to process UDP LIDAR packets, streaming concurrently through an event loop.
- **NumPy**: Tensor matrix manipulations.

### The Node Orchestration Engine (DAG)

The backend has transitioned into a highly dynamic Directed Acyclic Graph (DAG) architecture. Instead of hardcoded pipelines, data flows from defined hardware sensors down through arbitrary operation trees.

1. **`NodeManager` (`orchestrator.py`)**:
   - Loads persisted `nodes` and `edges` from SQLite.
   - Maps physical target destinations (via IDs).
   - Serves as the high-level event router. Whenever a node completes its compute method, it calls `self.manager.forward_data(self.id, payload)`, and the Orchestrator distributes that array to all connected Edge targets.

2. **The Registry (`node_factory.py`)**:
   - Maintains a master `node_schema_registry` exposing node metadata (Inputs, Outputs, Properties, UI names, Icons) to the Angular front-end.
   - Bootstraps nodes utilizing builder functions (`@NodeFactory.register()`).
   - Module-specific registries (`lidar/registry.py`, `fusion/registry.py`, `pipeline/registry.py`) register their nodes with the central factory.
   - Dynamically resolves duplicate topics by appending a short-hash (e.g., `sensor_464724_raw_points`) to prevent WebSocket collisions. Debug output nodes actively intercept tracking and prevent WebSocket broadcasts entirely (`topic = None`).

3. **`OperationNode` (`operation_node.py`)**:
   - Universal async wrapper for processing nodes.
   - Holds an instance of a `PipelineOperation` generated by the `OperationFactory`.
   - Native threading optimization: runs Open3D routines off the main thread via `asyncio.to_thread` to prevent thread-locking the WebSockets API.

4. **Pipeline Operations Stack (`app/modules/pipeline/operations`)**:
   - Discrete, atomic Open3D operations.
   - Includes: `Crop`, `Downsample`, `StatisticalOutlierRemoval`, `RadiusOutlierRemoval`, `PlaneSegmentation`, `Clustering`, `FilterByKey`, `BoundaryDetection`, and `DebugSave`.
   - Note: Visualization operations were entirely stripped from the backend to ensure host OS stability (X11/Wayland context issues); all 3D visualizations are rendered purely in the Angular frontend.

## Module Architecture

The backend uses a **self-contained module architecture** where all node implementations are pluggable, auto-discovered, and completely independent from the orchestrator.

### Core Principles

1. **Zero Coupling**: The orchestrator (`NodeManager`) is module-agnostic and knows nothing about specific node types
2. **Auto-Discovery**: Modules automatically register at startup via `discover_modules()`
3. **Uniform Interface**: All nodes extend the `ModuleNode` abstract base class
4. **Self-Contained**: Each module owns its schema definitions, factory builders, and processing logic

### Module Structure

All modules live under `app/modules/` and follow this standard pattern:

```
app/modules/<module_name>/
├── __init__.py              # Public API exports
├── registry.py              # NodeDefinition schema + factory builder
├── <node_class>.py          # Node implementation (extends ModuleNode)
└── (supporting files)       # Workers, operations, algorithms, etc.
```

### The ModuleNode Interface

All nodes must implement the `ModuleNode` abstract base class (`app/services/nodes/base_module.py`):

```python
from app.services.nodes.base_module import ModuleNode

class MyNode(ModuleNode):
    """Required attributes: id, name, manager"""
    
    async def on_input(self, payload: Dict[str, Any]):
        """Process input data from upstream nodes in the DAG"""
        points = payload.get("points")
        # 1. Process data (use asyncio.to_thread for heavy ops)
        # 2. Forward results: await self.manager.forward_data(self.id, new_payload)
        # 3. Optionally broadcast to WebSocket subscribers
        pass
    
    def get_status(self, runtime_status: Dict[str, Any]) -> Dict[str, Any]:
        """Return node health/metrics for status API"""
        return {"id": self.id, "name": self.name, "type": "my_type", "running": True}
    
    # Optional lifecycle hooks:
    def start(self, data_queue=None, runtime_status=None): pass
    def stop(self): pass
    def enable(self): pass
    def disable(self): pass
```

### The Registry Pattern

Each module provides a `registry.py` that:

1. **Defines NodeDefinition schemas** - JSON metadata for UI rendering (inputs, outputs, properties, icons)
2. **Registers with node_schema_registry** - Makes schema available to frontend via API
3. **Registers factory builders** - Functions decorated with `@NodeFactory.register()` that instantiate nodes

Example:

```python
from app.services.nodes.schema import NodeDefinition, PortDefinition, PropertyDefinition, node_schema_registry
from app.services.nodes.node_factory import NodeFactory

# 1. Define schema
MY_SCHEMA = NodeDefinition(
    type="my_node",
    category="Processing",
    name="My Node",
    description="Does something",
    icon="🔧",
    inputs=[PortDefinition(id="input", name="Input", accepts=["points"])],
    outputs=[PortDefinition(id="output", name="Output", produces="points")],
    properties=[PropertyDefinition(id="threshold", name="Threshold", type="number", default=1.0)]
)

# 2. Register schema
node_schema_registry.register(MY_SCHEMA)

# 3. Register factory builder
@NodeFactory.register("my_node")
def build_my_node(node_data, manager, edges):
    from .my_node import MyNode
    return MyNode(manager=manager, node_id=node_data["id"], config=node_data.get("config", {}))
```

### Auto-Discovery Mechanism

At startup, `app/modules/__init__.py` automatically imports all module registries:

```python
def discover_modules():
    """Dynamically import all module registries (side-effect registration)"""
    import importlib
    for module in ["lidar", "fusion", "pipeline"]:
        importlib.import_module(f"app.modules.{module}.registry")
```

This is called by `app/services/nodes/instance.py` when the `NodeManager` singleton initializes.

**Result**: Adding a new module requires zero orchestrator changes - just create the folder and restart.

### Module Types

There are three primary module archetypes:

#### Type 1: Sensor Modules (Hardware Sources)

**Purpose**: Interface with physical hardware or simulation data sources

**Characteristics**:
- Spawn `multiprocessing.Process` workers for UDP/file I/O
- Push data to a shared `multiprocessing.Queue`
- Don't receive upstream input (they ARE the source)
- Implement `start()` to spawn workers, `stop()` to terminate

**Example**: `modules/lidar/sensor.py`

**Structure**:
```
modules/lidar/
├── __init__.py
├── registry.py           # Sensor schema + builder
├── sensor.py             # LidarSensor class
├── workers/
│   ├── real.py           # UDP packet worker (SICK Scan API)
│   ├── pcd.py            # PCD file playback worker
│   └── api/              # C API bindings
├── core/
│   └── transformations.py # Pose transformations
└── io/
    └── pcd.py            # PCD file I/O utilities
```

#### Type 2: Fusion Modules (Stream Aggregators)

**Purpose**: Combine multiple upstream data streams into a single output

**Characteristics**:
- Receive input from multiple sensor nodes via `on_input()`
- Maintain internal buffers of latest frames per source
- Wait until all expected sources contribute before processing
- Use `enable()`/`disable()` for state management (not start/stop)

**Example**: `modules/fusion/service.py`

**Structure**:
```
modules/fusion/
├── __init__.py
├── registry.py           # Fusion schema + builder
└── service.py            # FusionService class
```

**Key Implementation**:
- Buffer frames in `_latest_frames: Dict[str, np.ndarray]`
- Check source readiness before merging
- Use `asyncio.to_thread()` for heavy operations (e.g., `np.concatenate`)
- Forward merged payload via `self.manager.forward_data()`

#### Type 3: Operation Modules (Algorithmic Processors)

**Purpose**: Apply transformations, filtering, or analysis to point cloud data

**Characteristics**:
- Receive single input stream via `on_input()`
- Apply Open3D or NumPy algorithms
- Produce single output stream
- Highly composable (chain multiple operations in DAG)

**Example**: `modules/pipeline/operations/crop.py`

**Structure**:
```
modules/pipeline/
├── __init__.py
├── registry.py           # 9 operation schemas + builders
├── operation_node.py     # Generic OperationNode wrapper
├── base.py               # PipelineOperation abstract base
├── factory.py            # OperationFactory for instantiating operations
└── operations/
    ├── crop.py           # Bounding box cropping
    ├── downsample.py     # Voxel downsampling
    ├── outliers.py       # Statistical outlier removal
    ├── segmentation.py   # Plane segmentation
    ├── clustering.py     # DBSCAN clustering
    ├── filter.py         # Field filtering
    ├── boundary.py       # Boundary detection
    └── debug.py          # Debug save to disk
```

**Key Implementation**:
- Each operation inherits from `PipelineOperation` abstract base
- `OperationNode` wraps operations for DAG integration
- All processing runs off main thread via `asyncio.to_thread()`
- Properties dynamically configure algorithms from UI

### Shared Utilities

Cross-cutting utilities live in `app/services/shared/`:

```
shared/
├── __init__.py
├── binary.py      # LIDR binary protocol encoding/decoding (WebSocket)
├── topics.py      # Topic hashing & unique generation
├── recorder.py    # Global RecordingService singleton
├── recording.py   # Generic point cloud recording format (ZIP/PCD)
└── thumbnail.py   # Thumbnail generation from point clouds
```

These are imported by multiple modules and are not specific to any node type.

### Adding a New Module

To add a new module (e.g., radar sensor):

1. **Create directory**: `app/services/modules/radar/`
2. **Create `__init__.py`**: Export the node class
3. **Create `registry.py`**: Define schema and factory builder
4. **Create `radar.py`**: Implement node class extending `ModuleNode`
5. **Restart application**: Auto-discovery will register the module

**No orchestrator changes needed!**

You can use the `/generate-module` command to scaffold a complete module with all boilerplate:

```bash
/generate-module radar "Process radar sensor data streams" --type=sensor
```

## Frontend Stack & Architecture

- **Angular 17+**: Utilizing Standalone components and modern control flows (`@if`, `@for`).
- **Angular Signals**: Extremely aggressive reactive state handling.
- **Three.js**: Custom WebGL rendering canvas specifically optimized for heavy Point Cloud arrays.
- **Synergy Design System** & **Tailwind CSS**.

### Flow Canvas (The Settings Editor)

Location: `web/src/app/features/settings/components/flow-canvas/`

The frontend application provides a stunning "Node-RED" style interactive canvas graph for routing LiDAR.

1. **State Independence**: The application employs strict separation of state variables. For example, loading flags are isolated (`isPaletteLoading` vs `isCanvasLoading`) so the Plugin Sidebar renders immediately, while the DOM engine explicitly waits for the Graph lines to finish calculating their SVG bezier offsets before lifting the overlay loader.
2. **Dynamic UI Form Generation**: The application parses the JSON properties dict defined by the backend `NodeDefinition` schemas to proactively yield typed, validated input fields (Number steppers, dropdowns, input strings) via the `DynamicNodeEditorComponent`. No hard-coded forms exist.
3. **Graph Algorithms**:
   - Auto-calculates bezier curve connections.
   - Port drag-and-drop targeting.
   - Employs live WebSockets tracking (rather than HTTP polling) to reflect immediate hardware telemetry bounds directly onto Node Cards (FPS stats, Error status, Last run ping).

### 3D Workspaces (Three.js Visualizer)

Location: `web/src/app/features/workspaces/`

The Workspace allows subscribing to any node that broadcasts data over WebSockets (e.g., `sensor_RAW`, `fused_xyz`, `cropped_813b1`).

1. **Multi-Topic Streaming**: Simultaneously decodes custom `LIDR` binary protocol via `MultiWebsocketService`.
2. **BufferGeometry Mastery**: Mutates WebGL arrays entirely in-place. If point count bounds fluctuate, ThreeJS geometries are resized; otherwise, positions execute direct array substitutions to achieve 60+ FPS playback on dense 100k+ point clouds.
3. **Persisted Viewports**: The active active topic list automatically synchronizes back to `localStorage` through reactive Angular effects, seamlessly resuming visualizer configurations upon refresh.

## Network Protocols

### WebSocket Binary Frame Format (LIDR)

Point cloud nodes do not send slow JSON arrays over network protocols. They pack memory blocks directly onto binary buffers decoded synchronously by standard DataViews on the client.

| Offset | Size  | Type    | Description               |
| ------ | ----- | ------- | ------------------------- |
| 0      | 4     | char[4] | Magic "LIDR"              |
| 4      | 4     | uint32  | Version                   |
| 8      | 8     | float64 | Timestamp                 |
| 16     | 4     | uint32  | Point count               |
| 20     | N\*12 | float32 | Points (x, y, z) \* count |

### Data Recording Subsystem

The recording system operates **independently from WebSocket streaming** by intercepting node outputs directly at the DAG orchestrator level.

**Key Architecture Principles**:

1. **Node-Based Recording**: Recording targets nodes by their `node_id`, not WebSocket topics. The frontend simply sends `POST /api/v1/recordings/start` with the node ID.

2. **DAG-Level Interception**: When any node calls `manager.forward_data(node_id, payload)`, the orchestrator checks `recorder.is_recording(node_id)` and writes the full N-dimensional point cloud data directly to disk **before** WebSocket broadcast occurs.

3. **Full Data Capture**: Recording captures complete numpy arrays (all dimensions, metadata, etc.), while WebSocket streaming only broadcasts XYZ coordinates for visualization. This separation ensures recordings preserve all processing data.

4. **Concurrent Recording**: Multiple recordings can target the same node simultaneously without collision, each generating a unique UUID-based recording file.

5. **Singleton Integration**: The `RecordingService` is a global singleton lazily loaded by the orchestrator, avoiding circular dependencies while ensuring recording handles are available wherever `forward_data()` is called.

**Recording Flow**:
- User clicks record button → `POST /api/v1/recordings/start` with `node_id`
- Backend creates `RecordingHandle` and stores in `active_recordings` dict
- As nodes process data, orchestrator intercepts via `recorder.record_node_payload(node_id, points, timestamp)`
- Frames are batched and written to ZIP archive asynchronously
- User clicks stop → frames flush, metadata written, thumbnail generated, saved to SQLite

### REST System Flow

Most traditional API interaction follows this generic loop:

1. UI modifies DAG Node visually natively in RAM.
2. Angular sends simple JSON struct (`POST /api/v1/nodes` or `POST /api/v1/edges`).
3. SQLite repository mutates table row.
4. UI calls `POST /api/v1/nodes/reload`.
5. Orchestrator flushes event loops, terminates child UDP multiprocessing workers, and reads entirely fresh configuration blocks from disk, cleanly re-instantiating the new graph mapping.

## Standard Execution

**Start Simulator**:

```bash
sh scripts/run_sim.sh
```

_Triggers FastAPI uvicorn daemon. Falls over to recorded `.pcd` payload frames._

**Compile Frontend**:

```bash
cd web
npm run start
```

_Hosts angular framework proxy targeted to API endpoints at port `8004`._
