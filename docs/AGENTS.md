# LiDAR Standalone - Development Guide

## Project Structure

```
lidar-standalone/
├── app/                    # Backend (Python FastAPI)
│   ├── api/v1/             # REST API endpoints (all under /api/v1 prefix)
│   │   ├── lidars.py       # Lidar CRUD + enable/disable + reload + topic_prefix
│   │   ├── fusions.py      # Fusion CRUD + enable/disable
│   │   ├── nodes.py        # Runtime status monitoring (GET /nodes/status)
│   │   ├── system.py       # System status (GET /status)
│   │   └── websocket.py    # WebSocket streaming + topic discovery
│   ├── services/           # Lidar data parsing and WebSocket handling
│   │   ├── lidar/
│   │   │   ├── core/              # Core domain models and utilities
│   │   │   │   ├── sensor_model.py   # LidarSensor model class
│   │   │   │   ├── transformations.py # Point cloud transformation math
│   │   │   │   └── topics.py         # Topic prefix generation & management
│   │   │   ├── protocol/          # Communication protocols
│   │   │   │   └── binary.py         # LIDR binary format encoding/decoding
│   │   │   ├── workers/           # Process workers
│   │   │   │   ├── sick_scan.py      # Worker process for real hardware
│   │   │   │   └── pcd.py            # Worker process for PCD simulation
│   │   │   ├── sensor.py          # LidarService — sensor lifecycle orchestrator
│   │   │   └── fusion.py          # FusionService — multi-sensor fusion
│   │   └── websocket/
│   │       └── manager.py  # WebSocket connection manager
│   ├── repositories/       # SQLite persistence layer
│   │   ├── lidars.py       # Lidar config persistence (enabled, topic_prefix, pose, etc.)
│   │   ├── fusions.py      # Fusion config persistence (enabled, sensor_ids, pipeline)
│   │   └── sqlite.py       # Migrations and DB initialization
│   ├── pipeline/           # Point cloud processing pipelines
│   └── static/             # Built Angular frontend (served at /)
├── web/                    # Modern Angular frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── core/       # Core singletons (API services, Store architecture, Models)
│   │   │   │   ├── models/           # TS Interfaces (lidar.model.ts, fusion.model.ts)
│   │   │   │   ├── services/         # Global Services
│   │   │   │   │   ├── api/          # Backend API clients
│   │   │   │   │   │   ├── lidar-api.service.ts
│   │   │   │   │   │   ├── fusion-api.service.ts
│   │   │   │   │   │   └── nodes-api.service.ts  # Runtime status polling
│   │   │   │   │   └── stores/       # State Management (SignalsSimpleStoreService)
│   │   │   ├── features/   # Feature modules/components (Settings, Workspaces)
│   │   │   │   ├── settings/
│   │   │   │   │   ├── components/lidar-editor/ # Reactive Lidar Configuration Form
│   │   │   │   │   └── settings.component.*     # Node management UI with runtime status
│   │   │   │   └── workspaces/                  # 3D visualization with Three.js
│   │   │   ├── layout/     # Layout shells (Main, SideNav, Header, Footer)
│   │   │   ├── app.*       # Root component and config
│   │   │   └── ...
│   │   ├── assets/         # Static assets
│   │   ├── environments/   # Environment config (API URLs: /api/v1)
│   │   └── styles/         # Global styles and Tailwind configuration
│   ├── package.json
│   ├── angular.json
│   └── tailwind.config.js
├── config/
│   └── data.db             # SQLite database (gitignored, auto-created on first run)
├── tests/                  # Unit tests (pytest)
│   └── services/
│       └── lidar/
│           ├── test_sensor_model.py    # LidarSensor model tests
│           ├── test_transformations.py # Transformation utilities tests
│           ├── test_topics.py          # Topic management tests
│           └── test_binary_protocol.py # Binary protocol tests
├── pytest.ini              # Pytest configuration
├── requirements.txt        # Python dependencies
└── AGENTS.md               # This file
```

## Frontend Stack

- **Angular** - UI framework (utilizing Standalone Components and new Control Flow)
- **Angular Signals** - Reactive state management (`signal`, `computed`, `update`)
- **Three.js** - 3D point cloud rendering (Canvas/WebGL)
- **Tailwind CSS** - Utility-first styling
- **Synergy Design System** (`@synergy-design-system/angular`) - Enterprise UI component library
- **Reactive Forms** - Form handling and strict validation (e.g., Lidar Editor)

## Backend Stack & Architecture

- **FastAPI** - Python web framework for REST endpoints and WebSockets
- **Open3D** - Point cloud processing, transformation, and downsampling pipelines
- **Multiprocessing / Subprocesses** - Hard-isolated workers for lidar ingestion
- **Asyncio** - Event loop for non-blocking WebSocket streaming
- **NumPy** - Efficient array operations and transformations
- **pytest** - Unit testing framework with 126+ tests

### Core Backend Components

1. **API Layer (`app/api/v1/`)**: REST endpoints (all under `/api/v1` prefix) for managing Lidar/Fusion configs, enable/disable controls, runtime status, and topic discovery.
2. **WebSocket Manager (`app/services/websocket/`)**: Broadcasts optimized point cloud binary frames (LIDR format) to connected Angular clients via `/api/v1/ws/{topic}`.
3. **Lidar Service (`app/services/lidar/`)**:
   - **Core Domain (`core/`)**: Sensor models, transformation mathematics, and topic management utilities
     - `sensor_model.py` - LidarSensor class with pose configuration
     - `transformations.py` - 4x4 transformation matrices and point cloud transformations
     - `topics.py` - URL-safe topic prefix generation with collision handling
   - **Protocol (`protocol/`)**: Binary communication format
     - `binary.py` - LIDR format encoding/decoding for efficient WebSocket streaming
   - **Workers (`workers/`)**: Isolated process tasks
     - `sick_scan.py` - Connects to actual hardware (UDP)
     - `pcd.py` - Loads PCD files for simulation
   - **Services**:
     - `sensor.py` - LidarService orchestrator (307 lines, down from 424)
     - `fusion.py` - Multi-sensor point cloud fusion
   - **Dev-friendly**: Gracefully handles missing `sick_scan_api` or invalid PCD paths; surfaces errors in status endpoint instead of crashing.
   - **Runtime tracking**: Process health, last frame timestamps, errors displayed in UI
4. **SQLite Persistence (`app/repositories/`)**: All lidar and fusion configurations (including `enabled`, `topic_prefix`, pose) persisted in `config/data.db`.
5. **Testing (`tests/`)**: Comprehensive unit tests with 126+ test cases covering:
   - Transformation mathematics (33 tests)
   - Binary protocol encoding/decoding (26 tests)
   - Topic generation and collision handling (37 tests)
   - Sensor model initialization and pose management (30 tests)

## State Management Architecture

The application uses a lightweight signal-based store architecture:

1. `SignalsSimpleStoreService<T>`: A generic class providing a `.state` signal, `.select()` for computed slices, and `.set()`/`.setState()` for dispatching changes.
2. **Domain Stores** (e.g., `LidarStoreService`): Extend the simple store to provide domain-specific state (like `lidars`, `selectedLidar`, `isLoading`, `editMode`).
3. **Components**: Inject the specific store via `inject()`, bind properties directly to store selectors, and dispatch updates cleanly without convoluted input/output drilling for global models.

## Backend API Endpoints

| Endpoint                             | Method    | Description                                                        |
| ------------------------------------ | --------- | ------------------------------------------------------------------ |
| `/api/v1/lidars/`                    | GET       | Returns `{ lidars: LidarConfig[], available_pipelines: string[] }` |
| `/api/v1/lidars/`                    | POST      | Register or Update a Lidar configuration                           |
| `/api/v1/lidars/{sensor_id}`         | DELETE    | Remove a Lidar configuration                                       |
| `/api/v1/lidars/{id}/enabled`        | POST      | Enable/disable a lidar (`?enabled=true` or `false`)                |
| `/api/v1/lidars/{id}/topic_prefix`   | POST      | Update topic prefix (`?topic_prefix=...`)                          |
| `/api/v1/lidars/reload`              | POST      | Trigger backend service to reload config and restart all nodes     |
| `/api/v1/fusions/`                   | GET       | Returns `{ fusions: FusionConfig[] }`                              |
| `/api/v1/fusions/`                   | POST      | Register or Update a Fusion configuration                          |
| `/api/v1/fusions/{id}`               | DELETE    | Remove a Fusion configuration                                      |
| `/api/v1/fusions/{id}/enabled`       | POST      | Enable/disable a fusion (`?enabled=true` or `false`)               |
| `/api/v1/status`                     | GET       | Returns system status `{ version: string, is_running: bool }`      |
| `/api/v1/nodes/status`               | GET       | **Runtime status** of all nodes (process health, frame age, errors)|
| `/api/v1/topics`                     | GET       | Returns available WebSocket topics                                 |
| `/api/v1/ws/{topic}`                 | WebSocket | Point cloud binary streaming                                       |

## WebSocket Binary Frame Format (LIDR)

```
Offset | Size | Type    | Description
-------|------|---------|------------
0      | 4    | char[4] | Magic "LIDR"
4      | 4    | uint32  | Version
8      | 8    | float64 | Timestamp
16     | 4    | uint32  | Point count
20     | N*12 | float32 | Points (x, y, z) * count
```

## Development Commands

```bash
# Install dependencies
cd web && npm install

# Start dev server
npm run start

# Build for production
npm run build
```

## Flow Canvas & Node System

The Settings page features a **Node-RED style flow canvas** for visual node configuration:

### Canvas Features
- **Drag-and-drop**: Nodes can be dragged from the palette onto the canvas
- **Visual connections**: Bezier curves show data flow from sensors to fusions
- **Real-time status**: Node cards display runtime health with color-coded badges
- **Pan & Zoom**: Canvas supports panning (Shift+drag or middle mouse) and zooming (mouse wheel)
- **Auto layout**: Automatically arrange nodes in a clean grid
- **Persistent positions**: Node positions saved to localStorage

### Canvas Architecture
- **Location**: `web/src/app/features/settings/components/flow-canvas/`
- **Reactive updates**: Uses Angular `effect()` to watch store changes and auto-update when nodes are added/removed
- **Connection calculation**: SVG bezier curves calculated from node positions with output ports (right side of sensors) to input ports (left side of fusions)
- **Node state management**: Canvas reads from `LidarStoreService` and `FusionStoreService` signals

### Node Plugin System

The canvas supports extensible node types through a plugin architecture:

#### Core Plugin Components

1. **`NodePlugin` interface** (`web/src/app/core/models/node-plugin.model.ts`):
```typescript
interface NodePlugin {
  type: string;              // Unique identifier (e.g., 'sensor', 'transform')
  displayName: string;       // UI label
  description: string;       // Short description for palette
  icon: string;             // Material icon name
  category: 'source' | 'processing' | 'sink' | 'utility';
  style: NodeStyle;         // Visual styling (colors, borders)
  ports: NodePorts;         // Input/output port configuration
  config?: NodeConfigSchema; // Optional configuration schema
}
```

2. **`NodePluginRegistry` service** (`web/src/app/core/services/node-plugin-registry.service.ts`):
   - Singleton service managing all registered plugins
   - Built-in plugins: `sensor` and `fusion`
   - Methods: `register()`, `getAll()`, `getByType()`, `unregister()`

#### Creating New Plugins

**Step 1**: Define your plugin in `web/src/app/plugins/`:

```typescript
// example: web/src/app/plugins/transform-plugin.ts
import { NodePlugin } from '../core/models/node-plugin.model';

export const TransformNodePlugin: NodePlugin = {
  type: 'transform',
  displayName: 'Transform',
  description: 'Apply transformations to point clouds',
  icon: 'rotate_90_degrees_ccw',
  category: 'processing',
  style: {
    backgroundColor: '#fef3c7',
    color: '#f59e0b',
    borderColor: '#fbbf24',
  },
  ports: {
    inputs: [{ id: 'input', label: 'Points In', type: 'pointcloud' }],
    outputs: [{ id: 'output', label: 'Points Out', type: 'pointcloud' }],
  },
  config: {
    fields: [
      { name: 'rotation', type: 'number', label: 'Rotation (degrees)', default: 0 },
      { name: 'scale', type: 'number', label: 'Scale Factor', default: 1.0 },
    ],
  },
};
```

**Step 2**: Register plugin in `app.config.ts`:

```typescript
import { NodePluginRegistry } from './core/services/node-plugin-registry.service';
import { TransformNodePlugin } from './plugins/transform-plugin';

export const appConfig: ApplicationConfig = {
  providers: [
    // ... other providers
    {
      provide: APP_INITIALIZER,
      useFactory: (registry: NodePluginRegistry) => () => {
        registry.register(TransformNodePlugin);
      },
      deps: [NodePluginRegistry],
      multi: true,
    },
  ],
};
```

**Step 3**: The plugin automatically appears in the palette and can be dragged onto the canvas.

#### Plugin Categories

- **source**: Data producers (sensors, file readers)
- **processing**: Data transformers (filters, fusion, downsampling)
- **sink**: Data consumers (recorders, publishers)
- **utility**: Helper nodes (debug, monitoring)

#### Current Plugin Status

**Implemented (Frontend Only)**:
- Plugin palette displays all registered plugins dynamically
- Drag-and-drop from palette to canvas works
- Visual distinction by category colors

**Backend Integration Needed**:
- Custom plugins currently show a warning toast when dropped
- To make custom plugins functional, backend API endpoints need to be extended to support generic node types
- Currently only `sensor` and `fusion` types are persisted and executed

#### Future Plugin Enhancements

1. **Backend Support**: Extend `/api/v1/nodes` to support generic node types with plugin metadata
2. **Connection Validation**: Enforce port type compatibility when connecting nodes
3. **Node Configuration UI**: Auto-generate config forms from `NodeConfigSchema`
4. **Plugin Marketplace**: Allow importing/exporting plugin definitions
5. **Custom Node Rendering**: Support custom templates per plugin type

## Key Implementation Notes

1. **Synergy Design System**: Use Angular components from `@synergy-design-system/angular` seamlessly with standard structural directives (`*ngIf`, `*ngFor`).
2. **Signals Over RxJS Variables**: Component reactive states rely natively on Angular Signals (`set`, `update`, `computed`, `effect`) instead of `BehaviorSubject` chains where appropriate.
3. **Data Flows**:
   - Modal forms (like `<app-lidar-editor>`) are encapsulated and driven entirely by ReactiveForms logic, initialized from `LidarStoreService` state on load.
   - The "Save" actions invoke `LidarApiService`, refresh `LidarStoreService`, and subsequently clear the global form flag.
   - Canvas components use `effect()` to reactively update when stores change (e.g., when nodes are added/edited).
4. **Runtime Status Monitoring**:
   - Settings page polls `/api/v1/nodes/status` every 2 seconds to display real-time node health.
   - Status badges show: Running (green), Stale (yellow), Starting (yellow), Stopped (gray), Error (red).
   - Loading overlays with `syn-spinner` appear when toggling node enable/disable.
5. **Topic Naming**:
   - Each lidar has a persisted `topic_prefix` field (auto-generated from `name`, slugified, collision-safe).
   - WebSocket topics: `{topic_prefix}_raw_points` and `{topic_prefix}_processed_points`.
   - Fusion topics: custom topic name (e.g., `fused_points`).
